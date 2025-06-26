# Rockbox Tag File Entry Class

# tag_file_entry.py
import struct
import math
from rockbox_db_py.utils.defs import ENCODING, TAGFILE_ENTRY_CHUNK_LENGTH
from rockbox_db_py.utils.struct_helpers import (
    ENDIANNESS_CHAR,
    read_uint32,
    write_uint32,
)


class TagFileEntry:
    """Represents an entry in a tag data file (database_X.tcd)."""

    def __init__(
        self, tag_data="", idx_id=0xFFFFFFFF, is_filename_db=False, offset_in_file=None
    ):
        self.tag_data = tag_data  # Stored as Python string
        self.idx_id = idx_id
        self.is_filename_db = is_filename_db
        self.offset_in_file = offset_in_file

    @classmethod
    def from_file(cls, f, is_filename_db=False):
        """Reads a TagFileEntry from a file object."""

        initial_offset = f.tell()
        tag_length = read_uint32(f)
        idx_id = read_uint32(f)

        raw_tag_data = f.read(tag_length)
        if len(raw_tag_data) < tag_length:
            raise EOFError(
                f"Not enough bytes to read tag data. Expected {tag_length}, got {len(raw_tag_data)}"
            )

        # Decode data up to the first null byte
        null_byte_pos = raw_tag_data.find(b"\x00")
        if null_byte_pos != -1:
            decoded_tag_data = raw_tag_data[:null_byte_pos].decode(ENCODING)
        else:
            decoded_tag_data = raw_tag_data.decode(ENCODING, errors="ignore")

        return cls(
            tag_data=decoded_tag_data,
            idx_id=idx_id,
            is_filename_db=is_filename_db,
            offset_in_file=initial_offset,
        )

    def to_bytes(self):
        """Converts the TagFileEntry object to its raw byte representation, applying padding."""
        encoded_data = self.tag_data.encode(ENCODING)
        data_with_null = encoded_data + b"\x00"

        # Calculate the padded length based on filename database status
        if self.is_filename_db:
            padded_length = len(data_with_null)
        else:
            padded_length = (
                int(math.ceil(len(data_with_null) / TAGFILE_ENTRY_CHUNK_LENGTH))
                * TAGFILE_ENTRY_CHUNK_LENGTH
            )

        # Pad with 'X' bytes
        padded_data = data_with_null.ljust(padded_length, b"X")

        # Pack header and padded data
        packed_header = struct.pack(
            ENDIANNESS_CHAR + "II",
            padded_length,  # This is the tag_length field
            self.idx_id,
        )
        return packed_header + padded_data

    @property
    def tag_length(self):
        """Calculates the tag_length field based on current data and filename db status."""
        encoded_data = self.tag_data.encode(ENCODING)
        data_with_null_len = len(encoded_data) + 1  # +1 for null terminator

        if self.is_filename_db:
            return data_with_null_len
        else:
            return (
                int(math.ceil(data_with_null_len / TAGFILE_ENTRY_CHUNK_LENGTH))
                * TAGFILE_ENTRY_CHUNK_LENGTH
            )

    @property
    def size(self):
        """Returns the total size of the entry in bytes, including header and padding."""
        return self.tag_length + 8  # 8 bytes for tag_length and idx_id fields

    def __repr__(self):
        return (
            f"TagFileEntry(tag_data='{self.tag_data}', idx_id={self.idx_id}, "
            f"is_filename_db={self.is_filename_db}, tag_length={self.tag_length})"
        )

    def __str__(self):
        return self.tag_data
