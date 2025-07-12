# tag_file_entry.py
#
# Represents a single entry in a Rockbox Tag File (database_X.tcd).
# Each entry corresponds to a specific tag data (like artist names or song titles)
# and contains metadata about its position in the file and its unique identifier.

import struct
import math
from typing import Optional

from rockbox_db_py.classes.db_file_type import RockboxDBFileType
from rockbox_db_py.utils.defs import ENCODING, TAGFILE_ENTRY_CHUNK_LENGTH
from rockbox_db_py.utils.struct_helpers import ENDIANNESS_CHAR
from rockbox_db_py.utils.struct_helpers import read_uint32


class TagFileEntry:
    """
    Models the 'struct tagfile_entry' structure from Rockbox's tagcache.c.
    Represents how individual tag data (like artist names or song titles)
    is stored on disk within a Rockbox Tag File (database_X.tcd).
    """

    def __init__(
        self,
        tag_data: str = "",
        idx_id: int = 0xFFFFFFFF,
        offset_in_file: Optional[int] = None,
        unique_id: Optional[str] = None,
        db_file_type: Optional[RockboxDBFileType] = None,
    ):
        self.tag_data = tag_data
        self.idx_id = idx_id
        self.offset_in_file = offset_in_file
        self.db_file_type = db_file_type
        self.is_filename_db = (
            True if db_file_type and db_file_type.is_filename_db else False
        )

        # A unique ID, used for de-duplication and tracking.
        self.unique_id = unique_id

    @property
    def key(self) -> str:
        """
        Returns a unique key for this entry based on its tag data and idx_id.
        This is used for de-duplication and quick lookups.
        """
        if self.unique_id:
            return self.unique_id
        return self.tag_data

    @classmethod
    def from_file(
        cls, f, db_file_type: Optional[RockboxDBFileType] = None
    ) -> "TagFileEntry":
        """
        Reads a TagFileEntry from a file object.

        Args:
            f: File object, positioned at the start of an entry.
            db_file_type: Optional RockboxDBFileType instance, which indicates if this is a filename database,
                            which dictates unique padding rules.

        Returns:
            A new TagFileEntry instance.

        Raises:
            EOFError: If the end of the file is reached unexpectedly.
        """
        initial_offset: int = f.tell()

        tag_length: int = read_uint32(f)
        idx_id: int = read_uint32(f)

        raw_tag_data: bytes = f.read(tag_length)
        if len(raw_tag_data) < tag_length:
            raise EOFError(
                f"Not enough bytes to read tag data. Expected {tag_length}, got {len(raw_tag_data)}"
            )

        decoded_tag_data: str
        null_byte_pos: int = raw_tag_data.find(b"\x00")
        is_comment_db: bool = db_file_type == RockboxDBFileType.COMMENT

        if null_byte_pos != -1:
            # If it's a comment DB and the null-terminated part is 40 bytes, try binary unpack
            if is_comment_db and null_byte_pos == 40:
                try:
                    # Attempt to unpack as 10 unsigned 32-bit integers (little-endian assumed)
                    ints = struct.unpack("<10I", raw_tag_data[:null_byte_pos])
                    decoded_tag_data = " ".join(
                        f"{i:08X}" for i in ints
                    )  # Format as "00000EDA 00000B79 ..."
                except struct.error:
                    # Fallback if unpacking fails, just hex representation
                    decoded_tag_data = "".join(
                        f"{b:02X}" for b in raw_tag_data[:null_byte_pos]
                    )
            else:
                # Standard UTF-8 decode for other tags or non-matching comment patterns
                try:
                    decoded_tag_data = raw_tag_data[:null_byte_pos].decode(ENCODING)
                except UnicodeDecodeError:
                    # Fallback for non-UTF-8 data with null terminator.
                    decoded_tag_data = "".join(
                        f"{b:02X}" for b in raw_tag_data[:null_byte_pos]
                    )
        else:
            # If no null byte, and it's a comment DB and raw data is 40 bytes, try binary unpack
            if is_comment_db and len(raw_tag_data) == 40:
                try:
                    ints = struct.unpack("<10I", raw_tag_data)
                    decoded_tag_data = " ".join(f"{i:08X}" for i in ints)
                except struct.error:
                    decoded_tag_data = "".join(f"{b:02X}" for b in raw_tag_data)
            else:
                # Fallback for other non-null-terminated data, represent as hex string
                decoded_tag_data = "".join(f"{b:02X}" for b in raw_tag_data)

        return cls(
            tag_data=decoded_tag_data,
            idx_id=idx_id,
            db_file_type=db_file_type,
            offset_in_file=initial_offset,
        )

    def to_bytes(self) -> bytes:
        """
        Converts the TagFileEntry object into its raw byte representation for disk.
        Applies padding and null termination based on Rockbox specifications.
        """
        encoded_data: bytes = self.tag_data.encode(ENCODING)
        data_with_null: bytes = encoded_data + b"\x00"

        # Calculate the padded length of the data portion, applying specific rules for filename database.
        if self.is_filename_db:
            padded_length: int = len(data_with_null)
        else:
            padded_length = (
                int(math.ceil(len(data_with_null) / TAGFILE_ENTRY_CHUNK_LENGTH))
                * TAGFILE_ENTRY_CHUNK_LENGTH
            )

        # Pad with 'X' bytes as seen in tagcache.c for unused space.
        padded_data: bytes = data_with_null.ljust(padded_length, b"X")

        # Pack the fixed-size 8-byte header (tag_length and idx_id) with endianness.
        packed_header: bytes = struct.pack(
            ENDIANNESS_CHAR + "II",
            padded_length,
            self.idx_id,
        )
        return packed_header + padded_data

    @property
    def tag_length(self) -> int:
        """
        Calculates the 'tag_length' field value as written to the file,
        including null termination and padding.
        """
        encoded_data: bytes = self.tag_data.encode(ENCODING)
        data_with_null_len: int = len(encoded_data) + 1

        if self.is_filename_db:
            return data_with_null_len
        else:
            return (
                int(math.ceil(data_with_null_len / TAGFILE_ENTRY_CHUNK_LENGTH))
                * TAGFILE_ENTRY_CHUNK_LENGTH
            )

    @property
    def size(self) -> int:
        """
        Returns the total byte size of this TagFileEntry on disk,
        including its 8-byte header and the padded data.
        """
        return self.tag_length + 8

    def __repr__(self) -> str:
        """Provides a developer-friendly string representation."""
        return (
            f"TagFileEntry(tag_data='{self.tag_data}', idx_id={self.idx_id}, "
            f"is_filename_db={self.is_filename_db}, tag_length={self.tag_length}, "
            f"offset_in_file={hex(self.offset_in_file) if self.offset_in_file is not None else 'None'})"
        )

    def __str__(self) -> str:
        """Provides a user-friendly string representation (the tag data itself)."""
        return self.tag_data
