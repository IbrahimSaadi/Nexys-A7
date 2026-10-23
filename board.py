"""Nexys A7-100T pin facts and a deliberately non-executing XDC subset parser.

The catalog describes board wiring, not complete peripheral emulation. Directions
are relative to FPGA fabric. ``configurable`` means the consulted pin sources do
not prove one fixed direction; the user's VHDL port is authoritative at runtime.
No Tcl, Python eval, shell, network call or external process executes an XDC.
"""
from __future__ import annotations

from copy import deepcopy
import re
from collections.abc import Mapping

SOURCE_URLS = [
    'https://github.com/Digilent/digilent-xdc/blob/master/Nexys-A7-100T-Master.xdc',
    'https://github.com/Digilent/vivado-boards/blob/master/new/board_files/nexys-a7-100t/D.0/1.3/board.xml',
    'https://github.com/Digilent/vivado-boards/blob/master/new/board_files/nexys-a7-100t/D.0/1.3/mig.prj',
]
# Names/pads/standards transcribed from the official master XDC and DDR2 MIG
# pin-selection data. Pin locations are hardware facts. Digilent's board XML
# metadata is MIT licensed, Copyright (c) 2025 Digilent, Inc. See source URLs.
_PIN_ROWS = """
CLK100MHZ|E3|LVCMOS33
SW[0]|J15|LVCMOS33
SW[1]|L16|LVCMOS33
SW[2]|M13|LVCMOS33
SW[3]|R15|LVCMOS33
SW[4]|R17|LVCMOS33
SW[5]|T18|LVCMOS33
SW[6]|U18|LVCMOS33
SW[7]|R13|LVCMOS33
SW[8]|T8|LVCMOS18
SW[9]|U8|LVCMOS18
SW[10]|R16|LVCMOS33
SW[11]|T13|LVCMOS33
SW[12]|H6|LVCMOS33
SW[13]|U12|LVCMOS33
SW[14]|U11|LVCMOS33
SW[15]|V10|LVCMOS33
LED[0]|H17|LVCMOS33
LED[1]|K15|LVCMOS33
LED[2]|J13|LVCMOS33
LED[3]|N14|LVCMOS33
LED[4]|R18|LVCMOS33
LED[5]|V17|LVCMOS33
LED[6]|U17|LVCMOS33
LED[7]|U16|LVCMOS33
LED[8]|V16|LVCMOS33
LED[9]|T15|LVCMOS33
LED[10]|U14|LVCMOS33
LED[11]|T16|LVCMOS33
LED[12]|V15|LVCMOS33
LED[13]|V14|LVCMOS33
LED[14]|V12|LVCMOS33
LED[15]|V11|LVCMOS33
LED16_B|R12|LVCMOS33
LED16_G|M16|LVCMOS33
LED16_R|N15|LVCMOS33
LED17_B|G14|LVCMOS33
LED17_G|R11|LVCMOS33
LED17_R|N16|LVCMOS33
CA|T10|LVCMOS33
CB|R10|LVCMOS33
CC|K16|LVCMOS33
CD|K13|LVCMOS33
CE|P15|LVCMOS33
CF|T11|LVCMOS33
CG|L18|LVCMOS33
DP|H15|LVCMOS33
AN[0]|J17|LVCMOS33
AN[1]|J18|LVCMOS33
AN[2]|T9|LVCMOS33
AN[3]|J14|LVCMOS33
AN[4]|P14|LVCMOS33
AN[5]|T14|LVCMOS33
AN[6]|K2|LVCMOS33
AN[7]|U13|LVCMOS33
CPU_RESETN|C12|LVCMOS33
BTNC|N17|LVCMOS33
BTNU|M18|LVCMOS33
BTNL|P17|LVCMOS33
BTNR|M17|LVCMOS33
BTND|P18|LVCMOS33
JA[1]|C17|LVCMOS33
JA[2]|D18|LVCMOS33
JA[3]|E18|LVCMOS33
JA[4]|G17|LVCMOS33
JA[7]|D17|LVCMOS33
JA[8]|E17|LVCMOS33
JA[9]|F18|LVCMOS33
JA[10]|G18|LVCMOS33
JB[1]|D14|LVCMOS33
JB[2]|F16|LVCMOS33
JB[3]|G16|LVCMOS33
JB[4]|H14|LVCMOS33
JB[7]|E16|LVCMOS33
JB[8]|F13|LVCMOS33
JB[9]|G13|LVCMOS33
JB[10]|H16|LVCMOS33
JC[1]|K1|LVCMOS33
JC[2]|F6|LVCMOS33
JC[3]|J2|LVCMOS33
JC[4]|G6|LVCMOS33
JC[7]|E7|LVCMOS33
JC[8]|J3|LVCMOS33
JC[9]|J4|LVCMOS33
JC[10]|E6|LVCMOS33
JD[1]|H4|LVCMOS33
JD[2]|H1|LVCMOS33
JD[3]|G1|LVCMOS33
JD[4]|G3|LVCMOS33
JD[7]|H2|LVCMOS33
JD[8]|G4|LVCMOS33
JD[9]|G2|LVCMOS33
JD[10]|F3|LVCMOS33
XA_N[1]|A14|LVCMOS33
XA_P[1]|A13|LVCMOS33
XA_N[2]|A16|LVCMOS33
XA_P[2]|A15|LVCMOS33
XA_N[3]|B17|LVCMOS33
XA_P[3]|B16|LVCMOS33
XA_N[4]|A18|LVCMOS33
XA_P[4]|B18|LVCMOS33
VGA_R[0]|A3|LVCMOS33
VGA_R[1]|B4|LVCMOS33
VGA_R[2]|C5|LVCMOS33
VGA_R[3]|A4|LVCMOS33
VGA_G[0]|C6|LVCMOS33
VGA_G[1]|A5|LVCMOS33
VGA_G[2]|B6|LVCMOS33
VGA_G[3]|A6|LVCMOS33
VGA_B[0]|B7|LVCMOS33
VGA_B[1]|C7|LVCMOS33
VGA_B[2]|D7|LVCMOS33
VGA_B[3]|D8|LVCMOS33
VGA_HS|B11|LVCMOS33
VGA_VS|B12|LVCMOS33
SD_RESET|E2|LVCMOS33
SD_CD|A1|LVCMOS33
SD_SCK|B1|LVCMOS33
SD_CMD|C1|LVCMOS33
SD_DAT[0]|C2|LVCMOS33
SD_DAT[1]|E1|LVCMOS33
SD_DAT[2]|F1|LVCMOS33
SD_DAT[3]|D2|LVCMOS33
ACL_MISO|E15|LVCMOS33
ACL_MOSI|F14|LVCMOS33
ACL_SCLK|F15|LVCMOS33
ACL_CSN|D15|LVCMOS33
ACL_INT[1]|B13|LVCMOS33
ACL_INT[2]|C16|LVCMOS33
TMP_SCL|C14|LVCMOS33
TMP_SDA|C15|LVCMOS33
TMP_INT|D13|LVCMOS33
TMP_CT|B14|LVCMOS33
M_CLK|J5|LVCMOS33
M_DATA|H5|LVCMOS33
M_LRSEL|F5|LVCMOS33
AUD_PWM|A11|LVCMOS33
AUD_SD|D12|LVCMOS33
UART_TXD_IN|C4|LVCMOS33
UART_RXD_OUT|D4|LVCMOS33
UART_CTS|D3|LVCMOS33
UART_RTS|E5|LVCMOS33
PS2_CLK|F4|LVCMOS33
PS2_DATA|B2|LVCMOS33
ETH_MDC|C9|LVCMOS33
ETH_MDIO|A9|LVCMOS33
ETH_RSTN|B3|LVCMOS33
ETH_CRSDV|D9|LVCMOS33
ETH_RXERR|C10|LVCMOS33
ETH_RXD[0]|C11|LVCMOS33
ETH_RXD[1]|D10|LVCMOS33
ETH_TXEN|B9|LVCMOS33
ETH_TXD[0]|A10|LVCMOS33
ETH_TXD[1]|A8|LVCMOS33
ETH_REFCLK|D5|LVCMOS33
ETH_INTN|B8|LVCMOS33
QSPI_DQ[0]|K17|LVCMOS33
QSPI_DQ[1]|K18|LVCMOS33
QSPI_DQ[2]|L14|LVCMOS33
QSPI_DQ[3]|M14|LVCMOS33
QSPI_CSN|L13|LVCMOS33
ddr2_addr[0]|M4|SSTL18_II
ddr2_addr[10]|R2|SSTL18_II
ddr2_addr[11]|K5|SSTL18_II
ddr2_addr[12]|N6|SSTL18_II
ddr2_addr[1]|P4|SSTL18_II
ddr2_addr[2]|M6|SSTL18_II
ddr2_addr[3]|T1|SSTL18_II
ddr2_addr[4]|L3|SSTL18_II
ddr2_addr[5]|P5|SSTL18_II
ddr2_addr[6]|M2|SSTL18_II
ddr2_addr[7]|N1|SSTL18_II
ddr2_addr[8]|L4|SSTL18_II
ddr2_addr[9]|N5|SSTL18_II
ddr2_ba[0]|P2|SSTL18_II
ddr2_ba[1]|P3|SSTL18_II
ddr2_ba[2]|R1|SSTL18_II
ddr2_cas_n|L1|SSTL18_II
ddr2_ck_n[0]|L5|DIFF_SSTL18_II
ddr2_ck_p[0]|L6|DIFF_SSTL18_II
ddr2_cke[0]|M1|SSTL18_II
ddr2_cs_n[0]|K6|SSTL18_II
ddr2_dm[0]|T6|SSTL18_II
ddr2_dm[1]|U1|SSTL18_II
ddr2_dq[0]|R7|SSTL18_II
ddr2_dq[10]|V5|SSTL18_II
ddr2_dq[11]|U4|SSTL18_II
ddr2_dq[12]|V4|SSTL18_II
ddr2_dq[13]|T4|SSTL18_II
ddr2_dq[14]|V1|SSTL18_II
ddr2_dq[15]|T3|SSTL18_II
ddr2_dq[1]|V6|SSTL18_II
ddr2_dq[2]|R8|SSTL18_II
ddr2_dq[3]|U7|SSTL18_II
ddr2_dq[4]|V7|SSTL18_II
ddr2_dq[5]|R6|SSTL18_II
ddr2_dq[6]|U6|SSTL18_II
ddr2_dq[7]|R5|SSTL18_II
ddr2_dq[8]|T5|SSTL18_II
ddr2_dq[9]|U3|SSTL18_II
ddr2_dqs_n[0]|V9|DIFF_SSTL18_II
ddr2_dqs_n[1]|V2|DIFF_SSTL18_II
ddr2_dqs_p[0]|U9|DIFF_SSTL18_II
ddr2_dqs_p[1]|U2|DIFF_SSTL18_II
ddr2_odt[0]|M3|SSTL18_II
ddr2_ras_n|N4|SSTL18_II
ddr2_we_n|N2|SSTL18_II
"""




