"""Backend routing and optimization must preserve compatibility and checks."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import ghdl_backend
import server


class BackendTests(unittest.TestCase):
    def test_native_optimization_and_jit_commands(self):
        with tempfile.TemporaryDirectory(prefix='engine with spaces ') as directory:
            executable = Path(directory)/'ghdl.exe'
            executable.touch()
            binary = Path(directory)/('lab_live_tb.exe' if os.name == 'nt' else 'lab_live_tb')
            binary.touch()
            for description, native in [('llvm 21.1.8 code generator', True),
                                         ('static elaboration, LLVM JIT code generator', False),
                                         ('static elaboration, mcode JIT code generator', False)]:
                with self.subTest(description=description):
                    ghdl_backend._version.cache_clear()
                    with patch('ghdl_backend.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=description)):
                        backend = ghdl_backend.Backend(executable)
                    self.assertEqual(backend.native, native)
                    self.assertEqual(backend.flags, ['-O2'] if native else [])
                    self.assertEqual(backend.environment['PATH'].split(os.pathsep)[0], directory)
                    command = backend.live_command(directory, 'lab_live_tb')
                    self.assertEqual(command[-1], '--assert-level=error')
                    self.assertEqual(command[0], str(binary) if native else str(executable))
                    self.assertNotIn('--ieee-asserts=disable', command)
            ghdl_backend._version.cache_clear()

    @unittest.skipUnless(os.name == 'nt', 'Windows portable runtime')
    def test_verified_native_default_explicit_path_and_compatibility(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native = root/'runtime/ghdl-llvm/ucrt64/bin/ghdl.exe'
            original = root/'runtime/ghdl/bin/ghdl.exe'
            for executable in (native, original):
                executable.parent.mkdir(parents=True)
                executable.touch()
            with patch('server.ROOT', root), patch.dict(os.environ, {'GHDL_PATH': '', 'NEXYS_LAB_GHDL_BACKEND': 'auto'}):
                self.assertEqual(server.find_ghdl(), str(original))
                (root/'runtime/ghdl-llvm/READY').write_text('validated')
                self.assertEqual(server.find_ghdl(), str(native))
                with patch.dict(os.environ, {'NEXYS_LAB_GHDL_BACKEND': 'mcode'}):
                    self.assertEqual(server.find_ghdl(), str(original))
                with patch.dict(os.environ, {'GHDL_PATH': str(original)}):
                    self.assertEqual(server.find_ghdl(), str(original))


if __name__ == '__main__':
    unittest.main()
