import unittest
import server
import live


class ProjectTests(unittest.TestCase):
    def test_xdc_drives_arbitrary_scalar_names_without_an_adapter(self):
        files={'logic.vhd':'''library ieee; use ieee.std_logic_1164.all;
entity logic is port(direction, enable:in std_logic; status:out std_logic); end;
architecture rtl of logic is begin status<=direction xor enable; end;''',
        'board.xdc':'''set_property PACKAGE_PIN J15 [get_ports direction]
set_property PACKAGE_PIN L16 [get_ports enable]
set_property PACKAGE_PIN H17 [get_ports status]'''}
        info=server.inspect_project({'files':files,'top':'logic'})
        self.assertEqual(info['mapping']['direction'],'sw[0]')
        self.assertEqual(info['mapping']['enable'],'sw[1]')
        session=live.Session({'files':files,'top':'logic','mapping':info['mapping'],'board_bindings':info['bindings']['mapping']})
        try:
            for switches,expected in ((0,'0'),(1,'1'),(2,'1'),(3,'0')):
                frame=session.advance({'sw':switches,'ns':10})
                self.assertEqual(frame['board_values']['led[0]'],expected)
        finally:session.close()

    def test_dependent_generics_follow_override_and_nonzero_bounds(self):
        source='''library ieee; use ieee.std_logic_1164.all;
entity wide is generic(W:positive:=8; N:positive:=W*2);
port(a:in std_logic_vector(N+3 downto 4); b:out unsigned(0 to W-1)); end;'''
        ports=server.ports(source,'wide',{'W':64})
        self.assertEqual(ports[0]['width'],128)
        self.assertEqual((ports[0]['left'],ports[0]['right']),(131,4))
        self.assertEqual(ports[1]['type'],'unsigned(0 to 63)')

    def test_wide_ports_are_exposed_and_expression_code_is_not_executed(self):
        source='entity wide is port(a:in std_logic_vector(255 downto 0)); end;'
        self.assertEqual(server.ports(source,'wide')[0]['width'],256)
        with self.assertRaises(ValueError):
            server._integer_expression('__import__("os").system("echo unsafe")',{})

    def test_vcd_timescales_are_normalized_for_multiple_engines(self):
        vcd='$timescale\n1 ps\n$end\n$scope module tb $end\n$var wire 1 ! a $end\n$upscope $end\n$enddefinitions $end\n#10\n1!\n'
        result=server.parse_vcd(vcd)
        self.assertEqual(result['end'],10000)
        self.assertEqual(result['events'][0],[10000,'tb.a','1'])

    def test_split_display_pins_reconstruct_real_vhdl_digit(self):
        segments='0110000'  # Physical gfedcba digit 3.
        names=[f's{i}' for i in range(7)]+[f'd{i}' for i in range(8)]
        source='library ieee; use ieee.std_logic_1164.all; entity splitdisplay is port('+','.join(names)+':out std_logic); end; architecture rtl of splitdisplay is begin '
        source+=' '.join(f"s{i}<='{segments[6-i]}';" for i in range(7))
        source+=' '.join(f"d{i}<='{'0' if i==0 else '1'}';" for i in range(8))+' end;'
        bindings={f's{i}':[{'index':None,'signal':f'segment[{i}]'}] for i in range(7)}
        bindings.update({f'd{i}':[{'index':None,'signal':f'an[{i}]'}] for i in range(8)})
        session=live.Session({'files':{'split.vhd':source},'top':'splitdisplay','board_bindings':bindings})
        try:
            self.assertEqual(session.initial['digits'][0],segments)
            self.assertEqual(session.initial['digits'][1:],['1111111']*7)
            self.assertEqual(session.initial['board_values']['an[0]'],'0')
        finally:session.close()

    def test_fractional_clock_period_executes_exact_edges(self):
        source='''library ieee;use ieee.std_logic_1164.all;use ieee.numeric_std.all;
entity fast is port(timing:in std_logic;n:out std_logic_vector(7 downto 0));end;
architecture rtl of fast is signal count:unsigned(7 downto 0):=(others=>'0');begin
process(timing)begin if rising_edge(timing)then count<=count+1;end if;end process;n<=std_logic_vector(count);end;'''
        session=live.Session({'files':{'fast.vhd':source},'top':'fast','clocks':{'timing':{'period_ns':2.5}}})
        try:
            before=int(session.initial['wave']['values']['lab_board_tb.io_n'],2)
            after=int(session.advance({'ns':100})['wave']['values']['lab_board_tb.io_n'],2)
            self.assertEqual((after-before)%256,40)
        finally:session.close()

    def test_active_low_physical_reset_is_initialized_and_idle_high(self):
        source='''library ieee;use ieee.std_logic_1164.all;
entity resetcheck is port(clk,reset_n:in std_logic;led:out std_logic);end;
architecture rtl of resetcheck is signal state:std_logic;begin
process(clk,reset_n)begin if reset_n='0'then state<='0';elsif rising_edge(clk)then state<=not state;end if;end process;led<=state;end;'''
        session=live.Session({'files':{'reset.vhd':source},'top':'resetcheck','mapping':{'clk':'clock','reset_n':'cpu_resetn'}})
        try:
            self.assertEqual(session.initial['input_values']['reset_n'],'1')
            self.assertEqual(session.initial['wave']['values']['lab_board_tb.io_led'],'0')
        finally:session.close()

    def test_explicit_unknown_pin_does_not_revert_to_a_name_guess(self):
        files={'a.vhd':'library ieee;use ieee.std_logic_1164.all;entity a is port(clk:in std_logic);end;',
               'a.xdc':'set_property PACKAGE_PIN NOT_A_PIN [get_ports clk]'}
        result=server.inspect_project({'files':files,'top':'a'})
        self.assertEqual(result['mapping']['clk'],'zero')
        self.assertIsNone(result['bindings']['mapping']['clk'][0]['signal'])

    def test_utf8_comments_are_preserved_without_locale_write_errors(self):
        source='''-- تعليق عربي في ملف المستخدم
entity utf8_tb is end;architecture test of utf8_tb is begin
process begin report "UTF8_SOURCE_PASSED";wait;end process;end;'''
        result=server.simulate({'files':{'utf8_tb.vhd':source},'top':'utf8_tb','mode':'testbench','duration':'10ns'})
        self.assertTrue(result['ok'],result['log'])
        self.assertIn('UTF8_SOURCE_PASSED',result['log'])


if __name__=='__main__':unittest.main()
