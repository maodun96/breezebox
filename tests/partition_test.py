"""Ensure the release guard rejects layout drift, not just oversized images."""
import importlib.util
from pathlib import Path
import struct

spec = importlib.util.spec_from_file_location('build', Path(__file__).parents[1] / 'build.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
data = b''.join(struct.pack('<HBBII16sI', 0x50aa, kind, subtype, offset, size,
                            name.encode(), flags)
                for name, kind, subtype, offset, size, flags in build.PARTITIONS)
build.check_partitions(data + b'\xff' * 32)
for position in (2, 3, 4, 8, 12, 28):
    changed = bytearray(data)
    changed[position] ^= 1
    try:
        build.check_partitions(changed)
    except AssertionError:
        pass
    else:
        raise AssertionError(f'Layout drift accepted at byte {position}')
try:
    build.check_partitions(data[:-32])
except AssertionError:
    pass
else:
    raise AssertionError('Missing partition accepted')
print('PASS partition guard: rejects type, subtype, offset, size, label, flags and missing entries')
