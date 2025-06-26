# Basic struct helper, to help with struct packing and unpacking.

import struct
import zlib

# Assume we are dealing with little-endian byte order
ENDIANNESS_CHAR = '<'

def read_uint32(file_obj):
    """Read a 32-bit unsigned integer from the data at the given offset."""

    data = file_obj.read(4)
    if len(data) != 4:
        raise ValueError("Not enough data to read a 32-bit unsigned integer.")

    return struct.unpack(ENDIANNESS_CHAR + 'I', data)[0]

def write_uint32(file_obj, value):
    """Write a 32-bit unsigned integer to the file."""
    file_obj.write(struct.pack(ENDIANNESS_CHAR + 'I', value))

def calculate_crc32(s: str) -> int:
    """Calculates the CRC32 checksum of a string, as expected by Rockbox for deleted entries."""
    # Convert to lowercase and encode to bytes
    s_bytes = s.lower().encode('utf-8')
    checksum = zlib.crc32(s_bytes, 0xFFFFFFFF)

    if checksum < 0:
        checksum = checksum + 2**32

    return checksum
