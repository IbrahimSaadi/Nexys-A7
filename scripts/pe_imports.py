"""List Windows PE DLL imports without executing the binary."""
from pathlib import Path
import struct
import sys


def imports(path):
    data = Path(path).read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    sections = struct.unpack_from('<H', data, pe+6)[0]
    optional_size = struct.unpack_from('<H', data, pe+20)[0]
    optional = pe+24
    directory = optional + (112 if struct.unpack_from('<H', data, optional)[0] == 0x20b else 96)
    rva = struct.unpack_from('<I', data, directory+8)[0]
    section_table = optional+optional_size

    def offset(address):
        for index in range(sections):
            size, start, raw_size, raw = struct.unpack_from('<IIII', data, section_table+40*index+8)
            if start <= address < start+max(size, raw_size):
                return raw+address-start
        raise ValueError('Unmapped PE address')

    if not rva:
        return []
    result = []
    position = offset(rva)
    while any(data[position:position+20]):
        name_rva = struct.unpack_from('<I', data, position+12)[0]
        name = offset(name_rva)
        result.append(data[name:data.index(b'\0', name)].decode('ascii'))
        position += 20
    return result


if __name__ == '__main__':
    for name in sys.argv[1:]:
        print(name, imports(name))
