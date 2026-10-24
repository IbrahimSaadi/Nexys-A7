"""Persistent VHDL simulation with explicitly selected hardware or preview timing."""
import atexit
from collections import deque
from decimal import Decimal
from pathlib import Path
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
import uuid
from windows_performance import interactive_qos
from ghdl_backend import Backend


def clock_config(ps, mapping, configured=None):
    """Return validated clocks keyed by the entity's actual port spelling."""
    names = {p['name'].lower(): p for p in ps}
    result = {}
    for p in ps:
        if mapping[p['name']] == 'clock':
            if p['direction'] != 'in' or p['vector']:
                raise ValueError('Clock must be a scalar input std_logic: ' + p['name'])
            result[p['name']] = {'period_ns': 10}
    if configured is None:
        return result
    if not isinstance(configured, dict):
        raise ValueError('clocks must be a dictionary of input names and period_ns')
    for name, options in configured.items():
        p = names.get(str(name).lower())
        if not p or p['direction'] != 'in' or p['vector']:
            raise ValueError('Clock must name a scalar input std_logic: ' + str(name))
        if options is None:
            result.pop(p['name'], None)
            continue
        period = options.get('period_ns') if isinstance(options, dict) else options
        if isinstance(period,bool) or not isinstance(period,(int,float)):
            raise ValueError('Clock period_ns must be a positive number')
        half_fs=Decimal(str(period))*500000
        if not half_fs.is_finite() or period<=0 or period>1000000000 or half_fs!=half_fs.to_integral_value() or half_fs<1:
            raise ValueError('Clock period must be positive, at most 1 second, and a multiple of 2 fs (0.000002 ns)')
        result[p['name']] = {'period_ns': period}
    return result


def port_base(port):
    return re.match(r'\s*([a-zA-Z_]+)', port.get('sim_type', port['type']))[1].lower()


def logic_expr(port, expression):
    base = port_base(port)
    if base == 'bit':
        return 'to_stdulogic(' + expression + ')'
    if base == 'bit_vector':
        return 'to_stdlogicvector(' + expression + ')'
    if port['vector']:
        return 'std_logic_vector(' + expression + ')'
    return expression


def port_expr(port, expression):
    base = port_base(port)
    if base == 'bit':
        return 'to_bit(' + expression + ')'
    if base == 'bit_vector':
        return 'to_bitvector(' + expression + ')'
    if base in ('signed', 'unsigned', 'std_ulogic_vector'):
        return base + '(' + expression + ')'
    return expression


def bit_value(value, port):
    """Normalize a manual drive value without truncation or float precision loss."""
    width = port['width']
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, int):
        if value < 0 and port_base(port) == 'signed' and value >= -(2**(width-1)):
            value %= 2**width
        if not 0 <= value < 2**width:
            raise ValueError(f"Input {port['name']} must fit its {width}-bit unsigned pattern")
        return format(value, f'0{width}b')
    if isinstance(value, str):
        text = value.strip().upper().replace('_', '')
        if text.startswith('0X'):
            try:
                return bit_value(int(text, 16), port)
            except ValueError as exc:
                raise ValueError('Invalid hexadecimal drive for ' + port['name']) from exc
        if text.startswith('0B'):
            text = text[2:]
        alphabet = r'[01]+' if port_base(port) in ('bit','bit_vector') else r'[01UXZWLH-]+'
        if len(text) == width and re.fullmatch(alphabet, text):
            return text
    raise ValueError(f"Input {port['name']} requires exactly {width} std_logic bits, an integer, or hexadecimal text")


def mapped_value(port, target, switches, buttons):
    """Resolve simple board controls; all other signals remain manually drivable."""
    width = port['width']
    target = str(target)
    if target.lower() == 'sw':
        return format(switches % 2**width, f'0{width}b')
    match = re.fullmatch(r'sw\[(\d+)\]', target, re.I)
    if match:
        bit = int(match[1])
        if not 0 <= bit < 16:
            raise ValueError('Switch index must be 0–15')
        return format((switches >> bit) & 1, f'0{width}b')
    if target in ('btnC', 'btnU', 'btnL', 'btnR', 'btnD'):
        return ('1' if target in buttons else '0') * width
    if target == 'cpu_resetn':
        return '1' * width
    return ('Z' if port['direction'] == 'inout' and port_base(port) not in ('bit','bit_vector') else '0') * width


