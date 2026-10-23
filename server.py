#!/usr/bin/env python3
"""Local HDL lab. Simulation is real GHDL, never JavaScript emulation."""
import argparse
from collections import deque
import errno
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

ROOT = Path(__file__).resolve().parent
MAX_FILES = 40
APP_VERSION = '0.4.1'


def find_ghdl():
    """Resolve locally; never assume the cloud machine's paths exist on Windows."""
    configured = os.environ.get('GHDL_PATH', '').strip().strip('"')
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_dir():
            candidate /= 'ghdl.exe' if os.name == 'nt' else 'ghdl'
        if candidate.is_file():
            return str(candidate.resolve())
        raise ValueError('GHDL_PATH does not point to GHDL: ' + configured + '. Set it to the full path of ghdl.exe (Windows) or ghdl, then restart the server.')
    bundled = ROOT / 'runtime' / 'ghdl' / 'bin' / ('ghdl.exe' if os.name == 'nt' else 'ghdl')
    if bundled.is_file():
        return str(bundled)
    found = shutil.which('ghdl')
    if found:
        return found
    cloud = Path('/workspace/.nexys-tools/bin/ghdl')
    if os.name != 'nt' and cloud.is_file():
        return str(cloud)
    raise ValueError('GHDL was not found. Install GHDL from https://github.com/ghdl/ghdl/releases, add its bin folder to PATH, and restart the terminal and server. On Windows you can instead set $env:GHDL_PATH = "C:\\path\\to\\ghdl\\bin\\ghdl.exe" in PowerShell before running py server.py. Verify with ghdl --version. See the Windows section in README.md.')


def simulator_status():
    try:
        executable = find_ghdl()
        result = subprocess.run([executable, '--version'], text=True, encoding='utf-8',errors='replace', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5)
        if result.returncode:
            raise ValueError('GHDL was found but could not start. Check the matching Windows architecture and extract the complete release, including DLLs.\n' + result.stdout)
        return {'ok': True, 'simulator': 'GHDL', 'language': 'VHDL-2008', 'version': result.stdout.splitlines()[0]}
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        return {'ok': False, 'simulator': 'GHDL', 'error': str(exc)}


def _section(body, keyword):
    start = re.search(r'\b' + keyword + r'\s*\(', body, re.I)
    if not start:
        return ''
    text, depth = '', 1
    for char in body[start.end():]:
        if char == '(':
            depth += 1
        if char == ')':
            depth -= 1
        if not depth:
            return text
        text += char
    raise ValueError('Unclosed ' + keyword + ' declaration')


def _integer_expression(text, names):
    import ast
    import operator
    tree = ast.parse(text.strip().lower().replace(' mod ', ' % '), mode='eval')
    operations = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                  ast.Div: operator.floordiv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) is int:
            result = node.value
        elif isinstance(node, ast.Name) and node.id in names and type(names[node.id]) is int:
            result = names[node.id]
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            result = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and type(node.op) in operations:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and not 0 <= right <= 24:
                raise ValueError('Unsupported range exponent')
            result = operations[type(node.op)](left, right)
        else:
            raise ValueError('Unresolved range expression: ' + text + '. Supply integer generics or use Testbench mode.')
        if abs(result) > 10000000:
            raise ValueError('Range expression exceeds adapter limit')
        return result
    return visit(tree)


