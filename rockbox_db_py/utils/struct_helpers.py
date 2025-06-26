# Basic struct helper, to help with struct packing and unpacking.

import struct

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