def _canonical(name):
    lower = name.lower()
    if lower == 'clk100mhz':
        return 'clock'
    if lower in ('btnc', 'btnu', 'btnl', 'btnr', 'btnd'):
        return 'btn' + lower[-1].upper()
    if lower in ('ca', 'cb', 'cc', 'cd', 'ce', 'cf', 'cg'):
        return f'segment[{ord(lower[-1])-ord("a")}]'
    match = re.fullmatch(r'led(16|17)_([rgb])', lower)
    if match:
        return f'rgb[{int(match[1])-16}].{match[2]}'
    return lower


def _metadata(name):
    """Only attach directions justified by wiring/interface definitions."""
    if name == 'clock':
        return 'clock', 'in', 'digital', 'clock_source'
    if name.startswith('sw['):
        return 'switches', 'in', 'digital', 'interactive_gpio'
    if name.startswith('btn') or name == 'cpu_resetn':
        return 'buttons', 'in', 'digital', 'interactive_gpio'
    if name.startswith('led['):
        return 'leds', 'out', 'digital', 'interactive_gpio'
    if name.startswith('rgb['):
        return 'rgb_leds', 'out', 'digital', 'raw_signal'
    if name.startswith(('segment[', 'an[')) or name == 'dp':
        return 'seven_segment', 'out', 'digital', 'multiplex_display'
    if re.match(r'j[abcd]\[', name):
        return 'pmod', 'inout', 'digital', 'raw_signal'
    if name.startswith(('xa_p[', 'xa_n[')):
        return 'xadc', 'inout', 'analog_capable', 'digital_raw_only'
    if name.startswith('vga_'):
        return 'vga', 'out', 'digital', 'raw_signal'
    if name.startswith('sd_'):
        direction = {'sd_reset':'out', 'sd_cd':'in', 'sd_sck':'out'}.get(name, 'inout')
        return 'micro_sd', direction, 'digital', 'raw_signal'
    if name.startswith('acl_'):
        direction = 'in' if name == 'acl_miso' or name.startswith('acl_int[') else 'out'
        return 'accelerometer', direction, 'digital', 'raw_signal'
    if name.startswith('tmp_'):
        return 'temperature', 'inout' if name in ('tmp_scl','tmp_sda') else 'in', 'digital', 'raw_signal'
    if name.startswith('m_'):
        return 'microphone', 'in' if name == 'm_data' else 'out', 'digital', 'raw_signal'
    if name.startswith('aud_'):
        return 'audio', 'out', 'digital', 'raw_signal'
    if name.startswith('uart_'):
        # Directions confirmed by Digilent's board.xml UART port_maps.
        direction = {'uart_txd_in':'in', 'uart_rxd_out':'out', 'uart_rts':'out', 'uart_cts':'in'}[name]
        return 'uart', direction, 'digital', 'raw_signal'
    if name.startswith('ps2_'):
        return 'usb_hid_ps2', 'inout', 'digital', 'raw_signal'
    if name.startswith('eth_'):
        # REFCLK's direction is not stated by the consulted master-XDC source.
        directions = {'eth_mdc':'out','eth_mdio':'inout','eth_rstn':'out',
                      'eth_crsdv':'in','eth_rxerr':'in','eth_txen':'out','eth_intn':'in'}
        direction = directions.get(name, 'in' if name.startswith('eth_rxd[') else 'out' if name.startswith('eth_txd[') else 'configurable')
        return 'ethernet', direction, 'digital', 'raw_signal'
    if name.startswith('qspi_'):
        return 'qspi_flash', 'inout' if name.startswith('qspi_dq[') else 'out', 'digital', 'raw_signal'
    if name.startswith('ddr2_'):
        direction = 'inout' if name.startswith(('ddr2_dq[','ddr2_dqs_')) else 'out'
        return 'ddr2', direction, 'digital', 'raw_signal'
    return 'other', 'configurable', 'digital', 'raw_signal'


