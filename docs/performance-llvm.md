# Native LLVM update: 0.4.8-perf2

Validated locally on 2026-10-24. Python remains the server; GHDL executes the original VHDL using a native LLVM backend and GCC linker. No user VHDL files or example sources were edited.

## Implemented

- Added the official GHDL 6.0.0 LLVM/UCRT64 runtime in `runtime/ghdl-llvm`, alongside the original mcode runtime.
- Compile designs with `-O2`. Launch the compiled live executable directly with `--assert-level=error`, retaining the existing clock/input harness and frame protocol.
- Recompiled the original IEEE `std_logic_1164` and `numeric_std` VHDL-2008 bodies with `-O3`. Their source hashes match the original bundled sources. No fast-math, disabled checks, disabled assertions, synthesis substitutions or clock skipping.
- Pass the private compiler/DLL directory only to child processes. No global PATH, system power plan or installed-toolchain changes.
- Select the native runtime only when its validation marker is installed. Keep explicit `GHDL_PATH` overrides and the compatibility launcher.
- Apply the same native compiler support to the GHDL Testbench path; Vivado is unchanged.

The LLVM-JIT candidate was not selected. It gave a smaller speed improvement and failed one test involving simulation completion. The selected native LLVM backend passed the full suite.

## Identical-work comparison

`scripts/compare_engines.py` replays identical sources, settings, intervals and input sequences against both backends. It compares every sampled output, reconstructed digit, input value and HDL timestamp, verifies the source/configuration hash did not change, and rejects timing overrides. Engine order is alternated across workloads. Compilation is timed separately from execution.

Final raw results: `benchmark-engine-library-O3.json`. Earlier stages: `benchmark-engine-before-library.json` and `benchmark-engine-library-O2.json`.

| Workload | Original execution | Native execution | Speedup | Matching snapshots |
|---|---:|---:|---:|---:|
| 32-bit vector counter, 20 ms HDL | 4.84 s | 2.70 s | 1.79x | 201/201 |
| 128-bit vector counter, 8 ms HDL | 5.43 s | 2.89 s | 1.88x | 81/81 |
| Original elevator, 25 ms HDL | 0.98 s | 0.82 s | 1.19x | 251/251 |

This is a same-machine measurement, with other applications running. It is not a universal speed guarantee. Matching these samples and regression tests is evidence for tested behavior, not a proof of equivalence for every possible VHDL project. Sampling intervals were not enlarged to obtain these gains.

Startup in these trials increased from about 0.14–0.30 s to 0.88–1.45 s. Short testbenches may therefore take longer overall despite faster execution. The compatibility launcher remains available for such workloads or backend-specific issues.

## Verification

- Default/native backend: **58 tests passed**, including assertions/failures, physical bindings, fractional clock edge counts, signed/wide ports, unknown-state/inout resolution, generic widths, display reconstruction, transport, history and backend selection.
- Original mcode backend: **58 tests passed**.
- 533 replayed snapshots/timestamps matched exactly across the two engines.
- Test output: `test-results-default.txt` and `test-results-mcode.txt`.
- Sustained fixed-batch native run: `benchmark-llvm-long.json` (35 seconds, HTTP path, excludes browser rendering).
- In that sustained run, median simulator wait stayed at about 23.0–23.4 ms per identical batch; five-second throughput windows stayed at 0.0054–0.0058x, without a progressive decline. This counter runs continuously enabled, unlike the input-changing comparison above, so its absolute throughput should not be compared directly with that table.
- No browser automation was run. No frontend files were changed in this update.

## Running and reverting

Export the current project before restarting or changing ports. Restart using `Start-Nexys-Lab.cmd`; verify version **0.4.8-perf2** in the header and `llvm 21.1.8 code generator` in Terminal after Run. Previously running servers keep their loaded code until restarted.

Use `Start-Nexys-Lab-Compatible.cmd` for the original engine. Backups of the previous application code are in `performance-backup-perf1`. Both runtime directories are retained.

Reproduce the comparison:

```powershell
.\runtime\python\python.exe scripts/compare_engines.py --candidate runtime/ghdl-llvm/ucrt64/bin/ghdl.exe
.\runtime\python\python.exe scripts/benchmark_transport.py --seconds 35 --qos high
.\runtime\python\python.exe -m unittest discover -v
```

Package URLs/checksums, optimized source/object hashes and runtime provenance are in `third_party/llvm-runtime.json`. GHDL's package SHA256 was verified against the [official release](https://github.com/ghdl/ghdl/releases/tag/v6.0.0). Compiler/linker dependencies came from the [official MSYS2 package repository](https://repo.msys2.org/mingw/ucrt64/); their downloaded hashes are recorded locally. Package license notices are retained under `third_party/llvm-packages` and LLVM's license is in `third_party/LLVM-LICENSE.txt`. The unchanged GHDL source archive was already included in `third_party`.
