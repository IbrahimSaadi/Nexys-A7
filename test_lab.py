"""Integration tests executing the real simulator, including UI board bindings."""
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile
import threading
import urllib.request
import json
import live
import server


class LabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = {p.name: p.read_text() for p in (server.ROOT/'examples/elevator').iterdir()}

    def run_board(self, commands):
        result = server.simulate({'files': self.files, 'top': 'elevator_top', 'mode': 'board', 'commands': commands})
        self.assertTrue(result['ok'], result['log'])
        return result

    def test_original_testbench(self):
        result = server.simulate({'files': self.files, 'top': 'tb_fsm', 'mode': 'testbench', 'duration': '2us'})
        self.assertTrue(result['ok'], result['log'])
        self.assertIn('ALL FSM TESTS PASSED', result['log'])
        self.assertNotIn('error:', result['log'])

    def test_board_roundtrip(self):
        commands = [{'sw':3, 'buttons':['btnU']}, {'sw':3, 'buttons':[]}, {'sw':15, 'buttons':[], 'ticks':3}]
        arrived = self.run_board(commands)
        self.assertEqual(arrived['wave']['values']['lab_board_tb.dut.curr_floor[3:0]'], '0011')
        self.assertEqual(arrived['wave']['values']['lab_board_tb.io_door'], '1')
        self.assertIn('elevator_top.vhd: DEBOUNCE_CYCLES=20', arrived['overrides'])
        commands += [{'sw':0, 'ticks':10}, {'sw':0, 'buttons':['btnU']}, {'sw':0, 'buttons':[]}, {'sw':0, 'ticks':3}]
        returned = self.run_board(commands)
        self.assertEqual(returned['wave']['values']['lab_board_tb.dut.curr_floor[3:0]'], '0000')
        self.assertEqual(returned['wave']['values']['lab_board_tb.io_door'], '1')
        self.assertIn('constant DEBOUNCE_CYCLES : integer := 2000000', self.files['elevator_top.vhd'])

    def test_other_design_and_mapping(self):
        source = '''library ieee; use ieee.std_logic_1164.all;
entity switch_test is port (switches: in std_logic_vector(3 downto 0); lights: out std_logic_vector(3 downto 0)); end;
architecture rtl of switch_test is begin lights <= not switches; end;'''
        r = server.simulate({'files': {'switch_test.vhd': source}, 'mode':'board', 'top':'switch_test', 'mapping':{'switches':'sw','lights':'led'}, 'commands':[{'sw':5}]})
        self.assertTrue(r['ok'], r['log'])
        self.assertEqual(r['wave']['values']['lab_board_tb.io_lights[3:0]'], '1010')

    def test_compile_failure(self):
        r = server.simulate({'files': {'broken.vhd':'entity broken is port WHAT'}, 'top':'broken', 'mode':'testbench'})
        self.assertFalse(r['ok'])
        self.assertEqual(r['phase'], 'analysis')

    def test_assertion_failure(self):
        source = '''entity bad_tb is end; architecture sim of bad_tb is begin process begin assert false report "expected failure" severity failure; wait; end process; end;'''
        r = server.simulate({'files':{'bad_tb.vhd':source}, 'top':'bad_tb','mode':'testbench'})
        self.assertFalse(r['ok'])
        self.assertIn('expected failure', r['log'])

    def test_path_rejected(self):
        with self.assertRaises(ValueError):
            server.simulate({'files':{'../outside.vhd':'abc'}})

    def test_explicit_simulator_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix='ghdl path ') as directory:
            executable = Path(directory)/'ghdl.exe'
            executable.touch()
            with patch.dict('os.environ', {'GHDL_PATH': str(executable)}):
                self.assertEqual(server.find_ghdl(), str(executable.resolve()))

    def test_invalid_explicit_path_is_actionable(self):
        with patch.dict('os.environ', {'GHDL_PATH': '/nonexistent/ghdl.exe'}):
            self.assertIn('GHDL_PATH', server.simulator_status()['error'])
            self.assertFalse(server.simulator_status()['ok'])

    def test_bundled_simulator_without_path_setup(self):
        with tempfile.TemporaryDirectory(prefix='portable app ') as directory:
            root = Path(directory)
            executable = root/'runtime/ghdl/bin'/('ghdl.exe' if server.os.name == 'nt' else 'ghdl')
            executable.parent.mkdir(parents=True)
            executable.touch()
            with patch('server.ROOT', root), patch.dict('os.environ', {'GHDL_PATH': ''}):
                self.assertEqual(server.find_ghdl(), str(executable))

    def test_missing_simulator_is_actionable(self):
        with patch.dict('os.environ', {'GHDL_PATH': ''}), patch('server.shutil.which', return_value=None), patch('server.Path.is_file', return_value=False):
            status = server.simulator_status()
            self.assertFalse(status['ok'])
            self.assertIn('GHDL was not found', status['error'])
            self.assertIn('PowerShell', status['error'])

    def test_occupied_port_uses_new_server_and_uncached_assets(self):
        old = server.create_server('127.0.0.1', 0)
        new = None
        thread = None
        try:
            port = old.server_address[1]
            if port > 65515:
                self.skipTest('Ephemeral port too close to port range limit')
            new = server.create_server('127.0.0.1', port, auto_port=True)
            self.assertNotEqual(new.server_address[1], port)
            thread = threading.Thread(target=new.serve_forever, daemon=True)
            thread.start()
            base = 'http://127.0.0.1:' + str(new.server_address[1])
            with urllib.request.urlopen(base+'/api/health') as response:
                health = json.load(response)
                self.assertEqual(health['app_version'], server.APP_VERSION)
                self.assertTrue(health['ok'], health)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
            with urllib.request.urlopen(base+'/app.js') as response:
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
        finally:
            old.server_close()
            if new:
                if thread:
                    new.shutdown()
                    thread.join()
                new.server_close()

    def test_live_clock_preserves_state_and_exact_100mhz(self):
        text = '''library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity counter is port(clk,rst:in std_logic; led:out std_logic_vector(15 downto 0)); end;
architecture rtl of counter is signal n:unsigned(15 downto 0):=(others=>'0'); begin
process(clk) begin if rising_edge(clk) then if rst='1' then n<=(others=>'0'); else n<=n+1; end if; end if; end process;
led<=std_logic_vector(n); end;'''
        session = live.Session({'files':{'counter.vhd':text},'top':'counter'})
        try:
            before = int(session.initial['wave']['values']['lab_board_tb.io_led'], 2)
            frame = session.advance({'ns':10000})
            after = int(frame['wave']['values']['lab_board_tb.io_led'], 2)
            self.assertEqual((after-before)%65536,1000)
            self.assertEqual(frame['sim_ns'],10000)
            frame = session.advance({'ns':10000})
            final = int(frame['wave']['values']['lab_board_tb.io_led'],2)
            self.assertEqual((final-after)%65536,1000)
            self.assertEqual(frame['sim_ns'],20000)
        finally:
            session.close()

    def test_live_elevator_uses_original_debounce_and_display(self):
        session = live.Session({'files':self.files,'top':'elevator_top'})
        try:
            # Same-floor request: original 20 ms debounce must be respected.
            frame = session.advance({'ns':10000000,'buttons':['btnU']})
            self.assertEqual(frame['wave']['values']['lab_board_tb.io_door'],'0')
            session.advance({'ns':10000000,'buttons':['btnU']})
            frame = session.advance({'ns':1000000,'buttons':['btnU']})
            self.assertEqual(frame['wave']['values']['lab_board_tb.io_door'],'1')
            self.assertEqual(frame['digits'][:2],['1000000','1000000'])
            self.assertIn('NO TIMING OVERRIDES',frame['log'])
        finally:
            session.close()

    def test_live_interactive_uses_real_vhdl_up_down_and_preserves_source(self):
        files = self.files.copy()
        session = live.Session({'files':files, 'top':'elevator_top', 'timing':'interactive'})
        try:
            self.assertEqual(session.initial['time_scale'],10000)
            frame = session.advance({'sw':3,'buttons':['btnU'],'ns':3000})
            self.assertEqual(frame['inputs'],{'sw':3,'buttons':['btnU']})
            # Changing switches while moving must be ignored by the actual FSM.
            frame = session.advance({'sw':15,'ns':300000})
            self.assertEqual(frame['digits'][:2],['0110000','1000000'])
            self.assertEqual(frame['wave']['values']['lab_board_tb.io_door'],'1')
            self.assertEqual(frame['board_ns'],3030000000)
            frame = session.advance({'ns':1000000})
            self.assertEqual(frame['wave']['values']['lab_board_tb.io_door'],'0')
            session.advance({'sw':0,'buttons':['btnU'],'ns':3000})
            frame = session.advance({'sw':0,'ns':300000})
            self.assertEqual(frame['digits'][:2],['1000000','1000000'])
            self.assertEqual(frame['wave']['values']['lab_board_tb.io_door'],'1')
            self.assertIn('COUNTERS SCALED',frame['log'])
            self.assertEqual(files,self.files)
            self.assertIn('100000000',self.files['clk_div.vhd'])
        finally:
            session.close()

    def test_interactive_rejects_unrecognized_timing_profile(self):
        with self.assertRaisesRegex(ValueError,'standard elevator constants'):
            live.Session({'files':{'simple.vhd':'entity simple is end; architecture sim of simple is begin end;'},'top':'simple','timing':'interactive'})


if __name__ == '__main__':
    unittest.main()