def _make_catalog():
    records = []
    for line in _PIN_ROWS.strip().splitlines():
        source_name, pin, standard = line.split('|')
        signal = _canonical(source_name)
        group, direction, kind, model = _metadata(signal)
        row = {'signal':signal, 'pin':pin, 'iostandard':standard,
               'group':group, 'direction':direction, 'kind':kind, 'model':model,
               'source_name':source_name}
        if signal == 'clock':
            row['frequency_hz'] = 100000000
        if signal in ('cpu_resetn', 'dp') or signal.startswith(('segment[','an[')):
            row['active_low'] = True
        if signal == 'cpu_resetn':
            row['idle'] = '1'
        records.append(row)
    if len({r['pin'] for r in records}) != len(records):
        raise RuntimeError('Duplicate physical pin in board catalog')
    return records


PINS = _make_catalog()
BY_PIN = {row['pin']: row for row in PINS}
BY_SIGNAL = {row['signal']: row for row in PINS}


def catalog():
    """Return JSON-ready catalog; raw exposure does not mean a device model exists."""
    return {'board':'Nexys A7-100T', 'fpga':'xc7a100tcsg324-1',
            'sources':SOURCE_URLS[:], 'pins':deepcopy(PINS),
            'limitations':['Raw pins are not complete DDR2, Ethernet, USB, SD, SPI or sensor models.',
                           'Analog-capable XADC pins expose digital levels only in this simulator.',
                           'Power, ground, and dedicated configuration/JTAG pins are not ordinary fabric signal ports.',
                           'Directions are relative to FPGA fabric; configurable directions require the project port declaration.']}