def ports(source, entity, generics=None):
    source = re.sub(r'--[^\n]*', '', source)
    match = re.search(r'\bentity\s+' + re.escape(entity) + r'\s+is\b(.*?)\bend\b', source, re.I | re.S)
    if not match:
        raise ValueError('Top entity not found in project: ' + entity)
    body = match[1]
    overrides = {name.lower(): value for name, value in (generics or {}).items()}
    names = {name:value for name,value in overrides.items() if type(value) is int}
    for declaration in _section(body, 'generic').split(';'):
        m = re.match(r'\s*([\w\s,]+):\s*\w+\s*:=\s*(.+)', declaration, re.S)
        if m:
            try:
                value = _integer_expression(m[2], names)
            except (ValueError, SyntaxError, ZeroDivisionError):
                continue
            for name in re.split(r'\s*,\s*',m[1].strip()):
                if name.lower() not in overrides:
                    names[name.lower()] = value
    for name, value in (generics or {}).items():
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',name):
            raise ValueError('Invalid generic name')
        if type(value) is int:
            names[name.lower()] = value
    result = []
    for declaration in _section(body, 'port').split(';'):
        if not declaration.strip():
            continue
        declaration = declaration.split(':=',1)[0]
        m = re.fullmatch(r'\s*([\w\s,]+):\s*(in|out|inout|buffer)\s+(std_logic|std_ulogic|bit|std_logic_vector|std_ulogic_vector|bit_vector|signed|unsigned)\s*(?:\((.*?)\))?\s*',declaration,re.I|re.S)
        if not m:
            raise ValueError('This port type needs a custom Testbench adapter: ' + declaration)
        base = m[3].lower()
        vector = base.endswith('_vector') or base in ('signed','unsigned')
        left = right = None
        if vector:
            bounds = re.fullmatch(r'\s*(.*?)\s+(downto|to)\s+(.*?)\s*',m[4] or '',re.I|re.S)
            if not bounds:
                raise ValueError('Vector bounds must resolve before board simulation: ' + declaration)
            left = _integer_expression(bounds[1],names)
            right = _integer_expression(bounds[3],names)
            width = abs(left-right)+1
            if (bounds[2].lower()=='downto' and left<right) or (bounds[2].lower()=='to' and left>right):
                raise ValueError('Null vector ranges are not supported by the board adapter')
            concrete = f'{base}({left} {bounds[2].lower()} {right})'
        else:
            width, concrete = 1, base
        if not 1 <= width <= 4096:
            raise ValueError('Board adapter supports ports up to 4096 bits')
        for name in re.split(r'\s*,\s*',m[1].strip()):
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',name):
                raise ValueError('Invalid port identifier')
            result.append({'name':name,'direction':m[2].lower(),'type':concrete,'width':width,'vector':vector,'left':left,'right':right})
    return result


def auto_map(port):
    name = port['name'].lower()
    return {'clk': 'clock', 'clk100mhz': 'clock', 'rst': 'btnC', 'reset': 'btnC', 'go': 'btnU', 'dest_floor': 'sw', 'sw': 'sw', 'led': 'led', 'segment': 'segment', 'seg': 'segment', 'an': 'an', 'dp': 'dp', 'door': 'door', 'btnc': 'btnC', 'btnu': 'btnU', 'btnl': 'btnL', 'btnr': 'btnR', 'btnd': 'btnD'}.get(name, 'zero' if port['direction'] == 'in' else 'unused')


def inspect_project(data):
    import board
    files = data.get('files', {})
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_FILES or any(not isinstance(value,str) for value in files.values()):
        raise ValueError('Import or create VHDL source files first (1–40 files).')
    source = '\n'.join(text for name,text in files.items() if name.lower().endswith(('.vhd','.vhdl')))
    clean = re.sub(r'--[^\n]*','',source)
    entities = list(dict.fromkeys(re.findall(r'\bentity\s+(\w+)\s+is\b',clean,re.I)))
    if not entities:
        raise ValueError('No VHDL entities found')
    referenced = {name.lower() for name in re.findall(r'\bentity\s+work\.(\w+)',clean,re.I)}
    referenced.update(name.lower() for name in re.findall(r'\b\w+\s*:\s*(\w+)\s+(?:generic\s+map|port\s+map)\b',clean,re.I))
    candidates = [name for name in entities if name.lower() not in referenced]
    suggested = next((name for name in candidates if name.lower()=='main'), next((name for name in candidates if name.lower().endswith('_top')),next((name for name in candidates if not name.lower().startswith('tb')),entities[0])))
    requested = data.get('top','')
    top = next((name for name in entities if name.lower()==str(requested).lower()),suggested)
    ps = ports(source,top,data.get('generics') or {})
    bindings = board.suggest_mapping(ps,files)
    mapping = {p['name']:('zero' if p['direction']=='in' else 'unused') for p in ps}
    for p in ps:
        bits = bindings['mapping'].get(p['name'],[])
        if not bits or any(bit['signal'] is None for bit in bits):
            continue
        signals = [bit['signal'] for bit in bits]
        if not p['vector']:
            value = signals[0]
            if value in ('clock','btnC','btnU','btnL','btnR','btnD','cpu_resetn','dp') or value.startswith('sw['):
                mapping[p['name']] = value
            elif value.startswith('led['):
                mapping[p['name']] = ('door' if p['name'].lower()=='door' else 'led') if value=='led[0]' else 'unused'
        else:
            for family in ('sw','led','segment','an'):
                if all(bit['signal']==f"{family}[{bit['index']}]" for bit in bits):
                    mapping[p['name']] = family
                    break
    clocks = {}
    for name,period in bindings.get('clocks',{}).items():
        if isinstance(period,dict):
            period = period.get('period_ns')
        if isinstance(period,(int,float)) and period>0:
            clocks[name] = {'period_ns':period}
    return {'ok':True,'top':top,'suggested_top':suggested,'entities':entities,'ports':ps,'mapping':mapping,'bindings':bindings,'clocks':clocks}


