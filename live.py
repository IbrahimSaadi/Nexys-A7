"""Persistent, unmodified VHDL simulation. Wall time never substitutes for HDL time."""
import atexit
from decimal import Decimal
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
import time
import uuid


def harness(top, ps, mapping):
    declarations, bindings, clock = [], [], []
    inputs = []
    outputs = []
    for p in ps:
        n = 'io_' + p['name']
        declarations.append(f"signal {n}: {p['type']} := " + ("(others=>'0');" if p['vector'] else "'0';"))
        bindings.append(f"{p['name']} => {n}")
        target = mapping[p['name']]
        if p['direction'] == 'in':
            if target == 'clock':
                if p['vector']:
                    raise ValueError('Clock must be a scalar std_logic')
                clock.append(f'{n} <= not {n} after 5 ns;')
            else:
                inputs.append((p, target))
        else:
            outputs.append(p)
    code = ['library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all; use std.textio.all;',
            'entity lab_live_tb is end;', 'architecture sim of lab_live_tb is', *declarations,
            "type digits_t is array(0 to 7) of std_logic_vector(6 downto 0);",
            "signal digits: digits_t := (others=>(others=>'1'));", 'begin',
            f"dut: entity work.{top} port map ({', '.join(bindings)});", *clock]
    seg = next((p for p in ps if mapping[p['name']] == 'segment' and p['width'] == 7 and p['vector']), None)
    an = next((p for p in ps if mapping[p['name']] == 'an' and p['width'] == 8 and p['vector']), None)
    if seg and an:
        code += [f"process begin wait on io_{seg['name']}, io_{an['name']}; wait for 0 ns; wait for 0 ns;",
                 f"for i in 0 to 7 loop if io_{an['name']}(i)='0' then digits(i) <= io_{seg['name']}; end if; end loop; end process;"]
    code += ['process', 'variable ln: line;', 'variable sw, mask, duration_ns: integer;',
             'begin']
    # Initialize only the mapped physical reset. No timing constants are patched.
    for p, target in inputs:
        if target == 'btnC':
            code.append(f"io_{p['name']} <= " + ("(others=>'1');" if p['vector'] else "'1';"))
    code += ['wait for 100 ns;']
    for p, target in inputs:
        if target == 'btnC':
            code.append(f"io_{p['name']} <= " + ("(others=>'0');" if p['vector'] else "'0';"))
    code += ['wait for 100 ns;', 'loop', 'write(ln, string\'("LAB_FRAME ")); write(ln, now, unit=>ns);']
    for p in outputs:
        code.append(f"write(ln, string' (\" \")); write(ln, to_string(io_{p['name']}));")
    code += ["for i in 0 to 7 loop write(ln, string' (\" \")); write(ln, to_string(digits(i))); end loop;",
             'writeline(output, ln); flush(output);',
             'if endfile(input) then std.env.finish; end if;',
             'readline(input, ln); read(ln, sw); read(ln, mask); read(ln, duration_ns);']
    buttons = ['btnC', 'btnU', 'btnL', 'btnR', 'btnD']
    for p, target in inputs:
        n = 'io_' + p['name']
        if target == 'sw':
            if p['vector']:
                code.append(f'{n} <= std_logic_vector(to_unsigned(sw mod {2**min(p["width"],16)}, {p["width"]}));')
            else:
                code.append(f"if sw mod 2=1 then {n}<='1'; else {n}<='0'; end if;")
        elif target in buttons:
            bit = buttons.index(target)
            one = "(others=>'1')" if p['vector'] else "'1'"
            zero = "(others=>'0')" if p['vector'] else "'0'"
            code.append(f'if (mask / {2**bit}) mod 2=1 then {n}<={one}; else {n}<={zero}; end if;')
    code += ['wait for duration_ns * 1 ns;', 'end loop;', 'end process;', 'end;']
    return '\n'.join(code), outputs