def _commands(text):
    """Split a small static Tcl subset without evaluating substitutions."""
    text = text.replace('\\\r\n',' ').replace('\\\n',' ')
    buffer, braces, brackets, quote, escaped, comment = [], 0, 0, False, False, False
    for char in text:
        if comment:
            if char == '\n':
                comment = False
                if buffer:
                    yield ''.join(buffer).strip()
                    buffer = []
            continue
        if escaped:
            buffer.extend(('\\',char))
            escaped = False
            continue
        if char == '\\':
            escaped = True
            continue
        if char == '#' and braces == 0 and not quote:
            comment = True
            continue
        if char == '"' and braces == 0:
            quote = not quote
        if not quote:
            if char == '{': braces += 1
            elif char == '}': braces -= 1
            elif char == '[' and braces == 0: brackets += 1
            elif char == ']' and braces == 0: brackets -= 1
        if char in ';\n' and braces == 0 and brackets == 0 and not quote:
            if buffer:
                yield ''.join(buffer).strip()
                buffer = []
        else:
            buffer.append(char)
    if buffer:
        yield ''.join(buffer).strip()


_PORT_REF = re.compile(r'[A-Za-z][A-Za-z0-9_]*(?:\[[0-9]+\])?\Z')
_PIN = re.compile(r'[A-Za-z]{1,2}[0-9]{1,2}\Z')


