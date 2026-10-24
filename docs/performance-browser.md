# Browser scheduling and sustained throughput

The reported screenshots showed similar batch sizes (812,280 and 856,770 ns) and simulator waits (19.4 and 19.9 ms), despite a lower lifetime average. Those snapshots do not establish the cause of the intervening slowdown.

Changes:

- Start the next asynchronous advance directly when simulation is behind wall time, avoiding an additional zero-delay timer. At most one continuous advance is in flight; pause, stop and manual step checks remain in place.
- Show a rolling five-active-second speed alongside the lifetime average. Measure client work and scheduling time between requests. Reset the recent window on pause/resume.
- Avoid repeating step-control DOM writes during ordinary running.
- Skip rebuilding multiplexed display values from sampled history when the backend already supplies eight valid digit values. Keep the fallback for other frames.
- Rebuild waveform signal choices only when their names change, preserving user selection and search.

Validation:

- 11 JavaScript tests passed, including rolling throughput, wide values, and rendering authoritative digits without reading historical events.
- A 300.84-second Chrome headless run of the bundled elevator completed. Final recent speed was 0.0196x and lifetime speed 0.0202x. Pause, exact 1 ns stepping, waveform rendering, cursors and stop then passed. Data: `benchmark-browser-pacing.json`.
- The final display-history and signal-list optimizations were added while the long-run page was already loaded. They were checked afterward with unit tests and a fresh Edge browser smoke run, which passed.
- Some earlier extended Edge headless runs stalled or canceled fetches (`net::ERR_ABORTED`) and failed. This was not reproduced in the completed Chrome run; its cause is not established. Do not interpret these results as a guarantee that every browser or project is fixed.

The browser harness uses an isolated profile and background-throttling suppression flags for controlled testing. It does not change the user's browser configuration. Existing sessions and user projects were not closed or modified. No HDL timing or clock changes were introduced.