class Session:
    def __init__(self, data):
        import server
        self.lock = threading.Lock()
        self.temp = tempfile.TemporaryDirectory(prefix='nexys-live-')
        self.process = None
        self.logs = []
        self.frames = queue.Queue()
        self.touched = time.monotonic()
        self.elapsed = 0
        self.history = []
        self.closed = False
        try:
            files = data.get('files', {})
            if not isinstance(files, dict) or not 1 <= len(files) <= server.MAX_FILES:
                raise ValueError('Supply 1–40 files')
            top = data.get('top', '')
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', top):
                raise ValueError('Invalid top entity')
            for name, text in files.items():
                if not re.fullmatch(r'[\w.-]+\.(vhd|vhdl|xdc|txt)', name, re.I) or not isinstance(text, str):
                    raise ValueError('Invalid project file')
                (Path(self.temp.name)/name).write_text(text, encoding='utf-8')
            self.ports = server.ports('\n'.join(files.values()), top)
            if not self.ports:
                raise ValueError('Board mode needs top-level ports. Use Testbench mode for a testbench.')
            self.mapping = {p['name']: data.get('mapping', {}).get(p['name'], server.auto_map(p)) for p in self.ports}
            executable = server.find_ghdl()
            pending = [name for name in files if name.lower().endswith(('.vhd', '.vhdl'))]
            def compile(args):
                r = subprocess.run([executable, *args], cwd=self.temp.name, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=25)
                return r.returncode, '$ ghdl ' + ' '.join(args) + '\n' + r.stdout
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
            source, self.outputs = harness(top, self.ports, self.mapping)
            (Path(self.temp.name)/'lab_live_tb.vhd').write_text(source)
            for args in (['-a', '--std=08', 'lab_live_tb.vhd'], ['-e', '--std=08', 'lab_live_tb']):
                status, log = compile(args)
                self.logs.append(log)
                if status:
                    raise ValueError(log)
            self.process = subprocess.Popen([executable, '-r', '--std=08', 'lab_live_tb', '--assert-level=error'],
                cwd=self.temp.name, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1)
            threading.Thread(target=self.reader, daemon=True).start()
            self.initial = self.frame()
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

    def frame(self):
        try:
            line = self.frames.get(timeout=30)
        except queue.Empty:
            self.close()
            raise ValueError('Simulator did not respond in 30 seconds. Session stopped.')
        if line is None:
            raise ValueError('Simulator stopped:\n' + '\n'.join(self.logs[-20:]))
        parts = line.split()
        scale = {'fs':1, 'ps':1000, 'ns':1000000, 'us':1000000000, 'ms':1000000000000, 'sec':1000000000000000}
        stamp = int(Decimal(parts[1]) * scale[parts[2]])
        values = {}
        for p, value in zip(self.outputs, parts[3:]):
            name = 'lab_board_tb.io_' + p['name'].lower()
            values[name] = value
            self.history.append([stamp, name, value])
        self.history = self.history[-4000:]
        digits = parts[3+len(self.outputs):3+len(self.outputs)+8]
        return {'ok': True, 'board': True, 'ports': self.ports, 'mapping': self.mapping,
                'digits': digits, 'sim_ns': (stamp-200000000)/1000000,
                'wave': {'values':values, 'events': self.history[:], 'end':stamp, 'truncated':False},
                'log': 'CONTINUOUS · ORIGINAL VHDL · 100 MHz / 10 ns · NO TIMING OVERRIDES\n' + '\n'.join(self.logs)}

    def advance(self, data):
        with self.lock:
            if self.closed:
                raise ValueError('Session closed. Press Run to start again.')
            self.touched = time.monotonic()
            switches = int(data.get('sw', 0))
            buttons = data.get('buttons', [])
            duration = int(data.get('ns', 1000000))
            if not 0 <= switches <= 65535 or not 10 <= duration <= 10000000 or duration % 10:
                raise ValueError('Invalid inputs or time interval (10 ns–10 ms, multiple of 10 ns)')
            mask = sum(1 << i for i, b in enumerate(['btnC','btnU','btnL','btnR','btnD']) if b in buttons)
            self.process.stdin.write(f'{switches} {mask} {duration}\n')
            self.process.stdin.flush()
            return self.frame()

    def close(self):
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
        session.close()


atexit.register(close_all)
threading.Thread(target=cleanup, daemon=True).start()