def board_tb(top, ps, mapping, commands, fast):
    declarations, bindings = [], []
    for p in ps:
        n = p['name']
        init = "(others => '0')" if p['vector'] else "'0'"
        declarations.append(f"signal io_{n}: {p['type']} := {init};")
        bindings.append(f'{n} => io_{n}')
    period = 10
    tick = 10000 if fast else 1000000000
    code = ['library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;', 'entity lab_board_tb is end;', 'architecture sim of lab_board_tb is', *declarations, 'begin', f"dut: entity work.{top} port map ({', '.join(bindings)});"]
    for p in ps:
        if p['direction'] == 'in' and mapping.get(p['name']) == 'clock':
            if p['vector']:
                raise ValueError('Clock must be scalar')
            code.append(f"io_{p['name']} <= not io_{p['name']} after {period//2} ns;")
    code.append('process begin')
    # Reset startup through the mapped center button.
    steps = [{'sw': 0, 'buttons': ['btnC'], 'ticks': 0}, {'sw': 0, 'buttons': [], 'ticks': 0}] + commands
    for command in steps:
        for p in ps:
            if p['direction'] != 'in':
                continue
            target = mapping.get(p['name'], auto_map(p))
            if target == 'clock':
                continue
            value = int(command.get('sw', 0)) if target == 'sw' else int(target in command.get('buttons', []))
            value %= 2**p['width']
            literal = '"' + format(value, f"0{p['width']}b") + '"' if p['vector'] else f"'{value}'"
            code.append(f"io_{p['name']} <= {literal};")
        ns = 300 + int(command.get('ticks', 0))*tick
        code.append(f'wait for {ns} ns;')
    code += ['report "BOARD SIMULATION COMPLETE";', 'std.env.finish;', 'end process;', 'end;']
    return '\n'.join(code)


def parse_vcd(text):
    signals, values, events = {}, {}, deque(maxlen=20000)
    event_count = 0
    scope, now, definitions = [], 0, True
    units={'fs':1,'ps':1000,'ns':1000000,'us':1000000000,'ms':1000000000000,'s':1000000000000000}
    scale=re.search(r'\$timescale\s+(\d+)\s*(fs|ps|ns|us|ms|s)\s+\$end',text,re.I)
    scale_fs=int(scale[1])*units[scale[2].lower()] if scale else 1
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if definitions:
            if parts[0] == '$scope':
                scope.append(parts[2])
            elif parts[0] == '$upscope':
                scope.pop()
            elif parts[0] == '$var':
                signals[parts[3]] = '.'.join(scope + [parts[4]])
            elif parts[0] == '$enddefinitions':
                definitions = False
            continue
        if line.startswith('#'):
            now = int(line[1:])*scale_fs
        else:
            if line[0] in 'bBrR' and len(parts) == 2:
                val, key = parts[0][1:], parts[1]
            elif line[0] in '01xXzZ':
                val, key = line[0], line[1:].strip()
            else:
                continue
            name = signals.get(key, '')
            values[name] = val
            if name and not re.search(r'\.(?:io_)?(?:clk|clk100mhz)$', name, re.I):
                event_count += 1
                events.append([now, name, val])
    return {'values': values, 'events': list(events), 'timescale': 'fs', 'end': now, 'truncated': event_count > 20000}


