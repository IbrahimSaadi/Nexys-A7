import time
import unittest

import live
from test_performance import SOURCE


class BackgroundTests(unittest.TestCase):
    def test_handoff_retains_counter_state_and_excludes_manual_driver(self):
        session = live.Session({'files': {'perf.vhd': SOURCE}, 'top': 'perf_test',
                                'inputs': {'enable': '1'}})
        try:
            baseline = int(session.initial['wave']['values']['lab_board_tb.io_q'], 2)
            session.run_background({'maximum_ns': 10000, 'inputs': {'enable': '1'}})
            with self.assertRaisesRegex(ValueError, 'foreground'):
                session.advance({'ns': 10})
            deadline = time.monotonic() + 3
            while session.latest['sim_ns'] < 10000 and time.monotonic() < deadline:
                time.sleep(0.01)
            frame = session.return_foreground()
            self.assertGreaterEqual(frame['sim_ns'], 10000)
            value = int(frame['wave']['values']['lab_board_tb.io_q'], 2)
            self.assertEqual(value - baseline, frame['sim_ns'] / 10)
            self.assertEqual(frame['wave']['mode'], 'history')
            time.sleep(0.03)
            self.assertEqual(session.latest['sim_ns'], frame['sim_ns'])
            stepped = session.advance({'ns': 10, 'debug_step': True})
            self.assertEqual(int(stepped['wave']['values']['lab_board_tb.io_q'], 2), value + 1)
            session.run_background({'maximum_ns': 10000, 'inputs': {'enable': '0'}})
            time.sleep(0.03)
            stopped = session.return_foreground()
            self.assertEqual(int(stopped['wave']['values']['lab_board_tb.io_q'], 2), value + 1)
        finally:
            session.close()

    def test_close_stops_background_runner_and_invalid_options_do_not_claim_session(self):
        session = live.Session({'files': {'perf.vhd': SOURCE}, 'top': 'perf_test'})
        try:
            with self.assertRaises(ValueError):
                session.run_background({'maximum_ns': 3})
            self.assertFalse(session.background_owned)
            session.run_background({'maximum_ns': 10000})
            with session.lock:
                session.close()
            session.background_thread.join(timeout=3)
            self.assertFalse(session.background_thread.is_alive())
        finally:
            if not session.closed:
                session.close()


if __name__ == '__main__':
    unittest.main()
