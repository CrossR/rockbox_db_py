# An individual entry of the Rockbox database index file.

import struct

from rockbox_db_py.classes.db_file_type import RockboxDBFileType
from rockbox_db_py.utils.defs import (
    TagTypeEnum,
    TAG_COUNT,
    FILE_TAG_INDICES,
    FLAG_DELETED,
    FLAG_DIRCACHE,
    FLAG_DIRTYNUM,
    FLAG_TRKNUMGEN,
    FLAG_RESURRECTED,
)
from rockbox_db_py.utils.struct_helpers import (
    ENDIANNESS_CHAR,
    read_uint32,
)


class IndexFileEntry:
    """
    Represents a single entry in the master index file (database_idx.tcd).
    Corresponds to struct index_entry in tagcache.c.
    """

    def __init__(self, tag_seek=None, flag=0):
        self.tag_seek = tag_seek if tag_seek is not None else [0] * TAG_COUNT
        self.flag = flag
        self._loaded_tag_files = {}

    @classmethod
    def from_file(cls, f, loaded_tag_files=None):
        """Reads an IndexFileEntry from a file object."""
        tag_seeks = []
        for _ in range(TAG_COUNT):
            tag_seeks.append(read_uint32(f))

        flag = read_uint32(f)

        instance = cls(tag_seeks, flag)
        if loaded_tag_files is not None:
            instance._loaded_tag_files = loaded_tag_files
        return instance

    def to_bytes(self):
        """
        Converts the IndexFileEntry object to its raw byte representation.
        Ensures TAG_COUNT tag_seek values are written, followed by the flag.
        """
        packed_data = b""
        # Write TAG_COUNT tag_seek values (each 4 bytes)
        for seek_val in self.tag_seek:
            packed_data += struct.pack(ENDIANNESS_CHAR + 'I', seek_val)

        # Write the flag (4 bytes)
        packed_data += struct.pack(ENDIANNESS_CHAR + 'I', self.flag)

        return packed_data

    @property
    def size(self):
        """
        Returns the total size of the entry in bytes.
        Calculated as (TAG_COUNT * 4 bytes for tag_seek) + (4 bytes for flag).
        """
        return TAG_COUNT * 4 + 4

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

    def get_parsed_tag_value(self, tag_enum: TagTypeEnum):
        """
        Retrieves the actual parsed value for a given tag type.
        Handles both file-based string tags (via offset lookup) and embedded numeric tags.
        """
        if not isinstance(tag_enum, TagTypeEnum):
            raise ValueError(f"Expected TagTypeEnum, got {type(tag_enum).__name__}")

        tag_index = tag_enum.value

        if tag_index < 0 or tag_index >= TAG_COUNT:
            raise IndexError(
                f"Tag index {tag_index} out of range. Must be between 0 and {TAG_COUNT - 1}."
            )

        seek_value = self.tag_seek[tag_index]

        if tag_index in FILE_TAG_INDICES:
            # Sentinel for no data (0xFFFFFFFF means no tag data)
            if seek_value == 0xFFFFFFFF:
                return None

            tag_file_type = None
            try:
                tag_file_type = RockboxDBFileType.from_tag_index(tag_index)
            except ValueError:
                pass

            if tag_file_type and tag_file_type.tag_index in self._loaded_tag_files:
                tag_file_obj = self._loaded_tag_files[tag_file_type.tag_index]
                tag_file_entry = tag_file_obj.get_entry_by_offset(seek_value)
                if tag_file_entry:
                    return tag_file_entry.tag_data

            return None # Tag file not loaded or entry not found at offset

        else: # Embedded numeric tag
            if seek_value == 0: # Common for undefined numeric tags
                return None
            return seek_value

    def __getattr__(self, name):
        # Allow direct access to standard properties
        if name in ["tag_seek", "flag", "_loaded_tag_files", "size"]:
            return object.__getattribute__(self, name)

        # Convert the name to an enum before passing it over.
        try:
            tag_enum = TagTypeEnum[name]
        except KeyError:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            )

        return self.get_parsed_tag_value(tag_enum)

    def __repr__(self):
        return (
            f"IndexFileEntry(flag={hex(self.flag)}, " f"flags={self.get_flag_names()})"
        )