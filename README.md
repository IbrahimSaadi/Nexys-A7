# Nexys Lab

A VHDL workbench with a photographic Nexys A7 board, general project/port discovery, physical pin mapping from XDC, a live signal inspector and real HDL execution. This is a general RTL simulation interface, not a complete electrical or peripheral emulator of the entire board.

## Windows portable edition

**App window:** run `Start-Nexys-Lab-App.cmd` for an independent window without browser tabs. This launcher uses installed Microsoft Edge in app mode with an isolated Nexys Lab profile; it is not a separately bundled native WebView application. Python and GHDL stay in local processes. Closing the app window shuts down its backend and simulation sessions. Port 8765 is reserved for this launcher so saved projects keep the same origin between launches; a second instance reports that the port is occupied.

Before moving an existing browser project into the app, use **Export project**, then **Import files** in the app to import that JSON. The app profile is separate from ordinary browser storage. The original browser and Compatible launchers remain available.

**Background simulation (perf3):** a running Board session transfers its advance loop to the Python server when the page becomes hidden, once any queued minimum button holds have completed. The server continues the same GHDL process with the current inputs and configured clocks. Returning to the page waits for the current batch, retrieves the bounded history and returns control to the UI. Paused sessions stay paused. This also works in ordinary browser mode after restarting the updated server. One unattended background run is capped at one hour; normal session cleanup then applies if the client never returns. Downloaded live traces still contain samples, not all internal transitions.

