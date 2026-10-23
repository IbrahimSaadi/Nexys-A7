# Nexys Lab

A VHDL workbench with a photographic Nexys A7 board, general project/port discovery, physical pin mapping from XDC, a live signal inspector and real HDL execution. This is a general RTL simulation interface, not a complete electrical or peripheral emulator of the entire board.

## Windows portable edition

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
