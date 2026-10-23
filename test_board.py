"""Tests for physical pin mapping; no user Tcl is ever executed."""
from pathlib import Path
import unittest

import board


def port(name, width=1, direction='in', left=None, right=None):
    vector = left is not None or width != 1
    if vector:
        left = width-1 if left is None else left
        right = 0 if right is None else right
        kind = 'downto' if left >= right else 'to'
        type_name = f'std_logic_vector({left} {kind} {right})'
    else:
        type_name = 'std_logic'
    return {'name':name,'width':width,'direction':direction,'vector':vector,'type':type_name}


class BoardTests(unittest.TestCase):
    def test_catalog_contains_unique_physical_pins_and_raw_model_limits(self):
        catalog = board.catalog()
        self.assertEqual(len(catalog['pins']),207)
        self.assertEqual(len({p['pin'] for p in catalog['pins']}),207)
        self.assertEqual(board.BY_SIGNAL['clock']['frequency_hz'],100000000)
        self.assertEqual(board.BY_SIGNAL['sw[8]']['iostandard'],'LVCMOS18')
        self.assertEqual(board.BY_SIGNAL['ddr2_dq[15]']['pin'],'T3')
        self.assertEqual(board.BY_SIGNAL['ddr2_dq[15]']['model'],'raw_signal')
        self.assertEqual(board.BY_SIGNAL['xa_p[1]']['kind'],'analog_capable')
        self.assertIn('Raw pins',catalog['limitations'][0])
        catalog['pins'][0]['pin']='edited'
        self.assertNotEqual(board.catalog()['pins'][0]['pin'],'edited')

    def test_counter_independent_switch_bits_and_clock(self):
        text='''set_property -dict {PACKAGE_PIN E3 IOSTANDARD LVCMOS33} [get_ports clk]
set_property PACKAGE_PIN J15 [get_ports {crt}]
set_property PACKAGE_PIN {L16} [get_ports ena_sw]
create_clock -name sys_clk -period 10.000 -waveform {0 5} [get_ports clk]
'''
        result=board.suggest_mapping([port('clk'),port('crt'),port('ena_sw')],{'counter.xdc':text})
        self.assertEqual(result['mapping']['clk'][0]['signal'],'clock')
        self.assertEqual(result['mapping']['crt'][0]['signal'],'sw[0]')
        self.assertEqual(result['mapping']['ena_sw'][0]['signal'],'sw[1]')
        self.assertEqual(result['clocks'],{'clk':10.0})
        self.assertEqual(result['warnings'],[])

    def test_all_24_elevator_pin_mappings(self):
        files={'elevator.xdc':(Path(__file__).parent/'examples/elevator/elevator_nexys4ddr.xdc').read_text()}
        ports=[port('clk'),port('rst'),port('go'),port('dest_floor',4),
               port('segment',7,'out'),port('an',8,'out'),port('dp',direction='out'),port('door',direction='out')]
        result=board.suggest_mapping(ports,files)
        bits=[bit for values in result['mapping'].values() for bit in values]
        self.assertEqual(len(bits),24)
        self.assertTrue(all(b['source']=='xdc' and b['signal'] for b in bits))
        self.assertEqual(result['warnings'],[])
        self.assertEqual(result['unmatched_constraints'],[])
        self.assertEqual(result['mapping']['rst'][0]['signal'],'btnC')
        self.assertEqual(result['mapping']['go'][0]['signal'],'btnU')
        self.assertEqual(result['mapping']['door'][0]['signal'],'led[0]')
        self.assertEqual([b['signal'] for b in result['mapping']['segment']],
                         [f'segment[{i}]' for i in range(6,-1,-1)])

    def test_comments_disabled_lines_and_multiline_constraints(self):
        text='''# set_property PACKAGE_PIN E3 [get_ports not_active]
set_property -dict { IOSTANDARD LVCMOS33 \\
PACKAGE_PIN J15 } \\
[get_ports {switch_input}]; # trailing comment
set_property PACKAGE_PIN "L16" [get_ports second]
'''
        result=board.parse_xdc(text)
        self.assertEqual(result['pins'],{'switch_input':'J15','second':'L16'})
        self.assertEqual(result['warnings'],[])

    def test_substitution_and_wildcards_are_not_executed_or_mapped(self):
        marker=Path(__file__).parent/'.local'/'xdc-must-not-execute'
        text=f'''set_property PACKAGE_PIN [exec touch {marker}] [get_ports danger]
set_property PACKAGE_PIN J15 [get_ports $port_variable]
set_property PACKAGE_PIN L16 [get_ports {{sw[*]}}]
exec touch {marker}
'''
        result=board.parse_xdc(text)
        self.assertEqual(result['pins'],{})
        self.assertTrue(any('port_variable' in message for message in result['warnings']))
        self.assertTrue(any('sw[*]' in message for message in result['warnings']))
        self.assertIn('danger',result['conflicts'])
        self.assertFalse(marker.exists())

    def test_conflicts_remain_unresolved_instead_of_name_fallback(self):
        text='''set_property PACKAGE_PIN J15 [get_ports SW0]
set_property PACKAGE_PIN L16 [get_ports sw0]
set_property PACKAGE_PIN M13 [get_ports SW0]
'''
        result=board.suggest_mapping([port('SW0')],{'conflict.xdc':text})
        self.assertIsNone(result['mapping']['SW0'][0]['signal'])
        self.assertTrue(result['warnings'])
        result=board.suggest_mapping([port('clk')],{'a.xdc':'create_clock -period 10 [get_ports clk]',
            'b.xdc':'create_clock -period 20 [get_ports clk]', 'c.xdc':'create_clock -period 10 [get_ports clk]'})
        self.assertEqual(result['clocks'],{})
        parsed=board.parse_xdc('create_clock -period 10 [get_ports CLK]; create_clock -period 20 [get_ports clk]; create_clock -period 10 [get_ports CLK]')
        self.assertEqual(parsed['clocks'],{})
        self.assertEqual(parsed['clock_conflicts'],['clk'])

    def test_ascending_nonzero_vectors_keep_physical_bit_indices(self):
        result=board.suggest_mapping([port('data',4,left=4,right=7)],{'pins.xdc':
            '\n'.join(f'set_property PACKAGE_PIN {pin} [get_ports {{data[{index}]}}]' for index,pin in [(4,'J15'),(5,'L16'),(6,'M13'),(7,'R15')])})
        bits=result['mapping']['data']
        self.assertEqual([b['index'] for b in bits],[4,5,6,7])
        self.assertEqual([b['signal'] for b in bits],['sw[0]','sw[1]','sw[2]','sw[3]'])

    def test_unknown_pin_never_falls_back_to_a_known_name(self):
        result=board.suggest_mapping([port('clk')],{'pins.xdc':'set_property PACKAGE_PIN Z99 [get_ports clk]'})
        bit=result['mapping']['clk'][0]
        self.assertIsNone(bit['signal'])
        self.assertEqual(bit['pin'],'Z99')
        self.assertEqual(bit['source'],'xdc')
        self.assertTrue(result['warnings'])

    def test_named_ports_without_xdc_are_conservative(self):
        result=board.suggest_mapping([port('sw',16),port('LED0',direction='out'),port('mystery')],{})
        self.assertEqual(result['mapping']['sw'][0]['signal'],'sw[15]')
        self.assertEqual(result['mapping']['LED0'][0]['signal'],'led[0]')
        self.assertIsNone(result['mapping']['mystery'][0]['signal'])

    def test_fixed_board_direction_conflict_is_reported(self):
        result=board.suggest_mapping([port('oops',direction='out')],{'pins.xdc':'set_property PACKAGE_PIN J15 [get_ports oops]'})
        self.assertEqual(result['mapping']['oops'][0]['signal'],'sw[0]')
        self.assertIn('disagrees',result['warnings'][0])


if __name__=='__main__':
    unittest.main()