def _port_list(command):
    match = re.search(r'\[\s*get_ports\s+(?:-quiet\s+)?(.*?)\s*\]\s*\Z', command, re.S)
    if not match:
        return None
    raw = match[1].strip()
    if len(raw) >= 2 and raw[0] in '{"' and raw[-1] == ('}' if raw[0] == '{' else '"'):
        raw = raw[1:-1].strip()
    refs = raw.split()
    return refs if refs and all(_PORT_REF.fullmatch(ref) for ref in refs) else None


def parse_xdc(text):
    """Parse literal PACKAGE_PIN and create_clock commands only.

    Dynamic Tcl, wildcards, variables, expressions and command substitution are
    reported but never executed. Conflicting assignments remain unresolved.
    ``pins`` retains authored port spelling; matching helpers are case-insensitive.
    """
    pins, clocks, warnings, conflicts, spelling, clock_conflicts = {}, {}, [], set(), {}, set()
    for command in _commands(text):
        if not command:
            continue
        refs = _port_list(command)
        if re.match(r'^set_property\b', command, re.I):
            if not re.search(r'\bPACKAGE_PIN\b', command, re.I):
                continue
            if not refs:
                warnings.append('Skipped nonliteral PACKAGE_PIN/get_ports command: ' + command[:160])
                continue
            direct = re.match(r'^set_property\s+PACKAGE_PIN\s+(\{[^{}]*\}|"[^"]*"|[^\s\[]+)\s+\[', command, re.I)
            prop = None
            if direct:
                literal = direct[1]
                if literal.startswith(('{','"')):
                    literal = literal[1:-1].strip()
                prop = re.fullmatch(r'([A-Za-z]{1,2}[0-9]{1,2})',literal)
            if not prop:
                dictionary = re.match(r'^set_property\s+-dict\s+\{([^{}]*)\}\s+\[', command, re.I|re.S)
                if dictionary:
                    tokens = dictionary[1].split()
                    if len(tokens)%2 == 0:
                        pairs = dict(zip((t.upper() for t in tokens[::2]),tokens[1::2]))
                        candidate = pairs.get('PACKAGE_PIN','')
                        prop = re.fullmatch(r'([A-Za-z]{1,2}[0-9]{1,2})',candidate)
            if not prop:
                warnings.append('Skipped nonliteral PACKAGE_PIN value: ' + command[:160])
                for ref in refs:
                    key=ref.lower()
                    conflicts.add(key)
                    prior=next((name for name in pins if name.lower()==key),None)
                    if prior is not None:pins.pop(prior,None)
                    warnings.append(f'{ref}: unresolved PACKAGE_PIN value; name fallback disabled')
                continue
            pin = prop[1].upper()
            for ref in refs:
                key = ref.lower()
                spelling.setdefault(key,ref)
                prior_key = spelling[key]
                if key in conflicts:
                    continue
                if prior_key in pins and pins[prior_key] != pin:
                    warnings.append(f'Conflicting PACKAGE_PIN assignments for {ref}; mapping left unresolved')
                    pins.pop(prior_key,None)
                    conflicts.add(key)
                else:
                    pins[prior_key] = pin
                if pin not in BY_PIN:
                    warnings.append(f'{ref}: package pin {pin} is not in the Nexys A7-100T signal catalog')
        elif re.match(r'^create_clock\b',command,re.I):
            period = re.search(r'(?:^|\s)-period\s+([0-9]+(?:\.[0-9]+)?)(?=\s)',command)
            if refs and period and float(period[1])>0:
                for ref in refs:
                    key = ref.lower()
                    if key in clock_conflicts:
                        continue
                    prior = next((name for name in clocks if name.lower()==key),None)
                    if prior is not None and clocks[prior] != float(period[1]):
                        clocks.pop(prior,None)
                        clock_conflicts.add(key)
                        warnings.append(f'Conflicting clock periods for {ref}; period left unresolved')
                    else:
                        clocks[prior or ref] = float(period[1])
            else:
                warnings.append('Skipped nonliteral create_clock command: '+command[:160])
    return {'pins':pins, 'clocks':clocks, 'warnings':warnings, 'conflicts':sorted(conflicts),
            'clock_conflicts':sorted(clock_conflicts)}


