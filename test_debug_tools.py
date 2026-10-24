import unittest
import live
import server
from test_performance import SOURCE


class DebugToolsTests(unittest.TestCase):
    def test_single_cycle_and_small_steps_preserve_clock_counts(self):
        session = live.Session({'files': {'perf.vhd': SOURCE}, 'top': 'perf_test',
                                'inputs': {'enable': '1'}, 'clocks': {'clk': {'period_ns': 10}}})
        try:
            value = lambda frame: int(frame['wave']['values']['lab_board_tb.io_q'], 2)
            initial = value(session.initial)
            for index in range(3):
                frame = session.advance({'ns': 10, 'debug_step': True})
                self.assertEqual(value(frame), initial + index + 1)
                self.assertEqual(frame['sim_ns'], (index + 1) * 10)
            for _ in range(10):
                frame = session.advance({'ns': 1, 'debug_step': True})
            self.assertEqual(frame['sim_ns'], 40)
            self.assertEqual(value(frame), initial + 4)
            frame = session.advance({'ns': 10, 'debug_step': True, 'inputs': {'enable': '0'}})
            self.assertEqual(value(frame), initial + 4)
            self.assertEqual(frame['wave']['capture'], 'sampled')
            for duration in [0, -1, 10000001, 1.5, True]:
                with self.assertRaises(ValueError):
                    session.advance({'ns': duration, 'debug_step': True})
            with self.assertRaises(ValueError):
                session.advance({'ns': 1})
        finally:
            session.close()

    def test_vcd_exposes_internal_signals_and_clock_edges(self):
        text = '''$timescale 1 ns $end
$scope module tb $end
$var wire 1 ! clk $end
$scope module dut $end
$var wire 4 # counter $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
0!
b0000 #
#5
1!
b0001 #
'''
        wave = server.parse_vcd(text)
        self.assertEqual(wave['capture'], 'vcd')
        self.assertIn([5000000, 'tb.clk', '1'], wave['events'])
        self.assertIn([5000000, 'tb.dut.counter', '0001'], wave['events'])


if __name__ == '__main__':
    unittest.main()