def simulate(data):
    executable = find_ghdl()
    files = data.get('files', {})
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError('Supply 1–40 files')
    for name, content in files.items():
        if not re.fullmatch(r'[\w.-]+\.(vhd|vhdl|xdc|txt)', name, re.I) or not isinstance(content, str):
            raise ValueError('Invalid file name: ' + str(name))
    top = data.get('top', 'elevator_top')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', top):
        raise ValueError('Invalid entity name')
    board = data.get('mode') == 'board'
    fast = bool(data.get('fast', True))
    logs = []
    def run(args, cwd):
        try:
            p = subprocess.run([executable, *args], cwd=cwd, text=True,encoding='utf-8',errors='replace', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=25)
        except OSError as exc:
            raise ValueError('Could not launch GHDL. Verify GHDL_PATH or PATH, extract the complete GHDL installation (including DLLs), and restart the server. Details: ' + str(exc)) from exc
        except subprocess.TimeoutExpired as exc:
            logs.append((exc.stdout or b'').decode(errors='replace') if isinstance(exc.stdout, bytes) else (exc.stdout or ''))
            raise ValueError('Simulation exceeded 25 seconds. Shorten the duration or use accelerated board mode.\n' + '\n'.join(logs))
        logs.append('$ ghdl ' + ' '.join(args) + '\n' + p.stdout)
        return p.returncode
    with tempfile.TemporaryDirectory(prefix='nexys-') as tmp:
        wd = Path(tmp)
        changed = []
        sources = []
        for name, content in files.items():
            if not name.lower().endswith(('.vhd', '.vhdl')):
                continue
            if board and fast:
                for constant, value in [('DIVISOR', 1000), ('DEBOUNCE_CYCLES', 20), ('SCAN_DIV', 5)]:
                    content, count = re.subn(r'(\bconstant\s+' + constant + r'\s*:\s*integer\s*:=\s*)\d+', lambda m: m[1]+str(value), content, flags=re.I)
                    if count:
                        changed.append(name + ': ' + constant + '=' + str(value))
            (wd/name).write_text(content,encoding='utf-8')
            sources.append(name)
        # Retry pending analyses to resolve package / entity dependencies without renaming user files.
        pending = sources[:]
        while pending:
            remaining = []
            failures = []
            progress = False
            for name in pending:
                if run(['-a', '--std=08', name], tmp):
                    remaining.append(name)
                    failures.append(logs.pop())
                else:
                    progress = True
            if not remaining:
                break
            if not progress:
                return {'ok': False, 'log': '\n'.join(logs + failures), 'phase': 'analysis'}
            pending = remaining
        ps = []
        mapping = {}
        entity = top
        if board:
            source = '\n'.join(files.values())
            ps = ports(source, top)
            if not ps:
                raise ValueError('Board mode requires a top entity with ports. Use Testbench mode for tb_fsm.')
            mapping = {p['name']: data.get('mapping', {}).get(p['name'], auto_map(p)) for p in ps}
            commands = data.get('commands', [])
            if len(commands) > 100 or sum(int(c.get('ticks', 0)) for c in commands) > 120 or any(int(c.get('ticks', 0)) < 0 for c in commands):
                raise ValueError('Board history limit: 100 actions / 120 ticks. Reset the session.')
            (wd/'lab_board_tb.vhd').write_text(board_tb(top, ps, mapping, commands, fast))
            if run(['-a', '--std=08', 'lab_board_tb.vhd'], tmp):
                return {'ok': False, 'log': '\n'.join(logs), 'phase': 'board binding'}
            entity = 'lab_board_tb'
        if run(['-e', '--std=08', entity], tmp):
            return {'ok': False, 'log': '\n'.join(logs), 'phase': 'elaboration'}
        duration = data.get('duration', '2us')
        if not re.fullmatch(r'[1-9][0-9]{0,5}(ns|us|ms)', duration):
            raise ValueError('Duration must be a positive integer followed by ns, us, or ms')
        args = ['-r', '--std=08', entity, '--assert-level=error', '--vcd=signals.vcd', '--vcd-nodate']
        for name,value in (data.get('generics') or {}).items():
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',str(name)) or not isinstance(value,(str,int,bool)):
                raise ValueError('Generic overrides require VHDL identifiers and scalar values')
            args.append('-g'+name+'='+ (str(value).lower() if isinstance(value,bool) else str(value)))
        if not board:
            args.append('--stop-time=' + duration)
        status = run(args, tmp)
        vcd_path = wd/'signals.vcd'
        if vcd_path.exists() and vcd_path.stat().st_size > 12_000_000:
            raise ValueError('Waveform exceeds 12 MB. Shorten simulation duration.')
        vcd = vcd_path.read_text() if vcd_path.exists() else ''
        return {'ok': status == 0, 'log': '\n'.join(logs), 'phase': 'simulation', 'ports': ps, 'mapping': mapping, 'wave': parse_vcd(vcd), 'vcd': vcd, 'overrides': changed, 'board': board}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT/'web'), **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def reply(self, data, status=200):
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == '/api/example':
            return self.reply({'files': {p.name: p.read_text() for p in (ROOT/'examples/elevator').iterdir() if p.is_file()}})
        if self.path == '/api/health':
            return self.reply({**simulator_status(), 'app_version': APP_VERSION})
        if self.path == '/api/board':
            import board
            return self.reply(board.catalog())
        if self.path == '/api/engines':
            import vivado
            return self.reply({'ghdl':simulator_status(),'vivado':vivado.status()})
        super().do_GET()

    def do_POST(self):
        # Local-only API: reject cross-origin browser requests and huge projects.
        origin = self.headers.get('Origin')
        if origin and origin.split('://')[-1] != self.headers.get('Host'):
            return self.reply({'error': 'Cross-origin requests denied'}, 403)
        length = int(self.headers.get('Content-Length', '0'))
        if length > 2_000_000:
            return self.reply({'error': 'Project exceeds 2 MB'}, 413)
        try:
            data = json.loads(self.rfile.read(length))
            if self.path == '/api/engines/test':
                import vivado
                return self.reply(vivado.self_test(data.get('vivado_path')))
            if self.path == '/api/engines':
                import vivado
                return self.reply({'ghdl':simulator_status(),'vivado':vivado.status(data.get('vivado_path'))})
            if self.path == '/api/inspect':
                return self.reply(inspect_project(data))
            if self.path in ('/api/live/start', '/api/live/advance', '/api/live/stop'):
                import live
                return self.reply(live.api(self.path.rsplit('/', 1)[-1], data))
            if self.path == '/api/run':
                if data.get('engine')=='vivado':
                    if data.get('mode')!='testbench':
                        raise ValueError('Vivado XSim currently runs Testbench mode. Continuous board mode uses GHDL.')
                    import vivado
                    result=vivado.run(data)
                    result['wave']=parse_vcd(result.get('vcd',''))
                    return self.reply(result)
                return self.reply(simulate(data))
            self.reply({'error': 'Unknown endpoint'}, 404)
        except Exception as exc:
            self.reply({'error': str(exc)}, 400)


