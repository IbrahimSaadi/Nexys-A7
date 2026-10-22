# Nexys Lab

A local VHDL development lab: multi-file editor, real GHDL execution, an interactive Nexys A7 style board, signal preview, and VCD export. Includes the supplied 16-floor elevator project without source changes.

## Start

Requires Python 3.10+ and GHDL with VHDL-2008 support. In the prepared cloud environment:

```sh
cd /workspace/Nexys-A7
. /workspace/.nexys-tools/activate.sh
python3 server.py
```

On your own Debian/Ubuntu computer, install `python3` and `ghdl` using the system package manager, then run `python3 server.py` from this folder. Open the local server on port 8000 in your browser. The default listener is loopback only. No Python or npm packages are needed.

This server runs user HDL using a native compiler. Use it for your own trusted projects. It is not a multi-user hosting service or a security sandbox; do not expose it to the public Internet. Runs use disposable build directories and a 25-second subprocess timeout. VHDL file I/O is not sandboxed.

## Windows

`[WinError 2] The system cannot find the file specified` when pressing Run usually means the GHDL executable cannot be found. Python alone is not enough to simulate VHDL.

1. Install Python 3.10+ and download the appropriate Windows GHDL build from [official GHDL releases](https://github.com/ghdl/ghdl/releases). Choose a native Windows build matching your computer; a Linux archive cannot run on Windows. Extract the **entire** archive so its libraries and DLLs stay together.
2. Add the folder containing `ghdl.exe` to your user `PATH`, then open a new PowerShell window. Check `ghdl --version`.
3. Alternatively, set the executable explicitly in the same PowerShell window that starts the app (replace the example path with your actual extracted path):

```powershell
$env:GHDL_PATH = 'C:\Tools\ghdl\bin\ghdl.exe'
& $env:GHDL_PATH --version
py server.py
```

Run from the folder containing `server.py`. Open the local server on port 8000 in a browser. `GHDL_PATH` accepts either the executable or its containing directory and supports paths with spaces. The variable shown above lasts for this PowerShell session. Restart an already-running server after updating its environment. If GHDL is missing or cannot start, the app's Terminal and server startup now show a setup error instead of a raw WinError.

## Elevator

1. Load the elevator example; choose **Interactive board**, top `elevator_top`.
2. Run once to initialize. Set SW3–SW0 to the destination in binary.
3. Click the Up button (GO), then **Advance 1 tick** for each floor.
4. The actual VHDL drives the multiplexed display and door LED. At arrival the door stays open for ten ticks.
5. To run the original assertions, select **Testbench**, top `tb_fsm`, duration `2us`, then Run.

Board interactions replay the command history from reset in GHDL. They are discrete simulation actions, not a continuously running FPGA. Changing switches takes effect at the next board action. Reset session clears simulation history. Each button click is a simulated press and release.

### Accelerated timing

The elevator uses 100 MHz and a 100-million-cycle second. Interactive board mode defaults to temporary build-copy overrides of `DIVISOR=1000`, `DEBOUNCE_CYCLES=20`, `SCAN_DIV=5`, giving a logical one-second tick in 10 microseconds. The terminal lists every applied override. Project/editor source files are never modified by this feature. Testbench mode never applies overrides. Disable acceleration for original constants; long hardware-time runs may hit the timeout.

Other designs are not automatically accelerated unless they use these exact constant names. Advance 1 tick means a 10-microsecond wait when accelerated, or a one-second wait otherwise, plus a 300-nanosecond settling interval. This does not guarantee a clock-enable pulse in an arbitrary future design.

## Future VHDL projects

- Import `.vhd`, `.vhdl`, `.xdc`, `.txt`, or an exported project JSON. Create, edit, and remove files in the explorer.
- Source edits persist in this browser's local storage; **Export project** makes a portable JSON backup. They do not overwrite server example files or automatically commit to Git.
- **Testbench mode** compiles the project and runs the selected entity until the configured duration or HDL termination. HDL assertions determine failures; a simulation that stops at its time limit is not proof of correctness. Use self-checking testbenches.
- **Board mode** discovers scalar `std_logic` and numeric fixed-width `std_logic_vector` top-level ports. The Port mapping tab binds input ports to the clock, switches, or buttons, and output ports to LEDs, segment, anodes, decimal point, or door. `sw` uses the least significant bits for narrow vectors. Unmapped inputs are zero. Generic-dependent widths, custom types, external libraries, and advanced interfaces require Testbench mode or a future adapter.
- Active-low `segment(6 downto 0)` uses `gfedcba`; active-low `an(7 downto 0)` selects digits. The display is reconstructed from actual multiplexed signal transitions. Decimal-point output is available in waveforms; it is not currently rendered on the board.
- **Waveforms** provides a compact transition preview. Download VCD for full analysis in a waveform viewer. Preview retains the latest 20,000 non-clock transitions and up to 28 signals.
- `.xdc` files are retained for export and future hardware work. They are not consumed by GHDL and do not determine virtual board mapping.

This is functional RTL simulation, not a complete emulation of FPGA silicon, DDR, USB, Ethernet, timing closure, or vendor IP. No Vivado, synthesis-to-device flow, bitstream generation, or board programming is included. Only VHDL is supported in this version.

## Validation

```sh
python3 -m unittest -v test_lab.py
```

Tests run the original elevator testbench, real top-level board up/down interaction with timing overrides, a different mapped VHDL design, compiler errors, assertion failures, and path validation.
