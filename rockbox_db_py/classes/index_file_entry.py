# index_file_entry.py
import struct
from rockbox_db_py.utils.defs import (
    TAG_COUNT,
    TAG_TYPES,
    FILE_TAG_INDICES,
    EMBEDDED_TAG_INDICES,
    FLAG_DELETED,
    FLAG_DIRCACHE,
    FLAG_DIRTYNUM,
    FLAG_TRKNUMGEN,
    FLAG_RESURRECTED
)
from rockbox_db_py.utils.struct_helpers import (
    ENDIANNESS_CHAR,
    read_uint32,
    write_uint32,
)


class IndexFileEntry:
    """
    Represents a single entry in the master index file (database_idx.tcd).
    Corresponds to struct index_entry in tagcache.c.
    """

    def __init__(self, tag_seek=None, flag=0):
        # tag_seek should be a list of TAG_COUNT integers
        self.tag_seek = tag_seek if tag_seek is not None else [0] * TAG_COUNT
        self.flag = flag

    @classmethod
    def from_file(cls, f):
        """Reads an IndexFileEntry from a file object."""
        tag_seeks = []
        for _ in range(TAG_COUNT):
            tag_seeks.append(read_uint32(f))

        flag = read_uint32(f)

        return cls(tag_seek=tag_seeks, flag=flag)

    def to_bytes(self):
        """Converts the IndexFileEntry object to its raw byte representation."""
        packed_data = b""
        for seek_val in self.tag_seek:
            packed_data += struct.pack(ENDIANNESS_CHAR + "I", seek_val)

        packed_data += struct.pack(ENDIANNESS_CHAR + "I", self.flag)

        return packed_data

    @property
    def size(self):
        """Returns the total size of the entry in bytes."""
        return (
            TAG_COUNT * 4 + 4
        )  # TAG_COUNT integers (4 bytes each) + 1 flag integer (4 bytes)

    def get_flag_names(self):
        """Returns a list of human-readable flag names set for this entry."""
        names = []
        if self.flag & FLAG_DELETED:
            names.append("DELETED")
        if self.flag & FLAG_DIRCACHE:
            names.append("DIRCACHE")
        if self.flag & FLAG_DIRTYNUM:
            names.append("DIRTYNUM")
        if self.flag & FLAG_TRKNUMGEN:
            names.append("TRKNUMGEN")
        if self.flag & FLAG_RESURRECTED:
            names.append("RESURRECTED")
        return names

    def get_dircache_idx(self):
        """Extracts the dircache index from the higher 16 bits of the flag."""
        return (self.flag >> 16) & 0x0000FFFF if (self.flag & FLAG_DIRCACHE) else None

    def get_tag_value(self, tag_index):
        """
        Retrieves the tag's value. For FILE_TAG_INDICES, this is an offset.
        For EMBEDDED_TAG_INDICES, this is the direct numeric value.
        """
        if tag_index < 0 or tag_index >= TAG_COUNT:
            raise IndexError(f"Tag index {tag_index} out of bounds.")
        return self.tag_seek[tag_index]

    def __repr__(self):
        tag_seek_str = ", ".join(
            [f"{TAG_TYPES[i]}={self.tag_seek[i]}" for i in range(TAG_COUNT)]
        )
        return (
            f"IndexFileEntry(tag_seek=[{tag_seek_str}], flag={hex(self.flag)}, "
            f"flags={self.get_flag_names()})"
        )
