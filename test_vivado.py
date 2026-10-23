import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import vivado


class VivadoTests(unittest.TestCase):
    def test_windows_internal_paths_resolve_to_public_launchers(self):
        with tempfile.TemporaryDirectory(prefix='Vivado tools ') as root:
            folder=Path(root)/'bin'
            internal=folder/'unwrapped'/'win64.o'
            internal.mkdir(parents=True)
            for tool in ('xvhdl','xelab','xsim'):
                (folder/(tool+'.bat')).touch()
                (folder/(tool+'.exe')).touch()
                (internal/(tool+'.exe')).touch()
            with patch('vivado.sys.platform','win32'):
                for selected in (root,folder,internal,internal/'xvhdl.exe',folder/'xsim.bat'):
                    with self.subTest(selected=selected):
                        found=vivado.discover(str(selected))
                        for tool,path in found.items():
                            self.assertTrue(Path(path).samefile(folder/(tool+'.bat')))
                with patch.dict(os.environ,{'VIVADO_PATH':str(internal),'XILINX_VIVADO':''}),patch('vivado.shutil.which',return_value=None):
                    self.assertTrue(Path(vivado.discover()['xvhdl']).samefile(folder/'xvhdl.bat'))
                with patch.dict(os.environ,{'VIVADO_PATH':'','XILINX_VIVADO':''}),patch('vivado.shutil.which',return_value=str(internal/'xvhdl.exe')):
                    self.assertTrue(Path(vivado.discover()['xvhdl']).samefile(folder/'xvhdl.bat'))

    def test_windows_missing_launchers_never_fall_back_to_executables(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)/'bin'
            internal=folder/'unwrapped'/'win64.o'
            internal.mkdir(parents=True)
            for tool in ('xvhdl','xelab','xsim'):
                (folder/(tool+'.exe')).touch()
                (internal/(tool+'.exe')).touch()
            with patch('vivado.sys.platform','win32'):
                for selected in (root,internal):
                    with self.assertRaisesRegex(ValueError,'launchers were not found'):
                        vivado.discover(str(selected))
                self.assertFalse(vivado.status(str(internal))['available'])

    @unittest.skipUnless(os.name=='nt','Windows batch execution regression')
    def test_windows_wrapper_runs_with_spaces_and_sets_environment(self):
        with tempfile.TemporaryDirectory(prefix='Vivado tools ') as root:
            folder=Path(root)/'bin';folder.mkdir()
            # A wrapper must actually execute, including its environment setup.
            (folder/'check.cmd').write_text('@echo off\necho %NEXYS_WRAPPER_READY%\necho ARG1=%~1\necho ARG2=%~2\n',encoding='ascii')
            for tool in ('xvhdl','xelab','xsim'):
                (folder/(tool+'.bat')).write_text('@echo off\nset "NEXYS_WRAPPER_READY=WRAPPER_ENV_OK"\ncall "%~dp0check.cmd" %*\nexit /b 0\n',encoding='ascii')
            for tool in vivado.discover(root).values():
                code,output=vivado.execute(tool,['--2008','source with spaces.vhd'],root)
                self.assertEqual(code,0,output)
                self.assertIn('WRAPPER_ENV_OK',output)
                self.assertIn('ARG1=--2008',output)
                self.assertIn('ARG2=source with spaces.vhd',output)

    def test_installed_toolset_detection_and_partial_install(self):
        with tempfile.TemporaryDirectory(prefix='Vivado tools ') as root:
            folder=Path(root)/'bin';folder.mkdir()
            suffix='.bat' if os.name=='nt' else ''
            for name in ('xvhdl','xelab'):(folder/(name+suffix)).touch()
            with patch.dict(os.environ,{'VIVADO_PATH':root}),patch('vivado.shutil.which',return_value=None):
                # Avoid unrelated locally installed tools in this isolated test.
                with patch('vivado.os.name',os.name):
                    if os.name!='nt':self.assertFalse(vivado.status()['available'])
                (folder/('xsim'+suffix)).touch()
                found=vivado.discover()
                # Windows may expand the TEMP directory's DOS short name.
                self.assertTrue(Path(found['xsim']).parent.samefile(folder))

    def test_batch_metacharacters_are_not_interpreted(self):
        with self.assertRaises(ValueError):vivado.command('C:/Vivado/bin/xsim.bat',['snapshot','name&whoami'])
        with self.assertRaises(ValueError):vivado.command('C:/%TEMP%/xsim.bat',['snapshot'])

    def test_compile_failure_is_not_reported_as_simulation_success(self):
        data={'files':{'bad.vhd':'invalid source'},'top':'bad','duration':'2us'}
        with patch('vivado.discover',return_value={name:name for name in ('xvhdl','xelab','xsim')}),patch('vivado.execute',return_value=(1,'ERROR: syntax error')):
            result=vivado.run(data)
        self.assertFalse(result['ok'])
        self.assertEqual(result['phase'],'analysis')

    def test_runtime_failure_assertions_are_detected_even_with_zero_exit(self):
        responses=[(0,'analysis complete'),(0,'elaboration complete'),(0,'Failure: assertion at time 0 ns')]
        with patch('vivado.discover',return_value={name:name for name in ('xvhdl','xelab','xsim')}),patch('vivado.execute',side_effect=responses):
            result=vivado.run({'files':{'tb.vhd':'entity tb is end;'},'top':'tb','duration':'2us'})
        self.assertFalse(result['ok'])
        self.assertEqual(result['phase'],'simulation')

    def test_bad_source_paths_and_durations_rejected_before_tool_launch(self):
        for data in ({'files':{'../escape.vhd':'abc'},'top':'a'}, {'files':{'a.vhd':'abc'},'top':'a','duration':'1us;exec bad'}):
            with self.assertRaises(ValueError):vivado.run(data)

    def test_error_severity_is_not_a_passing_testbench(self):
        responses=[(0,'analysis complete'),(0,'elaboration complete'),(0,'Error: unexpected data\nTime: 10 ns')]
        with patch('vivado.discover',return_value={name:name for name in ('xvhdl','xelab','xsim')}),patch('vivado.execute',side_effect=responses):
            result=vivado.run({'files':{'tb.vhd':'entity tb is end;'},'top':'tb','duration':'2us'})
        self.assertFalse(result['ok'])


if __name__=='__main__':unittest.main()
