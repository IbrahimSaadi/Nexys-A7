"""Fixed-batch real-GHDL benchmark; excludes browser rendering and compilation.

Run with the portable Python from the Nexys-Lab directory:
  runtime/python/python.exe scripts/benchmark_transport.py --seconds 35
  runtime/python/python.exe scripts/benchmark_transport.py --transport direct
"""
import argparse
import contextlib
import http.client
import json
import os
from pathlib import Path
import statistics
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import live
import server
from test_performance import SOURCE


def process_cpu_seconds(process):
    if os.name != 'nt':
        return None
    import ctypes
    from ctypes import wintypes
    values = [wintypes.FILETIME() for _ in range(4)]
    function = ctypes.windll.kernel32.GetProcessTimes
    function.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)]*4
    function.restype = wintypes.BOOL
    if not function(int(process._handle), *[ctypes.byref(value) for value in values]):
        return None
    return sum((value.dwHighDateTime << 32) + value.dwLowDateTime for value in values[2:])/1e7


def benchmark(args):
    # Select QoS explicitly so default/high comparisons remain reproducible
    # after Session starts opting into interactive scheduling automatically.
    os.environ['NEXYS_LAB_SYSTEM_QOS'] = '1'
    if args.project == 'elevator':
        files = {p.name: p.read_text() for p in (server.ROOT/'examples/elevator').iterdir()}
        project = {'files': files, 'top': 'elevator_top'}
    else:
        project = {'files': {'perf.vhd': SOURCE}, 'top': 'perf_test', 'inputs': {'enable': '1'}}
    httpd = client = session = None
    token = None
    connections = 0

    def request(action, data):
        nonlocal connections
        if client.sock is None:
            connections += 1
        client.request('POST', '/api/live/' + action, json.dumps(data), {'Content-Type': 'application/json'})
        response = client.getresponse()
        result = json.loads(response.read())
        if response.status != 200:
            raise RuntimeError(result)
        return result

    try:
        if args.transport == 'http':
            httpd = server.create_server('127.0.0.1', 0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            client = http.client.HTTPConnection(*httpd.server_address, timeout=35)
            initial = request('start', project)
            token = initial['session']
        else:
            session = live.Session(project)
            initial = session.initial
        simulator = (live.sessions[token] if token else session).process
        qos_applied = None
        if args.qos == 'high':
            from windows_performance import interactive_qos
            qos_applied = interactive_qos(simulator.pid)
        windows = []
        started = window_start = time.perf_counter()
        cpu_start = process_cpu_seconds(simulator)
        previous_ns = initial['sim_ns']
        samples = []
        while time.perf_counter() - started < args.seconds:
            begin = time.perf_counter()
            data = {'session': token, 'ns': args.interval, 'wave_history': False}
            frame = request('advance', data) if client else session.advance(data)
            end = time.perf_counter()
            metrics = frame['performance']
            samples.append(((end-begin)*1000, metrics['simulator_wait_ms'], metrics['frame_build_ms'],
                            max(0, (end-begin)*1000-metrics['backend_ms'])))
            if end-window_start >= 5 or end-started >= args.seconds:
                cpu_end = process_cpu_seconds(simulator)
                windows.append({'elapsed_s': round(end-started, 3), 'batches': len(samples),
                                'speed': (frame['sim_ns']-previous_ns)/1e9/(end-window_start),
                                'simulator_cpu_fraction': (cpu_end-cpu_start)/(end-window_start) if cpu_end is not None else None,
                                **{name: statistics.median(row[index] for row in samples)
                                   for index, name in enumerate(('request_ms', 'wait_ms', 'frame_ms', 'transport_ms'))}})
                previous_ns = frame['sim_ns']
                window_start = end
                cpu_start = cpu_end
                samples = []
                if args.qos == 'switch' and end-started >= 15 and qos_applied is None:
                    from windows_performance import interactive_qos
                    qos_applied = interactive_qos(simulator.pid)
        return {'transport': args.transport, 'project': args.project, 'interval_ns': args.interval,
                'engine': (live.sessions[token] if token else session).backend.version.strip(),
                'compiler_flags': (live.sessions[token] if token else session).backend.flags,
                'connections': connections, 'qos': args.qos, 'qos_applied': qos_applied, 'windows': windows}
    finally:
        if client:
            try:
                if token:
                    request('stop', {'session': token})
            finally:
                client.close()
        if session:
            session.close()
        if httpd:
            httpd.shutdown()
            httpd.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport', choices=('direct', 'http'), default='http')
    parser.add_argument('--project', choices=('counter', 'elevator'), default='counter')
    parser.add_argument('--seconds', type=float, default=35)
    parser.add_argument('--interval', type=int, default=136560)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--qos', choices=('default','high','switch'), default='default')
    args = parser.parse_args()
    # Keep per-request logging out of the terminal, like a hidden server window.
    with open(server.ROOT/'benchmark-http.log', 'w', encoding='utf-8') as log, contextlib.redirect_stderr(log):
        result = benchmark(args)
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    print(text)
