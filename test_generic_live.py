"""Generic port drives execute in real GHDL, independent of any board example."""
import unittest
import live


class GenericLiveTests(unittest.TestCase):
    def make(self, source, **options):
        return live.Session({'files': {'generic.vhd': source}, 'top': 'generic_design', **options})

    def test_arbitrary_input_names_large_patterns_persist_and_release(self):
        source = '''library ieee; use ieee.std_logic_1164.all;
entity generic_design is port(payload: in std_logic_vector(63 downto 0); flag: in std_logic; result: out std_logic_vector(63 downto 0); observed: out std_logic); end;
architecture rtl of generic_design is begin result<=payload; observed<=flag; end;'''
        s = self.make(source, inputs={'payload': '0xFEDCBA9876543210', 'flag': '1'})
        try:
            self.assertEqual(s.initial['wave']['values']['lab_board_tb.io_result'], format(0xFEDCBA9876543210, '064b'))
            frame = s.advance({'ns': 10, 'inputs': {'PAYLOAD': 2**63+5}})
            self.assertEqual(frame['wave']['values']['lab_board_tb.io_result'], format(2**63+5, '064b'))
            self.assertEqual(frame['input_values']['flag'], '1')
            frame = s.advance({'ns': 10})
            self.assertEqual(frame['wave']['values']['lab_board_tb.io_observed'], '1')
            frame = s.advance({'ns': 10, 'inputs': {'payload': None, 'flag': None}})
            self.assertEqual(frame['wave']['values']['lab_board_tb.io_result'], '0'*64)
            self.assertEqual(frame['wave']['values']['lab_board_tb.io_observed'], '0')
            self.assertEqual(frame['manual_inputs'], {})
        finally:
            s.close()

    def test_independent_scalar_switch_bits_without_wrapper(self):
        source = '''library ieee; use ieee.std_logic_1164.all;
entity generic_design is port(direction, enable:in std_logic; result:out std_logic_vector(1 downto 0)); end;
architecture rtl of generic_design is begin result <= enable & direction; end;'''
        s = self.make(source, mapping={'direction': 'sw[0]', 'enable': 'sw[1]'})
        try:
            for sw, expected in [(0, '00'), (1,'01'), (2,'10'), (3,'11')]:
                frame = s.advance({'ns': 10, 'sw': sw})
                self.assertEqual(frame['wave']['values']['lab_board_tb.io_result'], expected)
        finally:
            s.close()

    def test_unknown_states_and_resolved_bidirectional_bus(self):
        source = '''library ieee; use ieee.std_logic_1164.all;
entity generic_design is port(data_bus:inout std_logic_vector(3 downto 0); probe:in std_logic; copy_probe:out std_logic); end;
architecture rtl of generic_design is begin data_bus <= "10ZZ"; copy_probe <= probe; end;'''
        s = self.make(source)
        try:
            frame = s.advance({'ns': 10, 'inputs': {'data_bus': 'ZZ01', 'probe': 'X'}})
            self.assertEqual(frame['wave']['values']['lab_board_tb.io_data_bus'], '1001')
            self.assertEqual(frame['wave']['values']['lab_board_tb.io_copy_probe'], 'X')
            frame = s.advance({'ns': 10, 'inputs': {'data_bus': '01ZZ'}})
            self.assertEqual(frame['wave']['values']['lab_board_tb.io_data_bus'], 'XXZZ')
            frame = s.advance({'ns': 10, 'inputs': {'data_bus': None}})
            self.assertEqual(frame['wave']['values']['lab_board_tb.io_data_bus'], '10ZZ')
        finally:
            s.close()

    def test_configurable_clock_for_nonstandard_port_name(self):
        source = '''library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity generic_design is port(custom_clock:in std_logic; result:out std_logic_vector(15 downto 0)); end;
architecture rtl of generic_design is signal n:unsigned(15 downto 0):=(others=>'0'); begin
process(custom_clock) begin if rising_edge(custom_clock) then n<=n+1; end if; end process; result<=std_logic_vector(n); end;'''
        s = self.make(source, clocks={'custom_clock': {'period_ns': 40}})
        try:
            before = int(s.initial['wave']['values']['lab_board_tb.io_result'], 2)
            frame = s.advance({'ns': 1000})
            after = int(frame['wave']['values']['lab_board_tb.io_result'], 2)
            self.assertEqual(after-before, 25)
            self.assertEqual(frame['clocks'], {'custom_clock': {'period_ns': 40}})
            with self.assertRaisesRegex(ValueError, 'clock port'):
                s.advance({'ns': 10, 'inputs': {'custom_clock': '1'}})
        finally:
            s.close()

    def test_rejects_invalid_drives_without_corrupting_session(self):
        source = '''library ieee; use ieee.std_logic_1164.all;
entity generic_design is port(payload:in std_logic_vector(3 downto 0); result:out std_logic_vector(3 downto 0)); end;
architecture rtl of generic_design is begin result<=payload; end;'''
        s = self.make(source)
        try:
            for value in ('01', 16, -1, 1.5, 'HELLO'):
                with self.assertRaises(ValueError):
                    s.advance({'ns': 10, 'inputs': {'payload': value}})
            with self.assertRaisesRegex(ValueError, 'output-only'):
                s.advance({'ns': 10, 'inputs': {'result': '0000'}})
            frame = s.advance({'ns': 10, 'inputs': {'payload': 7}})
            self.assertEqual(frame['wave']['values']['lab_board_tb.io_result'], '0111')
        finally:
            s.close()

    def test_numeric_bit_and_unresolved_types_with_overridden_generic(self):
        source = '''library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity generic_design is generic(WIDTH:positive:=4); port(
 a:in unsigned(WIDTH-1 downto 0); s:in signed(WIDTH-1 downto 0);
 bits:in bit_vector(0 to WIDTH-1); flag:in bit; u:in std_ulogic; uv:in std_ulogic_vector(1 to WIDTH);
 sum_out:out unsigned(WIDTH-1 downto 0); s_out:out signed(WIDTH-1 downto 0);
 bits_out:out bit_vector(0 to WIDTH-1); flag_out:out bit; u_out:out std_ulogic; uv_out:out std_ulogic_vector(1 to WIDTH)); end;
architecture rtl of generic_design is begin
 sum_out<=a+1; s_out<=s; bits_out<=bits; flag_out<=flag; u_out<=u; uv_out<=uv; end;'''
        s = self.make(source, generics={'WIDTH':8}, inputs={'a':255,'s':-3,'bits':'10100101','flag':1,'u':'X','uv':'10ZZ0011'})
        try:
            values = s.initial['wave']['values']
            self.assertEqual(values['lab_board_tb.io_sum_out'],'00000000')
            self.assertEqual(values['lab_board_tb.io_s_out'],'11111101')
            self.assertEqual(values['lab_board_tb.io_bits_out'],'10100101')
            self.assertEqual(values['lab_board_tb.io_flag_out'],'1')
            self.assertEqual(values['lab_board_tb.io_u_out'],'X')
            self.assertEqual(values['lab_board_tb.io_uv_out'],'10ZZ0011')
            frame=s.advance({'ns':10,'inputs':{'a':14,'bits':'0x54','flag':0,'s':-128}})
            self.assertEqual(frame['wave']['values']['lab_board_tb.io_sum_out'],'00001111')
            self.assertEqual(frame['wave']['values']['lab_board_tb.io_bits_out'],'01010100')
            self.assertEqual(frame['wave']['values']['lab_board_tb.io_s_out'],'10000000')
            with self.assertRaises(ValueError):
                s.advance({'ns':10,'inputs':{'flag':'X'}})
        finally:
            s.close()

    def test_default_generic_expression_and_wide_vector(self):
        source = '''library ieee; use ieee.std_logic_1164.all;
entity generic_design is generic(WIDTH:positive:=128); port(payload:in std_logic_vector(WIDTH*2-1 downto 0); result:out std_logic_vector(WIDTH*2-1 downto 0)); end;
architecture rtl of generic_design is begin result<=payload; end;'''
        s=self.make(source)
        try:
            bits='10'*128
            frame=s.advance({'ns':10,'inputs':{'payload':bits}})
            self.assertEqual(frame['wave']['values']['lab_board_tb.io_result'],bits)
            self.assertEqual(next(p for p in frame['ports'] if p['name']=='payload')['width'],256)
        finally:
            s.close()


if __name__ == '__main__':
    unittest.main()
