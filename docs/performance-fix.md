# Local performance update: 0.4.8-perf1

Changes made on 2026-10-23:

- Reuse HTTP/1.1 connections for consecutive simulation requests, with TCP_NODELAY for small replies. Retain explicit response lengths, and close connections when rejecting unread request bodies.
- Stop printing every successful observation to the console. Session start/stop and errors remain logged.
- Compact JSON responses and keep the server history in a bounded deque. Incremental frames no longer copy the whole retained history on every request.
- Request Windows interactive HighQoS for the live GHDL child, with a graceful fallback on unsupported systems. No process priority, affinity or system power plan changes. Set `NEXYS_LAB_SYSTEM_QOS=1` to opt out.

The VHDL sources, clock periods, counter constants, reset/input timing, observation interval limits and automatic batch target are unchanged. Testbench execution is unchanged. The existing speed indicator still reports the average since Run, not an instantaneous speed.

## Measurements on this computer

Measurements use real bundled GHDL with a fixed 136,560 ns interval, excluding compilation and browser rendering. Other applications were running, so these are observations rather than controlled CPU benchmarks. Different designs must not be compared as if they had the same execution cost.

| Trial | Duration | Findings |
|---|---:|---|
| Counter before changes | 35 s | 671 connections; median transport overhead in five-second windows about 4.6–11.2 ms. |
| Counter after transport/history changes, default scheduling | 35 s | One connection; overhead about 0.6–2.0 ms. Simulator wait rose from about 42 to 145 ms, so fixing transport alone did not eliminate the observed slowdown in that run. |
| Counter directly through Python, no HTTP; HighQoS enabled at 15 s | 35 s | Wait stayed about 43 ms both before and after the QoS switch. This trial does not establish QoS as the cause of the earlier slowdown. |
| Counter with persistent HTTP and HighQoS | 35 s | One connection; wait about 42–43 ms; throughput about 0.0030–0.0031x throughout. |
| Included elevator with persistent HTTP and HighQoS | 60 s | One connection; wait about 5.0–5.6 ms; throughput fluctuated between 0.0180x and 0.0233x and recovered at the end, with no sustained progressive decline. |

Raw results are saved as `benchmark-before.json`, `benchmark-after.json`, `benchmark-qos.json`, `benchmark-high-qos.json` and `benchmark-elevator.json` in the application directory. Reproduce with `scripts/benchmark_transport.py` as described in README.

These tests establish lower transport overhead and correct operation of the changes. They do not prove that Windows scheduling caused the user's entire slowdown, nor that an unprovided project will maintain its startup throughput. HighQoS is a mitigation for background classification, not a thermal/power-limit override. See [Microsoft's QoS documentation](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessinformation).

## Validation and activation

`runtime/python/python.exe -m unittest discover -v`: **56 tests passed**, including real GHDL clock counts, state continuity across successive advances, fractional clocks, inout resolution, physical display reconstruction, bounded history, reusable HTTP connections, rejected-body connection closure and a real Windows QoS query.

No browser automation was run; frontend files were not changed. The user's own project was not available for reproduction.

Export the current browser project before restarting, particularly if switching ports. Restart the relevant server and refresh the browser; the header should report **0.4.8-perf1**. Previously running Python servers retain the old code until restarted. Original edited application files are backed up in `performance-backup`.
