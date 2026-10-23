"""Performance options must preserve actual GHDL time, clocks and input behavior."""
import json
import unittest
import live

SOURCE='''library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity perf_test is port(clk:in std_logic; enable:in std_logic; q:out std_logic_vector(31 downto 0));end;
architecture rtl of perf_test is signal n:unsigned(31 downto 0):=(others=>'0');begin
process(clk)begin if rising_edge(clk) and enable='1' then n<=n+1;end if;end process;
q<=std_logic_vector(n);end;'''

class PerformanceTests(unittest.TestCase):
    def test_incremental_frames_preserve_clock_edges_and_history(self):
        session=live.Session({'files':{'perf.vhd':SOURCE},'top':'perf_test','inputs':{'enable':'1'}})
        try:
            before=int(session.initial['wave']['values']['lab_board_tb.io_q'],2)
            merged=session.initial['wave']['events'][:]
            for index in range(40):
                frame=session.advance({'ns':1000,'wave_history':False})
                self.assertEqual(frame['wave']['mode'],'delta')
                self.assertEqual(len(frame['wave']['events']),len(session.outputs))
                merged.extend(frame['wave']['events'])
                self.assertEqual(frame['sim_ns'],(index+1)*1000)
                metrics=frame['performance']
                self.assertEqual(metrics['interval_ns'],1000)
                for name in ('simulator_wait_ms','frame_build_ms','backend_ms'):
                    self.assertGreaterEqual(metrics[name],0)
                self.assertGreaterEqual(metrics['backend_ms'],metrics['simulator_wait_ms'])
            self.assertEqual(int(frame['wave']['values']['lab_board_tb.io_q'],2)-before,4000)
            delta_size=len(json.dumps(frame))
            full=session.advance({'ns':1000})
            self.assertEqual(full['wave']['mode'],'history')
            self.assertEqual(full['wave']['events'][:-len(session.outputs)],merged)
            self.assertGreater(len(json.dumps(full)),delta_size*2)
            stopped=session.advance({'ns':1000,'wave_history':False,'inputs':{'enable':'0'}})
            self.assertEqual(stopped['wave']['values'],full['wave']['values'])
            with self.assertRaisesRegex(ValueError,'wave_history'):
                session.advance({'wave_history':'false'})
        finally:session.close()

if __name__=='__main__':unittest.main()
