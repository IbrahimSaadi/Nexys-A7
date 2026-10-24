"""Compare identical real-HDL workloads and every observed output across engines."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import live
import server
from test_performance import SOURCE


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def workloads():
    counter = {'files': {'counter.vhd': SOURCE}, 'top': 'perf_test', 'inputs': {'enable': '1'}}
    wide = {'files': {'wide.vhd': SOURCE.replace('31 downto 0', '127 downto 0')},
            'top': 'perf_test', 'inputs': {'enable': '1'}}
    elevator = {'files': {p.name: p.read_text() for p in (server.ROOT/'examples/elevator').iterdir()},
                'top': 'elevator_top'}
    for name, project, count in [('counter32', counter, 200), ('counter128', wide, 80), ('elevator', elevator, 250)]:
        steps = [{'ns': 100000, 'wave_history': False,
                  **({'buttons': ['btnU'] if index < 220 else []} if name == 'elevator' else
                     {'inputs': {'enable': '0' if index % 40 >= 30 else '1'}})} for index in range(count)]
        yield name, project, steps


def execute(executable, project, steps):
    source_hash = digest(project)
    started = time.perf_counter()
    with patch.object(server, 'find_ghdl', return_value=str(executable)):
        session = live.Session(project)
    startup_s = time.perf_counter()-started
    try:
        snapshots = []
        timings = []
        def snapshot(frame):
            return {**{key: frame[key] for key in ('sim_ns', 'board_ns', 'digits', 'input_values', 'board_values')},
                    'wave': frame['wave']['values']}
        snapshots.append(snapshot(session.initial))
        started = time.perf_counter()
        for step in steps:
            begin = time.perf_counter()
            frame = session.advance(step)
            timings.append(time.perf_counter()-begin)
            snapshots.append(snapshot(frame))
        elapsed = time.perf_counter()-started
        assert source_hash == digest(project), 'Source/configuration mutated'
        assert frame['sim_ns'] == sum(step['ns'] for step in steps), 'HDL time mismatch'
        assert frame['overrides'] == [], 'Unexpected source overrides'
        return snapshots, {'startup_s': startup_s, 'run_s': elapsed,
                           'hdl_s': frame['sim_ns']/1e9, 'speed': frame['sim_ns']/1e9/elapsed,
                           'first_quarter_s': sum(timings[:len(timings)//4]),
                           'last_quarter_s': sum(timings[-len(timings)//4:]),
                           'snapshots': len(snapshots), 'snapshot_sha256': digest(snapshots),
                           'source_sha256': source_hash, 'flags': session.backend.flags,
                           'version': session.backend.version.strip()}
    finally:
        session.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, default=server.ROOT/'runtime/ghdl/bin/ghdl.exe')
    parser.add_argument('--output', type=Path, default=server.ROOT/'benchmark-engine-comparison.json')
    args = parser.parse_args()
    os.environ.pop('NEXYS_LAB_SYSTEM_QOS', None)
    results = []
    for index, (name, project, steps) in enumerate(workloads()):
        runs = {}
        # Alternate order so the candidate does not always run after warmup.
        order = ('baseline', 'candidate') if index % 2 == 0 else ('candidate', 'baseline')
        for label in order:
            print(name, label, flush=True)
            runs[label] = execute(getattr(args, label).resolve(), project, steps)
        assert runs['baseline'][0] == runs['candidate'][0], name + ': output/timing mismatch'
        entry = {'project': name, 'outputs_identical': True,
                 'baseline': runs['baseline'][1], 'candidate': runs['candidate'][1],
                 'speedup': runs['baseline'][1]['run_s']/runs['candidate'][1]['run_s']}
        results.append(entry)
        print(json.dumps({'project': name, 'speedup': entry['speedup'], 'outputs_identical': True}), flush=True)
        args.output.write_text(json.dumps(results, indent=2), encoding='utf-8')