def port_indices(port):
    if not port['vector']:
        return [None]
    left, right = port.get('left'), port.get('right')
    if left is None or right is None:
        match = re.search(r'\(\s*(\d+)\s+(?:downto|to)\s*(\d+)\s*\)', port.get('sim_type', port['type']), re.I)
        if not match:
            raise ValueError('Cannot determine vector indices for ' + port['name'])
        left, right = int(match[1]), int(match[2])
    step = -1 if left > right else 1
    return list(range(left, right + step, step))


def normalize_bindings(ports, bindings):
    if bindings is None:
        bindings = {}
    if not isinstance(bindings, dict):
        raise ValueError('board_bindings must map port names to ordered bit records')
    by_name = {p['name'].lower(): p for p in ports}
    result = {p['name']: [] for p in ports}
    for name, records in bindings.items():
        port = by_name.get(str(name).lower())
        if not port or not isinstance(records, list):
            raise ValueError('Invalid board binding port: ' + str(name))
        indices, seen = set(port_indices(port)), set()
        for record in records:
            if not isinstance(record, dict):
                raise ValueError('Board binding records must be objects')
            index = record.get('index')
            if index not in indices or isinstance(index, bool) or index in seen:
                raise ValueError('Invalid or duplicate board binding index for ' + port['name'])
            signal = record.get('signal')
            if signal is not None and (not isinstance(signal, str) or len(signal) > 100):
                raise ValueError('Invalid board signal name')
            result[port['name']].append({**record, 'index': index, 'signal': signal})
            seen.add(index)
    return result


def scalar_logic_expr(port, index):
    expression = 'io_' + port['name'] + (f'({index})' if index is not None else '')
    return 'to_stdulogic(' + expression + ')' if port_base(port) in ('bit', 'bit_vector') else expression


def display_sources(ports, mapping, board_bindings):
    """Resolve physical segment/anode bits, independent of port spelling/order."""
    result = {'segment': {}, 'an': {}}
    for port in ports:
        if port['direction'] == 'in':
            continue
        target = mapping.get(port['name'])
        if target in result and port['vector'] and port['width'] == (7 if target == 'segment' else 8):
            # Preserve old bus mapping: leftmost port element is the high bit.
            for bit, index in enumerate(reversed(port_indices(port))):
                result[target][bit] = scalar_logic_expr(port, index)
    for port in ports:
        if port['direction'] == 'in':
            continue
        for record in board_bindings.get(port['name'], []):
            match = re.fullmatch(r'(segment|an)\[(\d+)\]', record.get('signal') or '', re.I)
            if match:
                group, bit = match[1].lower(), int(match[2])
                if bit >= (7 if group == 'segment' else 8):
                    raise ValueError('Invalid physical display bit: ' + record['signal'])
                result[group][bit] = scalar_logic_expr(port, record['index'])
    return result