def _indices(port):
    if not port.get('vector'):
        return [None]
    match = re.search(r'\(\s*(\d+)\s+(downto|to)\s+(\d+)\s*\)',port.get('type',''),re.I)
    if match:
        left,right = int(match[1]),int(match[3])
        return list(range(left,right+(-1 if left>right else 1),-1 if left>right else 1))
    return list(range(int(port['width'])-1,-1,-1))


def _name_signal(name,index):
    lower = name.lower()
    scalar_aliases = {'clk':'clock','clk100mhz':'clock','clock':'clock','rst':'btnC','reset':'btnC',
                      'go':'btnU','btnc':'btnC','btnu':'btnU','btnl':'btnL','btnr':'btnR','btnd':'btnD','door':'led[0]','led':'led[0]'}
    if index is None:
        candidate = scalar_aliases.get(lower,_canonical(name))
        if candidate in BY_SIGNAL:
            return candidate
        # Authored scalar names SW0, LED0 are common board naming conventions.
        match = re.fullmatch(r'(sw|led)(\d+)',lower)
        if match:
            candidate = f'{match[1]}[{int(match[2])}]'
            return candidate if candidate in BY_SIGNAL else None
        return None
    base = {'dest_floor':'sw','seg':'segment'}.get(lower,lower)
    candidate = _canonical(f'{base}[{index}]')
    return candidate if candidate in BY_SIGNAL else None


def suggest_mapping(ports, files):
    """Suggest every declared port bit from literal physical-pin constraints.

    XDC has priority over names. Result bit lists follow VHDL left-to-right order
    and retain the numeric index (including ascending/non-zero-based vectors).
    Unknown and conflicting pins stay visible and unmapped, never guessed.
    """
    if isinstance(files,str):
        files = {'project.xdc':files}
    if not isinstance(files,Mapping):
        raise ValueError('files must be a filename/content mapping')
    pins, clocks, warnings, conflicts, clock_conflicts = {}, {}, [], set(), set()
    for name,text in files.items():
        if not str(name).lower().endswith('.xdc'):
            continue
        parsed = parse_xdc(text)
        warnings.extend(f'{name}: {message}' for message in parsed['warnings'])
        conflicts.update(parsed['conflicts'])
        clock_conflicts.update(parsed['clock_conflicts'])
        for key in clock_conflicts:
            clocks.pop(key,None)
        for ref,pin in parsed['pins'].items():
            key = ref.lower()
            if key in pins and pins[key] != pin:
                conflicts.add(key)
                warnings.append(f'{ref}: conflicting PACKAGE_PIN constraints across files')
            pins[key] = pin
        for ref,period in parsed['clocks'].items():
            key = ref.lower()
            if key in clock_conflicts:
                continue
            if key in clocks and clocks[key] != period:
                warnings.append(f'{ref}: conflicting clock periods across files; clock period left unresolved')
                clocks.pop(key,None)
                clock_conflicts.add(key)
            else:
                clocks[key] = period
    for key in conflicts:
        pins.pop(key,None)
    mapping = {}
    for port in ports:
        bits = []
        for index in _indices(port):
            ref = port['name'] + (f'[{index}]' if index is not None else '')
            key = ref.lower()
            pin = pins.get(key)
            record = BY_PIN.get(pin)
            signal = record['signal'] if record else None
            source = 'xdc' if pin else 'unmapped'
            if not pin and key not in conflicts:
                signal = _name_signal(port['name'],index)
                if signal:
                    source = 'name'
                    pin = BY_SIGNAL[signal]['pin']
            direction = 'out' if port.get('direction')=='buffer' else port.get('direction')
            board_direction = BY_SIGNAL.get(signal,{}).get('direction')
            if board_direction in ('in','out') and direction in ('in','out') and direction != board_direction:
                warnings.append(f'{ref}: VHDL direction {direction} disagrees with fixed board signal {signal} ({board_direction})')
            bits.append({'index':index, 'signal':signal, 'pin':pin, 'source':source})
        mapping[port['name']] = bits
    return {'mapping':mapping, 'warnings':warnings, 'clocks':clocks,
            'unmatched_constraints':sorted(key for key in pins if key not in {p['name'].lower()+(f'[{i}]' if i is not None else '') for p in ports for i in _indices(p)})}
