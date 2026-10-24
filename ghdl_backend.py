"""Backend-specific execution without changing VHDL or simulator semantics."""
from functools import lru_cache
import os
from pathlib import Path
import re
import subprocess


@lru_cache(maxsize=8)
def _version(executable, modified_ns):
    result = subprocess.run([executable, '--version'], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                            errors='replace', timeout=5)
    if result.returncode:
        raise ValueError('GHDL could not start:\n' + result.stdout)
    return result.stdout


class Backend:
    def __init__(self, executable):
        self.executable = str(Path(executable).resolve())
        self.version = _version(self.executable, Path(self.executable).stat().st_mtime_ns)
        description = self.version.lower()
        self.native = bool(re.search(r'\b(?:llvm(?: \d[\w.]*)?|gcc) (?:code generator|back-end)', description))
        self.flags = ['-O2'] if self.native else []
        self.environment = os.environ.copy()
        # Keep toolchain executables and simulator DLLs private to these children.
        # The parent/system PATH is never modified.
        directory = str(Path(self.executable).parent)
        self.environment['PATH'] = directory + os.pathsep + self.environment.get('PATH', '')

    def compile_command(self, arguments):
        return [self.executable, arguments[0], *self.flags, *arguments[1:]]

    def live_command(self, directory, entity):
        if self.native:
            binary = Path(directory)/(entity + ('.exe' if os.name == 'nt' else ''))
            if not binary.is_file():
                raise ValueError('GHDL did not produce the expected simulation executable: ' + str(binary))
            return [str(binary), '--assert-level=error']
        return [self.executable, '-r', '--std=08', entity, '--assert-level=error']
