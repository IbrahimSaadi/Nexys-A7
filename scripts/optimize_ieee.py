"""Recompile unchanged IEEE package bodies with LLVM optimizations and checks."""
from pathlib import Path
import argparse
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ghdl_backend import Backend


def optimize(prefix, level=3):
    backend = Backend(prefix/'bin/ghdl.exe')
    if not backend.native:
        raise ValueError('This operation requires the native LLVM/GCC backend')
    if level not in (2, 3):
        raise ValueError('Use optimization level 2 or 3')
    backend.flags = ['-O' + str(level)]
    directory = prefix/'lib/ghdl/ieee/v08'
    for name in ('std_logic_1164-body.vhdl', 'numeric_std-body.vhdl'):
        subprocess.run(backend.compile_command(['-a', '--std=08', '--work=ieee',
                                               '../../src/ieee2008/' + name]),
                       cwd=directory, env=backend.environment, check=True, timeout=60)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--level', type=int, choices=(2, 3), default=3)
    optimize(Path(__file__).resolve().parents[1]/'runtime/ghdl-llvm/ucrt64', parser.parse_args().level)
