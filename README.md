# Nexys Lab

VHDL editor and continuous Nexys A7 style 2D board, powered by real GHDL simulation. Includes the supplied 16-floor elevator without changing its source files.

## Windows portable edition

Download **Nexys-Lab-Windows-x64.zip** from [GitHub Releases](https://github.com/IbrahimSaadi/Nexys-A7/releases/latest). Extract the entire ZIP to a writable folder and double-click **Start-Nexys-Lab.cmd**. Python and GHDL are included. No installation, PATH changes, administrator privileges or Internet connection are required to run. The launcher opens the browser and finds a free port if an older server is running. Keep its console open; Ctrl+C stops the app.

Use the newly opened browser tab, not an old bookmark. The header shows the running version. Code → Download ZIP is the source edition, without runtimes. Browser-local projects belong to the current address/port: export your edits before moving to a new version or port, then import the JSON.

## Continuous board mode

1. Select **Interactive board**, top entity `elevator_top`, then press **Run** once.
2. Set SW3–SW0 to the destination (0–15). Click Up / GO.
3. The simulation clock runs automatically. No Advance tick button is needed.
4. Pause/Resume freezes and continues HDL time without restarting the circuit. Stop ends the session. Reset session starts a fresh circuit.

The backend keeps one GHDL process and its state alive per session. It applies switch/button changes between 1 ms HDL intervals. A click generates at least 30 ms of HDL button input, enough for the design's original 20 ms debounce. Switch changes are delivered at the next interval. This interval-based I/O is not analog contact bounce or sub-cycle physical input timing.

### Clock and time accuracy

The clock is **100 MHz**, exactly **10 ns** per period in HDL time. Board mode uses the original source constants: no DIVISOR, DEBOUNCE_CYCLES or SCAN_DIV overrides. A one-second divider therefore requires 100 million clock cycles, just as described by the source. The door timer and travel timing come from actual VHDL, not JavaScript logic.

**Exact HDL time is not a guarantee of real-time execution.** An event-driven CPU simulator can run much slower than a physical FPGA. The UI shows HDL time, elapsed wall time and the measured ratio. It never labels software lag as real-time speed or compensates by changing the design. On the onboarding machine a 1 ms elevator interval took roughly 170 ms of wall time; your Windows machine may differ. Button debounce, floor travel and door timers can therefore take longer in wall time. If simulation can outrun wall time, the frontend paces requests to at most 1×.

The new board is a vector representation following the supplied board layout, not an exact photograph. Switches, buttons, LEDs and eight multiplexed seven-segment digits are functional. Other connectors and chips are visual references: DDR, VGA, USB, Ethernet, Pmod peripherals and full FPGA silicon are not emulated.

## Editor and future projects

- Import `.vhd`, `.vhdl`, `.xdc`, `.txt` files or an exported project JSON. Create, edit and delete files in the explorer. Source edits save to browser localStorage, not server example files. Export project creates a portable backup.
- Board mode supports scalar `std_logic` and numeric fixed-width `std_logic_vector` ports. Run to discover ports; use **Port mapping** to bind the 100 MHz clock, switches, buttons, LEDs, segment, anodes and door. Mapping changes stop the old session; Run starts the new binding. Narrow switch inputs use low-order bits. Unmapped inputs remain zero.
- The active-low display expects `segment(6 downto 0)` in gfedcba order and `an(7 downto 0)`. The backend samples settled multiplex transitions to reconstruct all digits. Decimal point is available as a sampled output but is not yet rendered on the board.
- Generic-dependent widths, custom types, other libraries, or vendor IP may need a wrapper or additional libraries. Use Testbench mode for interfaces the board adapter cannot bind.
- XDC files are retained for export; GHDL does not consume physical pin constraints. Virtual controls use the Port mapping tab.

## Testbench and waveforms

Select **Testbench**, top `tb_fsm`, duration `2us`, and Run. The included testbench must print **ALL FSM TESTS PASSED**. This mode generates a full VCD and honors the configured stop time. A successful stop-time run alone does not prove correctness: write self-checking assertions.

Live board mode previews **sampled output values** at frame boundaries and exports `live-samples.vcd`. It does not record every internal signal or 100 MHz edge, avoiding massive trace files during continuous runs. The seven-segment display is monitored inside VHDL between frames so multiplexing is preserved. For full clock-resolution waveform analysis, use Testbench mode and export its VCD.

## Source edition setup

Requires Python 3.10+ and GHDL supporting VHDL-2008. No Python/npm packages are required to run.

```sh
cd /workspace/Nexys-A7
. /workspace/.nexys-tools/activate.sh
python3 server.py --auto-port --open-browser
```

On Debian/Ubuntu install Python and GHDL using your system package manager. On Windows, source-edition users can install a native x64 GHDL release, extract it completely, and set its path in PowerShell:

```powershell
$env:GHDL_PATH = 'C:\Tools\ghdl\bin\ghdl.exe'
& $env:GHDL_PATH --version
py server.py --auto-port --open-browser
```

Portable-edition users do not need those manual steps. A raw WinError 2 usually means a source-edition GHDL executable was not found; the current app displays an actionable setup message instead. Default source listener: loopback port 8000; --auto-port tries the next ports if needed.

Only run your own trusted HDL. GHDL is a native compiler/runtime, including VHDL file I/O. This local app is not a security sandbox or a multi-user public service. Session count is limited to four; idle sessions close after two minutes without requests. A live interval that takes over 30 seconds stops the session. No Vivado, bitstream generation or physical FPGA programming is included.

## Validation and portable builds

```sh
python3 -m unittest -v test_lab.py
python3 scripts/build_windows.py
```

Tests cover the supplied FSM assertions, legacy batch simulation, persistent state, exactly 1,000 cycles per 10 microseconds, original 20 ms debounce, multiplexed digits, another mapped design, failure handling, portable simulator detection and occupied ports. Binary runtimes do not enter Git.

The build script verifies pinned official GHDL and CPython downloads and includes their licenses and GHDL source. It produces the portable ZIP and SHA256 file under dist/. GitHub Actions builds on Windows, runs tests using the bundled Windows Python and GHDL, then publishes tagged v* releases only after tests pass.

Hardware facts and the 24 checked elevator pin mappings are documented in [board-reference.md](docs/board-reference.md).
