"""Performance options must preserve actual GHDL time, clocks and input behavior."""
import json
import http.client
import threading
import unittest
from unittest.mock import patch
import live
import server

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

    def test_history_overflow_keeps_recent_samples_and_independent_snapshots(self):
        session=live.Session({'files':{'perf.vhd':SOURCE},'top':'perf_test'})
        try:
            # Fill the retained history without spending thousands of pipe round trips.
            seed=session.initial['wave']['events'][0]
            session.history.extend([seed]*3998)
            full=session.advance({'ns':10})
            self.assertEqual(len(full['wave']['events']),4000)
            self.assertFalse(full['wave']['truncated'])
            snapshot=full['wave']['events'][:]
            delta=session.advance({'ns':10,'wave_history':False})
            self.assertTrue(delta['wave']['truncated'])
            self.assertEqual(len(delta['wave']['events']),1)
            self.assertEqual(len(session.history),4000)
            self.assertEqual(full['wave']['events'],snapshot)
            newest=session.advance({'ns':10})
            self.assertEqual(newest['wave']['events'][:-2],snapshot[2:])
            self.assertEqual(newest['wave']['events'][-2],delta['wave']['events'][0])
        finally:session.close()


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.httpd=server.create_server('127.0.0.1',0)
        self.thread=threading.Thread(target=self.httpd.serve_forever,daemon=True)
        self.thread.start()
        self.client=http.client.HTTPConnection(*self.httpd.server_address,timeout=10)

    def tearDown(self):
        self.client.close()
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def post(self,path,data):
        self.client.request('POST',path,json.dumps(data),{'Content-Type':'application/json'})
        response=self.client.getresponse()
        result=json.loads(response.read())
        self.assertEqual(response.status,200,result)
        return result

    def test_live_batches_reuse_connection_preserve_edges_and_avoid_log_flood(self):
        initial=self.post('/api/live/start',{'files':{'perf.vhd':SOURCE},'top':'perf_test','inputs':{'enable':'1'}})
        token=initial['session']
        try:
            connection=self.client.sock
            self.assertIsNotNone(connection)
            before=int(initial['wave']['values']['lab_board_tb.io_q'],2)
            with patch.object(server.Handler,'log_message') as log:
                for index in range(20):
                    frame=self.post('/api/live/advance',{'session':token,'ns':1000,'wave_history':False})
                    self.assertIs(self.client.sock,connection)
                    self.assertEqual(frame['sim_ns'],(index+1)*1000)
                log.assert_not_called()
            self.assertEqual(int(frame['wave']['values']['lab_board_tb.io_q'],2)-before,2000)
            # Static responses and errors also need framing on a reused socket.
            for path,status in [('/pacing.js',200),('/missing-file',404)]:
                self.client.request('GET',path)
                response=self.client.getresponse()
                response.read()
                self.assertEqual(response.status,status)
            self.post('/api/live/advance',{'session':token,'ns':10})
        finally:self.post('/api/live/stop',{'session':token})

    def test_rejected_unread_bodies_close_connection(self):
        for headers,status in [({'Origin':'http://elsewhere'},403),
                               ({'Content-Length':'2000001'},413),
                               ({'Content-Length':'-1'},400),
                               ({'Content-Length':'bad'},400),
                               ({'Transfer-Encoding':'chunked'},400)]:
            with self.subTest(headers=headers):
                self.client.request('POST','/api/live/advance','{}',headers)
                response=self.client.getresponse()
                response.read()
                self.assertEqual(response.status,status)
                self.assertEqual(response.getheader('Connection'),'close')
                self.assertIsNone(self.client.sock)

if __name__=='__main__':unittest.main()