class LabServer(ThreadingHTTPServer):
    def server_bind(self):
        if os.name == 'nt':
            # Windows SO_REUSEADDR can permit two processes to share a port.
            self.allow_reuse_address = False
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def create_server(host, port, auto_port=False):
    for candidate in range(port, port + (20 if auto_port and port else 1)):
        try:
            return LabServer((host, candidate), Handler)
        except OSError as exc:
            if not auto_port or not (exc.errno == errno.EADDRINUSE or getattr(exc, 'winerror', None) in (10048, 10013)):
                raise
    raise OSError('No free port found. Close old Nexys Lab server windows and retry.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--open-browser', action='store_true')
    parser.add_argument('--auto-port', action='store_true', help='Try the next port when the requested port is occupied')
    args = parser.parse_args()
    status = simulator_status()
    if not status['ok']:
        print('Simulator setup required: ' + status['error'], flush=True)
    httpd = create_server(args.host, args.port, args.auto_port)
    actual_port = httpd.server_address[1]
    print(f'Nexys Lab v{APP_VERSION} listening on {args.host}:{actual_port}', flush=True)
    if args.open_browser:
        import threading
        import webbrowser
        threading.Timer(0.5, lambda: webbrowser.open(f'http://127.0.0.1:{actual_port}')).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
