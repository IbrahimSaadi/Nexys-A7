# Nexys A7 hardware references

Sources actually read during development:

- [Digilent Nexys A7 root repository](https://github.com/Digilent/Nexys-A7): official resource-center and demo links.
- [Official Nexys A7-100T board definition](https://github.com/Digilent/vivado-boards/blob/master/new/board_files/nexys-a7-100t/D.0/1.3/board.xml): part `xc7a100tcsg324-1`, 100,000,000 Hz clock, 16 slide switches, 16 user LEDs, 2 RGB LEDs, 5 directional/center buttons, and 8 display anodes.
- [Official Nexys A7-100T master XDC](https://github.com/Digilent/digilent-xdc/blob/master/Nexys-A7-100T-Master.xdc): board pins and 10 ns clock constraint.

The [Digilent reference manual](https://digilent.com/reference/programmable-logic/nexys-a7/reference-manual) is the vendor's manual link, but its website was blocked by the onboarding network proxy. Specifications above were checked against the accessible official GitHub files, rather than claiming that the manual was read.

The default board background is the same manufacturer product photograph as the user's supplied reference (higher resolution with slightly different margins); see [photo source](../third_party/PHOTO-SOURCE.md). The optional vector art follows that layout: power/USB/Ethernet/VGA/audio across the upper edge, FPGA and memory in the center, buttons on the right, eight digits below, and switches along the lower edge. It is a representative drawing, not a dimensionally exact reproduction. Only mapped controls and outputs are functional; decorative connectors do not imply peripheral simulation.

## Supplied elevator constraints checked against official pin mappings

All 24 pin-and-I/O-standard assignments match the corresponding named signal in the official master XDC. These constraints are for future Vivado hardware work; GHDL uses the app's virtual port mapping.

| Elevator port | Official signal | Package pin |
|---|---|---|
| `clk` | `CLK100MHZ` | E3 |
| `rst` | `BTNC` | N17 |
| `go` | `BTNU` | M18 |
| `dest_floor[0]` | `SW[0]` | J15 |
| `dest_floor[1]` | `SW[1]` | L16 |
| `dest_floor[2]` | `SW[2]` | M13 |
| `dest_floor[3]` | `SW[3]` | R15 |
| `door` | `LED[0]` | H17 |
| `segment[0]` | `CA` | T10 |
| `segment[1]` | `CB` | R10 |
| `segment[2]` | `CC` | K16 |
| `segment[3]` | `CD` | K13 |
| `segment[4]` | `CE` | P15 |
| `segment[5]` | `CF` | T11 |
| `segment[6]` | `CG` | L18 |
| `dp` | `DP` | H15 |
| `an[0]` | `AN[0]` | J17 |
| `an[1]` | `AN[1]` | J18 |
| `an[2]` | `AN[2]` | T9 |
| `an[3]` | `AN[3]` | J14 |
| `an[4]` | `AN[4]` | P14 |
| `an[5]` | `AN[5]` | T14 |
| `an[6]` | `AN[6]` | K2 |
| `an[7]` | `AN[7]` | U13 |
