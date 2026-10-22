"""Integration tests executing the real simulator, including UI board bindings."""
from pathlib import Path
import unittest
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


if __name__ == '__main__':
    unittest.main()
