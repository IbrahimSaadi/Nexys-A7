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
APP_VERSION = '0.3.0'


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
        result = subprocess.run([executable, '--version'], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5)
        if result.returncode:
            raise ValueError('GHDL was found but could not start. Check the matching Windows architecture and extract the complete release, including DLLs.\n' + result.stdout)
        return {'ok': True, 'simulator': 'GHDL', 'language': 'VHDL-2008', 'version': result.stdout.splitlines()[0]}
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        return {'ok': False, 'simulator': 'GHDL', 'error': str(exc)}


def ports(source, entity):
    match = re.search(r'\bentity\s+' + re.escape(entity) + r'\s+is\b(.*?)\bend\b', source, re.I | re.S)
    if not match:
        raise ValueError('Top entity not found in project: ' + entity)
    body = re.sub(r'--[^\n]*', '', match[1])
    start = re.search(r'\bport\s*\(', body, re.I)
    if not start:
        return []
    text, depth = '', 1
    for char in body[start.end():]:
        if char == '(':
            depth += 1
        if char == ')':
            depth -= 1
        if depth == 0:
            break
        text += char
    result = []
    for declaration in text.split(';'):
        m = re.fullmatch(r'\s*([\w\s,]+):\s*(in|out|inout|buffer)\s+(std_logic(?:_vector\s*\(\s*\d+\s+(?:down)?to\s+\d+\s*\))?)\s*', declaration, re.I)
        if not m:
            raise ValueError('Board mode supports std_logic and fixed numeric std_logic_vector ports. Use Testbench mode for other interfaces. Unsupported: ' + declaration)
        nums = re.search(r'\(\s*(\d+)\s+(downto|to)\s+(\d+)\s*\)', m[3], re.I)
        width = abs(int(nums[1])-int(nums[3]))+1 if nums else 1
        if width > 64:
            raise ValueError('Board port exceeds 64 bits')
        for name in m[1].replace(' ', '').replace('\n', '').split(','):
            result.append({'name': name, 'direction': m[2].lower(), 'type': m[3], 'width': width, 'vector': bool(nums)})
    return result


def auto_map(port):
    name = port['name'].lower()
    return {'clk': 'clock', 'clk100mhz': 'clock', 'rst': 'btnC', 'reset': 'btnC', 'go': 'btnU', 'dest_floor': 'sw', 'sw': 'sw', 'led': 'led', 'segment': 'segment', 'seg': 'segment', 'an': 'an', 'dp': 'dp', 'door': 'door', 'btnc': 'btnC', 'btnu': 'btnU', 'btnl': 'btnL', 'btnr': 'btnR', 'btnd': 'btnD'}.get(name, 'zero' if port['direction'] == 'in' else 'unused')


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
            now = int(line[1:])
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
            p = subprocess.run([executable, *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=25)
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
            (wd/name).write_text(content)
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
            if self.path in ('/api/live/start', '/api/live/advance', '/api/live/stop'):
                import live
                return self.reply(live.api(self.path.rsplit('/', 1)[-1], data))
            if self.path == '/api/run':
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