def harness(top, ps, mapping, clocks=None, initial_values=None, generics=None, board_bindings=None):
    declarations, bindings, clock = [], [], []
    inputs, outputs = [], []
    clocks = clock_config(ps, mapping) if clocks is None else clocks
    board_bindings = normalize_bindings(ps, board_bindings)
    display = display_sources(ps, mapping, board_bindings)
    initial_values = initial_values or {}
    generic_bindings = []
    for name, value in (generics or {}).items():
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', str(name)):
            raise ValueError('Invalid generic name')
        if isinstance(value, bool):
            literal = str(value).lower()
        elif isinstance(value, int):
            literal = str(value)
        elif isinstance(value, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*|\"[^\"\n]*\"|\'[01]\'', value):
            literal = value
        else:
            raise ValueError('Generic values must be integers, booleans or explicit VHDL string/identifier literals')
        generic_bindings.append(f'{name} => {literal}')
    generic_clause = (' generic map (' + ', '.join(generic_bindings) + ')') if generic_bindings else ''
    for p in ps:
        n = 'io_' + p['name']
        initial = 'Z' if p['direction'] == 'inout' and port_base(p) not in ('bit','bit_vector') else '0'
        declarations.append(f"signal {n}: {p.get('sim_type', p['type'])} := " + (f"(others=>'{initial}');" if p['vector'] else f"'{initial}';"))
        bindings.append(f"{p['name']} => {n}")
        if p['name'] in clocks:
            half_fs=int(Decimal(str(clocks[p['name']]['period_ns']))*500000)
            clock.append(f"{n} <= not {n} after {half_fs} fs;")
        elif p['direction'] in ('in', 'inout'):
            inputs.append(p)
        if p['direction'] != 'in':
            outputs.append(p)
    code = ['library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all; use ieee.std_logic_textio.all; use std.textio.all;',
            'entity lab_live_tb is end;', 'architecture sim of lab_live_tb is', *declarations,
            "type digits_t is array(0 to 7) of std_logic_vector(6 downto 0);",
            "signal digits: digits_t := (others=>(others=>'1'));",
            "signal lab_segments: std_logic_vector(6 downto 0) := (others=>'1');",
            "signal lab_anodes: std_logic_vector(7 downto 0) := (others=>'1');", 'begin',
            f"dut: entity work.{top}{generic_clause} port map ({', '.join(bindings)});", *clock]
    for group, signal_name, width in [('segment', 'lab_segments', 7), ('an', 'lab_anodes', 8)]:
        for bit in range(width):
            expression = display[group].get(bit, "'1'")
            code.append(f'{signal_name}({bit}) <= {expression};')
    if display['segment'] and display['an']:
        code += ["process begin wait on lab_segments, lab_anodes; wait for 0 ns; wait for 0 ns;",
                 "for i in 0 to 7 loop if lab_anodes(i)='0' then digits(i) <= lab_segments; end if; end loop; end process;"]
    code += ['process', 'variable ln: line;', 'variable duration_ns: integer;']
    for p in inputs:
        drive_type = f"std_logic_vector({p['width']-1} downto 0)" if p['vector'] else 'std_logic'
        code.append(f"variable drive_{p['name']}: {drive_type};")
    code.append('begin')
    for p in inputs:
        bits = initial_values.get(p['name'])
        if bits is not None:
            literal = '"' + bits + '"' if p['vector'] else "'" + bits + "'"
            code.append(f"io_{p['name']} <= {literal};")
    # Reset only physical reset bindings, respecting each pin's active level.
    reset_ports=[]
    for p in inputs:
        bits=list(initial_values.get(p['name'],'0'*p['width']))
        changed=False
        if mapping[p['name']] == 'btnC':
            bits=['1']*p['width'];changed=True
        elif mapping[p['name']] == 'cpu_resetn':
            bits=['0']*p['width'];changed=True
        positions={index:position for position,index in enumerate(port_indices(p))}
        for record in board_bindings.get(p['name'],[]):
            if record['signal'] in ('btnC','cpu_resetn'):
                bits[positions[record['index']]]='1' if record['signal']=='btnC' else '0';changed=True
        if changed:
            reset_ports.append(p)
            value=''.join(bits)
            code.append(f"io_{p['name']} <= " + ('"'+value+'";' if p['vector'] else "'"+value+"';"))
    code += ['wait for 100 ns;']
    for p in reset_ports:
        bits = initial_values.get(p['name'], ('1' if mapping[p['name']]=='cpu_resetn' else '0') * p['width'])
        literal = '"' + bits + '"' if p['vector'] else "'" + bits + "'"
        code.append(f"io_{p['name']} <= {literal};")
    code += ['wait for 100 ns;', 'loop', 'write(ln, string\'("LAB_FRAME ")); write(ln, now, unit=>ns);']
    for p in outputs:
        code.append(f"write(ln, string' (\" \")); write(ln, to_string({logic_expr(p, 'io_' + p['name'])}));")
    code += ["for i in 0 to 7 loop write(ln, string' (\" \")); write(ln, to_string(digits(i))); end loop;",
             'writeline(output, ln); flush(output);',
             'if endfile(input) then std.env.finish; end if;',
             'readline(input, ln); read(ln, duration_ns);']
    for p in inputs:
        code.append(f"read(ln, drive_{p['name']}); io_{p['name']} <= {port_expr(p, 'drive_' + p['name'])};")
    code += ['wait for duration_ns * 1 ns;', 'end loop;', 'end process;', 'end;']
    return '\n'.join(code), outputs


class Session:
    def __init__(self, data):
        import server
        self.lock = threading.Lock()
        self.runner_lock = threading.Lock()
        self.background_stop_event = threading.Event()
        self.background_thread = None
        self.background_owned = False
        self.background_error = None
        self.latest = None
        self.temp = tempfile.TemporaryDirectory(prefix='nexys-live-')
        self.process = None
        self.logs = []
        self.frames = queue.Queue()
        self.touched = time.monotonic()
        self.elapsed = 0
        self.history = deque(maxlen=4000)
        self.history_truncated = False
        self.closed = False
        self.timing = data.get('timing', 'original')
        if self.timing not in ('original', 'interactive'):
            self.temp.cleanup()
            raise ValueError('Unknown timing mode')
        self.time_scale = 10000 if self.timing == 'interactive' else 1
        self.overrides = []
        self.inputs = {'sw': 0, 'buttons': []}
        try:
            files = data.get('files', {})
            if not isinstance(files, dict) or not 1 <= len(files) <= server.MAX_FILES:
                raise ValueError('Supply 1–40 files')
            top = data.get('top', '')
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', top):
                raise ValueError('Invalid top entity')
            expected = {'DIVISOR': (100000000, 10000), 'DEBOUNCE_CYCLES': (2000000, 200), 'SCAN_DIV': (50000, 5)}
            applied = {}
            for name, text in files.items():
                if not re.fullmatch(r'[\w.-]+\.(vhd|vhdl|xdc|txt)', name, re.I) or not isinstance(text, str):
                    raise ValueError('Invalid project file')
                if self.timing == 'interactive' and name.lower().endswith(('.vhd','.vhdl')):
                    # Scale only the known elevator timing profile, in disposable copies.
                    # Unknown designs retain original mode rather than silently guessing.
                    for constant, (original, preview) in expected.items():
                        pattern = r'(\bconstant\s+' + constant + r'\s*:\s*integer\s*:=\s*)' + str(original) + r'\b'
                        text, count = re.subn(pattern, lambda m: m[1]+str(preview), text, flags=re.I)
                        if count:
                            applied[constant] = applied.get(constant,0) + count
                            self.overrides.append(f'{name}: {constant}={preview} (original {original})')
                (Path(self.temp.name)/name).write_text(text, encoding='utf-8')
            if self.timing == 'interactive' and any(applied.get(name) != 1 for name in expected):
                raise ValueError('Interactive timing requires the standard elevator constants (DIVISOR=100000000, DEBOUNCE_CYCLES=2000000, SCAN_DIV=50000). Select Original timing for this design.')
            generics = data.get('generics') or {}
            if not isinstance(generics, dict):
                raise ValueError('generics must be a dictionary')
            self.ports = server.ports('\n'.join(files.values()), top, generics) if generics else server.ports('\n'.join(files.values()), top)
            if not self.ports:
                raise ValueError('Board mode needs top-level ports. Use Testbench mode for a testbench.')
            self.mapping = {p['name']: data.get('mapping', {}).get(p['name'], server.auto_map(p)) for p in self.ports}
            self.board_bindings = normalize_bindings(self.ports, data.get('board_bindings'))
            self.clocks = clock_config(self.ports, self.mapping, data.get('clocks'))
            self.drive_ports = [p for p in self.ports if p['direction'] in ('in', 'inout') and p['name'] not in self.clocks]
            self.raw_inputs = {}
            self.set_inputs(data.get('inputs', {}))
            self.input_values = self.resolve_inputs(0, [])
            executable = server.find_ghdl()
            backend = Backend(executable)
            self.backend = backend
            pending = [name for name in files if name.lower().endswith(('.vhd', '.vhdl'))]
            def compile(args):
                command = backend.compile_command(args)
                r = subprocess.run(command, cwd=self.temp.name, env=backend.environment, text=True,encoding='utf-8',errors='replace', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=25)
                return r.returncode, '$ ghdl ' + ' '.join(command[1:]) + '\n' + r.stdout
            while pending:
                remaining, errors = [], []
                for name in pending:
                    status, log = compile(['-a', '--std=08', name])
                    if status:
                        remaining.append(name)
                        errors.append(log)
                    else:
                        self.logs.append(log)
                if len(remaining) == len(pending):
                    raise ValueError('\n'.join(errors))
                pending = remaining
            source, self.outputs = harness(top, self.ports, self.mapping, self.clocks, self.input_values, generics, self.board_bindings)
            (Path(self.temp.name)/'lab_live_tb.vhd').write_text(source)
            for args in (['-a', '--std=08', 'lab_live_tb.vhd'], ['-e', '--std=08', 'lab_live_tb']):
                status, log = compile(args)
                self.logs.append(log)
                if status:
                    raise ValueError(log)
            self.logs.append(backend.version.strip())
            self.process = subprocess.Popen(backend.live_command(self.temp.name, 'lab_live_tb'),
                cwd=self.temp.name, env=backend.environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True,encoding='utf-8',errors='replace', bufsize=1)
            # The simulator serves interactive browser controls even when its
            # console is hidden. Keep Windows from treating it as background work.
            if os.environ.get('NEXYS_LAB_SYSTEM_QOS') != '1' and interactive_qos(self.process.pid):
                self.logs.append('Windows interactive simulator scheduling enabled.')
            threading.Thread(target=self.reader, daemon=True).start()
            self.initial = self.frame()
            self.latest = self.initial
        except Exception:
            self.close()
            raise

    def reader(self):
        try:
            for line in self.process.stdout:
                if line.startswith('LAB_FRAME '):
                    self.frames.put(line)
                else:
                    self.logs.append(line.rstrip())
                    self.logs = self.logs[-100:]
        finally:
            self.frames.put(None)

    def frame(self, include_history=True):
        waiting = time.perf_counter()
        try:
            line = self.frames.get(timeout=30)
        except queue.Empty:
            self.close()
            raise ValueError('Simulator did not respond in 30 seconds. Session stopped.')
        if line is None:
            raise ValueError('Simulator stopped:\n' + '\n'.join(self.logs[-20:]))
        received = time.perf_counter()
        parts = line.split()
        scale = {'fs':1, 'ps':1000, 'ns':1000000, 'us':1000000000, 'ms':1000000000000, 'sec':1000000000000000}
        stamp = int(Decimal(parts[1]) * scale[parts[2]])
        values = {}
        events = []
        for p, value in zip(self.outputs, parts[3:]):
            name = 'lab_board_tb.io_' + p['name'].lower()
            values[name] = value
            events.append([stamp, name, value])
        self.history_truncated |= len(self.history) + len(events) > self.history.maxlen
        self.history.extend(events)
        digits = parts[3+len(self.outputs):3+len(self.outputs)+8]
        sim_ns = (stamp-200000000)/1000000
        clock_note = ', '.join(f"{name}={options['period_ns']} ns ({1000/options['period_ns']:g} MHz)" for name, options in self.clocks.items()) or 'none configured'
        heading = ('CONTINUOUS · ORIGINAL VHDL · NO TIMING OVERRIDES' if self.timing == 'original' else
                   'INTERACTIVE PREVIEW · COUNTERS SCALED 1:10000 IN TEMPORARY COPIES\n' + '\n'.join(self.overrides))
        heading += '\nCLOCKS: ' + clock_note
        result = {'ok': True, 'board': True, 'ports': self.ports, 'mapping': self.mapping,
                'digits': digits, 'sim_ns': (stamp-200000000)/1000000,
                'board_ns': sim_ns*self.time_scale, 'timing': self.timing, 'time_scale': self.time_scale,
                'overrides': self.overrides, 'inputs': self.inputs.copy(),
                'input_values': self.input_values.copy(), 'port_inputs': self.input_values.copy(),
                'manual_inputs': self.raw_inputs.copy(), 'clocks': self.clocks,
                'board_bindings': self.board_bindings, 'board_values': self.board_values(values),
                'wave': {'values':values, 'events': list(self.history) if include_history else events,
                         'end':stamp, 'truncated':self.history_truncated, 'mode':'history' if include_history else 'delta',
                         'capture':'sampled', 'timescale':'fs'},
                'log': heading + '\n' + '\n'.join(self.logs)}
        result['performance'] = {'simulator_wait_ms': (received-waiting)*1000,
                                 'frame_build_ms': (time.perf_counter()-received)*1000}
        return result

    def board_values(self, observed):
        result = {}
        # Physical inputs reflect their external drive; output/inout uses the
        # actual resolved DUT signal, not the external inout drive value.
        ordered = sorted(self.ports, key=lambda p: p['direction'] != 'in')
        for port in ordered:
            if port['direction'] == 'in':
                bits = self.input_values.get(port['name'])
            else:
                bits = observed.get('lab_board_tb.io_' + port['name'].lower())
            if bits is None:
                continue
            positions = {index: position for position, index in enumerate(port_indices(port))}
            for record in self.board_bindings.get(port['name'], []):
                signal = record.get('signal')
                if not signal:
                    continue
                value = bits[positions[record['index']]]
                if signal in result and result[signal] != value:
                    result[signal] = 'X'
                else:
                    result[signal] = value
        return result

    def set_inputs(self, values):
        if not isinstance(values, dict):
            raise ValueError('inputs must be a dictionary of input port names and drive values')
        by_name = {p['name'].lower(): p for p in self.drive_ports}
        updated = self.raw_inputs.copy()
        for name, value in values.items():
            p = by_name.get(str(name).lower())
            if not p:
                raise ValueError('Cannot drive unknown, output-only, or clock port: ' + str(name))
            if value is None:
                updated.pop(p['name'], None)
            else:
                updated[p['name']] = bit_value(value, p)
        self.raw_inputs = updated

    def resolve_inputs(self, switches, buttons):
        return {p['name']: self.raw_inputs.get(p['name'], mapped_value(p, self.mapping[p['name']], switches, buttons)) for p in self.drive_ports}

    def advance(self, data, _background=False):
        with self.lock:
            started = time.perf_counter()
            if self.closed:
                raise ValueError('Session closed. Press Run to start again.')
            if self.background_owned and not _background:
                raise ValueError('Return the session to foreground before advancing manually')
            self.touched = time.monotonic()
            switches = int(data.get('sw', 0))
            buttons = data.get('buttons', [])
            duration = int(data.get('ns', 1000000))
            include_history = data.get('wave_history', True)
            debug_step = data.get('debug_step', False)
            if not isinstance(debug_step, bool):
                raise ValueError('debug_step must be a boolean')
            if debug_step and (isinstance(data.get('ns'), bool) or not isinstance(data.get('ns'), int)):
                raise ValueError('Step duration must be an integer number of nanoseconds')
            if not isinstance(include_history, bool):
                raise ValueError('wave_history must be a boolean')
            valid_duration = 1 <= duration <= 10000000 if debug_step else 10 <= duration <= 10000000 and duration % 10 == 0
            if not 0 <= switches <= 65535 or not valid_duration:
                if debug_step:
                    raise ValueError('Invalid inputs or step duration (1–10,000,000 integer ns)')
                raise ValueError('Invalid inputs or time interval (10 ns–10 ms, multiple of 10 ns)')
            if not isinstance(buttons, list) or any(b not in ('btnC','btnU','btnL','btnR','btnD') for b in buttons):
                raise ValueError('buttons must be a list of board button names')
            self.set_inputs(data.get('inputs', {}))
            self.inputs = {'sw': switches, 'buttons': list(buttons)}
            self.input_values = self.resolve_inputs(switches, buttons)
            tokens = [str(duration), *[self.input_values[p['name']] for p in self.drive_ports]]
            self.process.stdin.write(' '.join(tokens) + '\n')
            self.process.stdin.flush()
            result = self.frame(include_history)
            result['performance'].update({'backend_ms': (time.perf_counter()-started)*1000,
                                          'interval_ns': duration})
            self.latest = result
            return result

    def run_background(self, data):
        """Transfer the existing session to one server-side driver, without restarting HDL."""
        with self.runner_lock:
            with self.lock:
                if self.closed:
                    raise ValueError('Session closed')
                if self.background_owned:
                    return {'ok': True, 'background': True}
                maximum = data.get('maximum_ns', 1000000)
                if type(maximum) is not int or not 10 <= maximum <= 10000000 or maximum % 10:
                    raise ValueError('Invalid background sample interval')
                switches = data.get('sw', 0)
                if type(switches) is not int or not 0 <= switches <= 65535:
                    raise ValueError('Invalid switches')
                self.set_inputs(data.get('inputs', {}))
                self.background_owned = True
                self.background_error = None
                self.background_stop_event.clear()
                baseline = self.latest['sim_ns']
            def drive():
                started = time.monotonic()
                quantum, cost = min(10000, maximum), None
                try:
                    # Bound unattended work if the client disappears without sending stop.
                    while not self.background_stop_event.is_set() and not self.closed:
                        if time.monotonic() - started > 3600:
                            break
                        duration = quantum if data.get('automatic', True) else maximum
                        frame = self.advance({'ns': duration, 'sw': switches, 'buttons': [],
                                              'wave_history': False}, _background=True)
                        measured = max(frame['performance']['simulator_wait_ms'], 0.001) / duration
                        cost = measured if cost is None else 0.7 * cost + 0.3 * measured
                        quantum = max(10, min(maximum, int(max(duration / 4, min(duration * 2, 20 / cost)) / 10) * 10))
                        wait = max(0, (frame['sim_ns'] - baseline) / 1e9 - (time.monotonic() - started))
                        if wait:
                            self.background_stop_event.wait(wait)
                except Exception as exc:
                    self.background_error = str(exc)
            self.background_thread = threading.Thread(target=drive, daemon=True)
            self.background_thread.start()
            return {'ok': True, 'background': True}

    def return_foreground(self):
        with self.runner_lock:
            self.background_stop_event.set()
            if self.background_thread:
                self.background_thread.join(timeout=35)
                if self.background_thread.is_alive():
                    raise ValueError('Background simulator did not stop its current advance')
            with self.lock:
                self.background_owned = False
                self.touched = time.monotonic()
                if self.background_error:
                    raise ValueError(self.background_error)
                if self.closed:
                    raise ValueError('Session closed')
                return {**self.latest, 'wave': {**self.latest['wave'], 'events': list(self.history),
                        'mode': 'history', 'truncated': self.history_truncated}}

    def close(self):
        self.background_stop_event.set()
        self.closed = True
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            for stream in (self.process.stdin, self.process.stdout):
                if stream:
                    stream.close()
        self.temp.cleanup()


sessions = {}
registry_lock = threading.Lock()


def api(action, data):
    if action == 'start':
        with registry_lock:
            if len(sessions) >= 4:
                raise ValueError('Four live sessions are already open. Stop an old session first.')
            session = Session(data)
            token = uuid.uuid4().hex
            sessions[token] = session
        return {**session.initial, 'session': token}
    token = data.get('session')
    with registry_lock:
        session = sessions.get(token)
        if action == 'stop':
            session = sessions.pop(token, None)
    if action == 'stop':
        if session:
            with session.lock:
                session.close()
        return {'ok': True}
    if not session:
        raise ValueError('Session expired. Press Run again.')
    if action == 'background':
        return session.run_background(data)
    if action == 'foreground':
        return session.return_foreground()
    return session.advance(data)


def cleanup():
    while True:
        time.sleep(30)
        with registry_lock:
            stale = [key for key, value in sessions.items() if time.monotonic()-value.touched > 120]
            for key in stale:
                session = sessions.pop(key)
                with session.lock:
                    session.close()


def close_all():
    for session in list(sessions.values()):
        session.background_stop_event.set()
        with session.lock:
            session.close()


atexit.register(close_all)
threading.Thread(target=cleanup, daemon=True).start()
