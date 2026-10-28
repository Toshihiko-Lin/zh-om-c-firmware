"""Read/rebuild this project's PyInstaller archive without executing its payload."""
import marshal
import struct
import zlib
from pathlib import Path

MAGIC = b'MEI\x0c\x0b\x0a\x0b\x0e'
EXPECTED_SHA256 = 'e30c019b3179d12c16abaa7ec03a4d2b75e8d647bf5f15ab9ca043098cb1ae43'


class Archive:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        cookie = self.data.rfind(MAGIC)
        _, size, offset, length, self.version, self.library = struct.unpack(
            '!8sIIII64s', self.data[cookie:cookie + 88])
        self.start = cookie + 88 - size
        self.stub = self.data[:self.start]
        self.entries = []
        table = self.data[self.start + offset:self.start + offset + length]
        i = 0
        while i < len(table):
            size, pos, packed, raw, flag, kind = struct.unpack('!iIIIBB', table[i:i + 18])
            name = table[i + 18:i + size].rstrip(b'\0').decode('utf-8')
            self.entries.append((name, self.data[self.start + pos:self.start + pos + packed], raw, flag, kind))
            i += size

    def read(self, name):
        for key, packed, _, flag, _ in self.entries:
            if key == name:
                return zlib.decompress(packed) if flag else packed
        raise KeyError(name)

    def write(self, path, replacements):
        payload = bytearray()
        table = bytearray()
        for name, packed, raw, flag, kind in self.entries:
            if name in replacements:
                data = replacements[name]
                raw = len(data)
                packed = zlib.compress(data, 9) if flag else data
            encoded = name.encode() + b'\0'
            size = (18 + len(encoded) + 15) & ~15
            table.extend(struct.pack('!iIIIBB', size, len(payload), len(packed), raw, flag, kind))
            table.extend(encoded + b'\0' * (size - 18 - len(encoded)))
            payload.extend(packed)
        cookie = struct.pack('!8sIIII64s', MAGIC, len(payload) + len(table) + 88,
                             len(payload), len(table), self.version, self.library)
        Path(path).write_bytes(self.stub + payload + table + cookie)


class Pyz:
    def __init__(self, data):
        self.data = data
        self.header = data[:12]
        self.entries = list(marshal.loads(data[struct.unpack('!i', data[8:12])[0]:]))

    def read(self, name):
        for key, (_, pos, length) in self.entries:
            if key == name:
                return marshal.loads(zlib.decompress(self.data[pos:pos + length]))
        raise KeyError(name)

    def write(self, replacements):
        payload = bytearray(self.header)
        table = []
        for name, (kind, pos, length) in self.entries:
            packed = (zlib.compress(marshal.dumps(replacements[name]), 9)
                      if name in replacements else self.data[pos:pos + length])
            table.append((name, (kind, len(payload), len(packed))))
            payload.extend(packed)
        payload[8:12] = struct.pack('!i', len(payload))
        payload.extend(marshal.dumps(table))
        return bytes(payload)
