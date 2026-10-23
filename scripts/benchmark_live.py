"""Compare sampled-response volume: run with --history, then without it. No source scaling."""
import sys,time,json,statistics
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import live
ports=';'.join(f'q{i}: out std_logic_vector(31 downto 0)' for i in range(16))
source=f'''library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity perf_probe is port(clk:in std_logic; {ports});end;
architecture rtl of perf_probe is signal n:unsigned(31 downto 0):=(others=>'0');begin
process(clk)begin if rising_edge(clk)then n<=n+1;end if;end process;
'''+''.join(f'q{i}<=std_logic_vector(n);' for i in range(16))+'end;'
s=live.Session({'files':{'probe.vhd':source},'top':'perf_probe'})
sizes=[];durations=[]
try:
 before=int(s.initial['wave']['values']['lab_board_tb.io_q0'],2)
 for i in range(60):
  start=time.perf_counter();frame=s.advance({'ns':100000,'wave_history':'--history' in sys.argv});durations.append((time.perf_counter()-start)*1000);sizes.append(len(json.dumps(frame)))
 after=int(frame['wave']['values']['lab_board_tb.io_q0'],2)
 print(json.dumps({'frames':60,'hdl_ns':frame['sim_ns'],'count_delta':after-before,'mean_advance_ms':statistics.mean(durations),'mean_response_bytes':statistics.mean(sizes),'last_response_bytes':sizes[-1],'total_response_bytes':sum(sizes)}))
finally:s.close()