Download **Nexys-Lab-Windows-x64.zip** from [GitHub Releases](https://github.com/IbrahimSaadi/Nexys-A7/releases/latest), extract the entire archive to a writable folder and double-click **Start-Nexys-Lab.cmd**. Python and GHDL are bundled. No installation, PATH edits, administrator privileges or Internet connection are needed for the GHDL workflow. Windows10/11 x64 (Intel/AMD) is the supported portable target.

The launcher opens a fresh browser tab and chooses a free port if an old server is running. Keep its console window open; Ctrl+C stops it. The header shows the version. Code → Download ZIP is the source edition, without the runtimes. Browser-local projects belong to the current address/port: export your edits before changing ports/versions, then import the JSON.

## Run your own project

1. A fresh workspace starts empty. Export the current project if you need a backup, then choose **New project**. The optional **Load example project** action imports sample source files.
2. Import your VHDL source files and XDC together. Entity discovery selects a likely top; choose the correct **Top entity** if necessary.
3. Click **Inspect project / XDC**. Inputs/outputs appear in **Signals**, and physical connections appear in **Board pins**. No project-specific wrapper is required for supported top-port types.
4. Set integer Generic values as JSON, for example `{"WIDTH":128}`, and inspect again. Configure any clock in the corresponding Signals row. Run restarts the design to apply clock/generic changes.
5. Press **Run**. The app uses source-defined timing without automatic constant overrides. Board switches/buttons drive matching XDC-bound pins; other inputs are editable in Signals. Outputs and resolved inout buses show their actual simulated values.

The uploaded counter design with `crt` and `ena_sw` can use top `main` directly: its XDC maps `crt` to SW0 and `ena_sw` to SW1 independently. The app does not need to know the names or behavior of that counter. The included elevator is now an example, not a requirement of the simulation engine.

Imports add files to the current project; New project avoids accidentally mixing old and new designs with duplicate entity names. Export project saves all project files and simulation settings as JSON. Source edits persist in browser localStorage, not server example files; they are not automatically committed to Git.

## Editor and diagnostics

### Waveforms and paused debugging

Pause a running Board session, then use **Step time** to advance by 1–10,000,000 integer nanoseconds, or select a clock and press **One cycle** to advance by its period. All configured clocks continue during that interval. Cycle stepping supports integer-nanosecond periods; fractional periods remain supported by continuous simulation. The controls wait for any in-flight advance before enabling a step. Changes to switches or raw Signals inputs apply on the next advance. Board button presses retain their existing 30 ms minimum hold in simulated time.

**Waveforms** provides Fit, zoom, pan, signal selection/search, and binary, hexadecimal, unsigned or signed values (including wide buses). Select cursor A or B and click a waveform to inspect the value at that time and measure the time difference. Internal signals recorded by Testbench VCD are selectable alongside ports and clocks. Not every VHDL type is representable in VCD. The preview retains up to 20,000 events; download the original Testbench VCD for the complete recording.

Live Board traces contain sampled top-level outputs, not internal events. Their timestamps include the 200 ns startup; the board's HDL elapsed-time counter excludes it. Earlier values removed by the bounded history are shown as unknown until the next retained event. Zooming cannot recover transitions between live samples. Drag the separator above the results panel upward for more waveform space.

Problems includes nearby source lines and rule-based suggested checks for common syntax, declaration, type, size, library, binding and runtime errors. Suggestions are advisory and do not modify source. Unrecognized diagnostics retain the compiler message without an invented fix. Compiler checks run when you press Run, not while typing.

VHDL sources are colored locally as you type: keywords, types, comments, numbers, strings and operators. The editor retains native text selection, copy/paste, tab insertion and scrolling. Non-VHDL files are shown as plain text; highlighting does not validate a design.

Press Run to compile and simulate. **Problems** displays errors, warnings and notes from GHDL or Vivado XSim, with severity/category filters. Categories include syntax, names, types/sizes, libraries, binding, runtime, assertions, tool setup and general messages. Classification is inferred from diagnostic text, so unfamiliar messages may remain General. Terminal retains the exact simulator output.

Click a file location in Problems to open its project source at the reported line/column. A colored line number marks the diagnostic; generated or external files are identified without opening unrelated files. Editing or resetting clears prior diagnostics so they are not presented as results for changed code. Errors are checked on Run, not continuously while typing. No errors reported is not a guarantee of functional correctness; use a testbench with assertions.

## General signal interface

The live adapter supports `std_logic`, `std_ulogic`, `bit`, their vector forms, `signed` and `unsigned`, with scalar or resolved numeric/generic widths up to4096 bits. Ascending and nonzero vector bounds are supported. Integer generic defaults can use arithmetic and other integer generics. More complex records, custom/unconstrained types or package-derived bounds require a user testbench or a dedicated top-port adapter; the app reports this rather than guessing.

Signals supports exact binary/hex values, large integers without JavaScript precision loss, signed integers through the API, nine-state logic, and `inout` external drive/release with real VHDL resolution. Z releases a resolved bus; conflicting drivers produce X. Manual values persist. Changing a board control releases a conflicting manual override on that bound port. Clock-generated inputs cannot simultaneously be driven manually.

Clock periods can be integer or fractional nanoseconds, down to the simulator's two-femtosecond full-period grid; the default mapped Nexys oscillator is100MHz/10ns. Every HDL clock event still executes. The live sampling interval is independently configurable from10ns to10ms in multiples of10ns: it affects observation/input-update frequency, not the clock period. Fast serial/video signals can be missed by coarse samples. Use a self-checking testbench and full VCD for precise protocol analysis.

Reset startup pulses bound BTNC high and CPU_RESETN low for100ns, then restores their initial drive. Dedicated CPU RESETN is also available as a control. Buttons generate a minimum30ms board-time press; input delivery is acknowledged without claiming the DUT accepted the command. Pause/Resume preserves state and does not catch up paused wall time.

## Pin catalog and device models

The catalog contains207 unique fabric signal pins from official Digilent master-XDC and DDR2 MIG data. It distinguishes digital pins, analog-capable pins, fixed/configurable directions and connection conflicts. XDC parsing accepts literal PACKAGE_PIN/-dict and create_clock forms only; it does not execute Tcl. Dynamic constraints, unknown pins, pin conflicts and direction mismatches are reported. Power, ground and dedicated configuration/JTAG connections are not ordinary fabric ports.

| Board interface | Current support |
|---|---|
|16 switches,5 directional/center buttons, CPU reset | Interactive digital input controls mapped through XDC |
|16 LEDs and2 RGB LEDs | Actual output levels displayed |
|8-digit seven-segment display | Settled multiplexed segments/anodes reconstructed inside VHDL, including split/renamed ports |
|Pmod, UART, VGA, PS/2, SPI/I2C, sensors | Raw mapped digital input/output/inout access and waveform observation |
|DDR2, Ethernet, USB/HID, SD, flash | Pin visibility and raw digital signal access; **no complete external-device behavioral model** |
|XADC analog-capable pins | Digital-level access only; **no voltage/analog conversion model** |

A visible connector or mapped DDR bus does not create a working device. In particular this release does not provide a UART terminal, VGA raster monitor, USB host/keyboard behavior, DDR memory contents or autonomous sensor replies. Such devices need their own protocol models/testbenches. The catalog labels those groups RAW, not simulated hardware. Digit decimal-point output is observed as a raw signal and is not yet reconstructed per digit.

The default board background uses the same manufacturer product photograph as the user's reference, at higher resolution with slightly different margins. Board photo restores it, Vector view chooses a drawing and Your photo imports a local front-facing600×550 reference. The original photograph pixels are not altered; HTML overlays provide live controls. See [photo source](third_party/PHOTO-SOURCE.md) and [hardware references](docs/board-reference.md).

## Clock time versus wall time

The interface always preserves source timing constants and configured clock periods. Exact HDL time does not guarantee real-time CPU execution. A 100 MHz divider taking 100 million cycles can run much slower than one wall second. HDL time, active wall time and measured speed are shown separately.

There is no application-specific timing selector. Previously saved or imported `interactive` timing settings are ignored by the interface; projects run with original timing. For quicker experiments, choose appropriate generics, clocks or explicit testbench stimulus in your project. The legacy scaled profile remains available only to direct API callers for compatibility.

Board instructions use physical control names (BTNU, BTNC, SW0, LED0) and inspected signal names. The interface does not infer a floor, door, GO action or any other application meaning. Creating a new project clears the previous signal inspection, bindings, output history and control state.

## Performance measurements and batching

The local **0.4.8-perf2** update prefers the validated bundled LLVM native backend. User designs compile with `-O2`; the unchanged VHDL-2008 `std_logic_1164` and `numeric_std` package bodies were rebuilt with `-O3`. Bounds checks, assertions, nine-state logic and all HDL clock events remain enabled. No timing constants are overridden. The native simulator is launched directly, so interactive Windows scheduling applies to the process executing the design.

This increases compilation/startup time (roughly 1–2 seconds for the measured examples) in exchange for faster sustained simulation. In the local comparison, execution was about 1.8–1.9 times faster for two vector counters and 1.2 times faster for the elevator. All 533 observed states/timestamps matched the original engine. These results depend on the project and computer; they do not imply real-time simulation. See [measurements and validation](docs/performance-llvm.md).

`Start-Nexys-Lab.cmd` selects LLVM when its validated runtime is present. `Start-Nexys-Lab-Compatible.cmd` uses the original mcode engine. Both use the same project format. Export your project before switching server ports. For direct Python launches, `NEXYS_LAB_GHDL_BACKEND=auto|mcode|llvm` controls selection; an explicit `GHDL_PATH` takes precedence. The original runtime remains installed. Full backend details are printed in the simulation Terminal.

Signals → **LIVE BATCHING** defaults to Auto. It begins with a small probe and adjusts each observation batch toward roughly 20 ms of simulator waiting, bounded by **MAX SAMPLE INTERVAL** (10 ns–10 ms). Fixed mode retains a constant observation interval. Button release boundaries can shorten a batch in either mode. These controls never change the HDL clock period, source constants or scheduled events. Larger observation intervals can miss brief signal changes; Testbench VCD remains the option for complete waveform analysis.

The live performance readout separates simulator waiting (including process communication), Python frame construction, approximate HTTP/JSON overhead and JavaScript UI update time. It also displays lag behind active wall time; pauses are excluded. These are elapsed-time measurements, not CPU profiling or hard real-time guarantees.

The speed readout separates **recent** throughput (approximately the last five active seconds) from the **session average**. Performance details also show time between requests, including browser scheduling and client work. A similar batch size and simulator wait time do not by themselves prove that total throughput is steady. Completed batches proceed directly to the next asynchronous request when HDL time is behind wall time; explicit pacing still applies when ahead. Pausing continues to exclude paused time from the speed calculation.

The browser receives new samples instead of the entire repeated history, retaining the latest 4,000 events locally for sampled waveforms/export. Board rendering is limited to about 30 updates per second, and hidden signal/waveform panels update when opened. Simulation requests continue independently and wait if HDL time gets ahead of active wall time. A slow design still runs slower than hardware; batching cannot remove its event-processing cost.

The local server reuses HTTP/1.1 connections and disables TCP buffering delays for small replies. Successful live-advance requests are not printed to the console; failures and session start/stop requests still are. The server keeps its sampled history in a bounded queue without copying all 4,000 entries on every incremental response.

On supported Windows versions, each live GHDL process requests interactive HighQoS to avoid automatic background execution-speed throttling. This does not change the system power plan, CPU affinity, process priority class, clocks or VHDL source. Windows still controls thermal and power limits. This may use more battery than background throttling; set `NEXYS_LAB_SYSTEM_QOS=1` before launching to retain Windows-managed QoS. Unsupported systems retain their defaults. See [Microsoft's process QoS documentation](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessinformation).

For a fixed-batch comparison, run `runtime/python/python.exe scripts/benchmark_transport.py --seconds 35 --qos high`. Add `--transport direct` to exclude HTTP, or `--project elevator` to use the included elevator. The default counter has a 100 MHz clock; the interval stays fixed at 136,560 ns. Every five seconds the script reports throughput, median simulator wait, frame construction and transport time. Compilation and browser rendering are excluded. Use `--qos default` for Windows-managed scheduling or `--qos switch` to switch the same process to HighQoS after 15 seconds. These measurements do not guarantee real-time simulation or isolate thermal/load effects.

## Testbench engines

**GHDL** runs continuous Board mode and Testbench mode. The included elevator `tb_fsm` with duration2us must report ALL FSM TESTS PASSED. Testbench mode compiles the selected project, applies generic overrides, honors the stop time, detects assertion failures and exports a full VCD. A successful stop-time run alone is not proof of correctness.

**Vivado XSim** is an optional **Testbench-only** bridge to an existing local Vivado installation. The app detects xvhdl/xelab/xsim through VIVADO_PATH, XILINX_VIVADO, PATH or common Windows install locations. In Signals, enter the installation folder if detection fails, then **Detect engines** and **Test Vivado**. The latter compiles/runs a four-clock-edge assertion test on your actual installation and prints the exact log.

Select Testbench mode and the Vivado XSim engine to compile VHDL2008 with the installed unisim/unimacro/secureip libraries and export a VCD. Vivado itself, generated IP simulation files, licenses and any additional libraries are supplied by your existing installation/project, not bundled by this app. XCI/XPR import, encrypted-IP project generation and live-board XSim interaction are not implemented. String-generic cases outside the bridge's validated literal arguments need a source testbench wrapper.

**Validation limit:** the XSim bridge's discovery, command validation, failure reporting and VCD handling have automated tests, but a real Vivado installation is not available in the cloud build machine. Its real execution must be verified using Test Vivado on the user's computer. Native Windows release tests use the bundled GHDL, not a claimed Vivado installation.

On Windows, select the installation root (for example `F:\Xilinx\Vivado\2018.2`) or its `bin` folder. Nexys Lab uses the public `xvhdl.bat`, `xelab.bat` and `xsim.bat` launchers so Vivado can set its DLL search paths. Paths into `bin\unwrapped\win64.o` are redirected to those launchers. A missing-DLL dialog such as `libboost_filesystem.dll` can result from running an internal executable directly; use the launchers first. If the same error occurs through the launchers, check or repair the Vivado installation.

Live Board waveforms are sampled outputs, exported as live-samples.vcd; they do not contain every internal or100MHz signal event. Use Testbench mode for full clock-resolution VCD analysis. Both engines' VCD timescales are normalized for the preview.

## Source setup and validation

Requires Python3.10+ and a VHDL2008 GHDL installation. The app needs no Python/npm packages to run.

```sh
cd /workspace/Nexys-A7
. /workspace/.nexys-tools/activate.sh
python3 server.py --auto-port --open-browser
python3 -m unittest discover -v
```

On a separate Debian/Ubuntu computer install Python and GHDL with its package manager. On Windows, source-edition users can set the full simulator executable path; portable-edition users do not need this:

```powershell
$env:GHDL_PATH = 'C:\Tools\ghdl\bin\ghdl.exe'
py server.py --auto-port --open-browser
```

Only execute trusted HDL. Native compiler/simulator execution and VHDL file I/O are not security-sandboxed. This local app is not a public multi-user hosting service. Up to four live sessions run concurrently; idle sessions close after two minutes without requests. A live interval that takes more than30seconds stops its session. No bitstream generation or physical-board programming is included.

With Playwright installed as a development-only tool, scripts/check_interaction.cjs checks the real elevator and scripts/check_generic.cjs imports a different project through the UI, changes generic widths/clocks, drives128-bit data, resolves an inout bus and checks XDC controls/RGB/catalog. Set NEXYS_LAB_URL to the running local app. These tests never replace GHDL outputs with a JavaScript model.

## Portable release build

```sh
python3 scripts/build_windows.py
```

The builder verifies pinned official GHDL and CPython downloads, includes license notices and GHDL source, and writes the Windows ZIP plus SHA256 under dist/. Binary runtimes do not enter Git. GitHub Actions runs all unit/integration tests using the bundled Windows executables and both real browser regressions before publishing a v* release. Vivado is installed separately and never redistributed in the ZIP.

### Building the portable release

The default `python scripts/build_windows.py` bundles the original mcode runtime. To include an already validated native LLVM installation, use `--llvm-runtime path/to/ghdl-llvm` (containing `READY` and `ucrt64`). Runtime binaries and downloaded archives are excluded from Git. The source upload does not replace existing GitHub Release ZIP files.
