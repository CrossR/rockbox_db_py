# src/rockbox_db_py/classes/index_file_entry.py

import struct
from typing import Dict, Optional, List, Union

from rockbox_db_py.classes.tag_file import TagFile
from rockbox_db_py.classes.tag_file_entry import TagFileEntry
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
    read_uint32,
    ENDIANNESS_CHAR,
)


class IndexFileEntry:
    """
    Models a single entry in the master index file (database_idx.tcd).

    Each entry links a specific audio track to its various tag values.
    For file-based tags (e.g., artist, title), it stores an offset into a TagFile.
    For embedded numeric tags (e.g., year, bitrate), it stores the value directly.
    """

    def __init__(
        self, tag_seek: Optional[List[Union[int, TagFileEntry]]] = None, flag: int = 0
    ):
        # tag_seek is a list of TAG_COUNT values. During loading/writing, these are int offsets/values.
        # During modification, they might temporarily hold TagFileEntry objects for resolution.
        self.tag_seek: List[Union[int, TagFileEntry]] = (
            tag_seek if tag_seek is not None else [0] * TAG_COUNT
        )

        # Status flags for the entry (e.g., DELETED, DIRTYNUM).
        self.flag: int = flag

        # Reference to loaded TagFile objects for resolving string tags.
        self._loaded_tag_files: Dict[int, TagFile] = {}

    @classmethod
    def from_file(cls, f, loaded_tag_files: Optional[Dict[int, TagFile]] = None):
        """
        Reads an IndexFileEntry from a file object.

        Args:
            f: File object, positioned at the start of an entry.
            loaded_tag_files: Dictionary of loaded TagFile objects for resolving string tags.

        Returns:
            A new IndexFileEntry instance.
        """
        tag_seeks: List[int] = []
        # Read TAG_COUNT 4-byte integers for tag_seek values.
        for _ in range(TAG_COUNT):
            tag_seeks.append(read_uint32(f))

        # Read the 4-byte flag.
        flag: int = read_uint32(f)

        instance = cls(tag_seek=tag_seeks, flag=flag)
        if loaded_tag_files is not None:
            instance._loaded_tag_files = loaded_tag_files
        return instance

    def to_bytes(self) -> bytes:
        """
        Converts the IndexFileEntry object to its raw byte representation for disk.
        Ensures all tag_seek values are numerical offsets/values before packing.
        """
        packed_data: bytes = b""
        # Pack each tag_seek value.
        for seek_val in self.tag_seek:
            # tag_seek should contain only integers (offsets or raw values) at this point.
            if not isinstance(seek_val, int):
                raise ValueError(
                    f"Tag seek value is not an integer: {seek_val}. "
                    "Ensure finalize_index_for_write is called before to_bytes."
                )
            packed_data += struct.pack(ENDIANNESS_CHAR + "I", seek_val)

        # Pack the flag.
        packed_data += struct.pack(ENDIANNESS_CHAR + "I", self.flag)

        return packed_data

    @property
    def size(self) -> int:
        """
        Returns the total byte size of this IndexFileEntry on disk.
        Calculated as (TAG_COUNT * 4 bytes for tag_seek) + (4 bytes for flag).
        """
        return TAG_COUNT * 4 + 4

    def get_flag_names(self) -> List[str]:
        """Returns a list of human-readable names for flags set on this entry."""
        names: List[str] = []
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

    def get_dircache_idx(self) -> Optional[int]:
        """Extracts the dircache index from the higher 16 bits of the flag."""
        return (self.flag >> 16) & 0x0000FFFF if (self.flag & FLAG_DIRCACHE) else None

    def get_parsed_tag_value(self, tag_enum: TagTypeEnum) -> Union[str, int, None]:
        """
        Retrieves the actual parsed value for a given tag type.
        Handles resolving file-based string tags (via offset lookup) and embedded numeric tags.

        Args:
            tag_enum: The TagTypeEnum member representing the desired tag.

        Returns:
            The resolved string, integer value, or None if not found/defined.
        """
        if not isinstance(tag_enum, TagTypeEnum):
            raise ValueError(f"Expected TagTypeEnum, got {type(tag_enum).__name__}")

        tag_index: int = tag_enum.value

        if tag_index < 0 or tag_index >= TAG_COUNT:
            raise IndexError(
                f"Tag index {tag_index} out of range. Must be between 0 and {TAG_COUNT - 1}."
            )

        seek_value: Union[int, TagFileEntry] = self.tag_seek[tag_index]

        # If seek_value is a TagFileEntry object (used during modification phase), return its data directly.
        if isinstance(seek_value, TagFileEntry):
            return seek_value.tag_data

        # For file-based tags, resolve the integer offset to a string.
        if tag_index in FILE_TAG_INDICES:
            # 0xFFFFFFFF is the sentinel for no data for string tags.
            if seek_value == 0xFFFFFFFF:
                return None

            # Attempt to resolve the offset to an entry in the corresponding TagFile.
            tag_file_type: Optional[RockboxDBFileType] = None
            try:
                tag_file_type = RockboxDBFileType.from_tag_index(tag_index)
            except ValueError:
                # Should not happen if FILE_TAG_INDICES and RockboxDBFileType are in sync.
                pass

            if tag_file_type and tag_file_type.tag_index in self._loaded_tag_files:
                tag_file_obj: "TagFile" = self._loaded_tag_files[
                    tag_file_type.tag_index
                ]
                tag_file_entry: Optional[TagFileEntry] = (
                    tag_file_obj.get_entry_by_offset(seek_value)
                )
                if tag_file_entry:
                    return tag_file_entry.tag_data

            # TagFile not loaded or entry not found at offset.
            return None

        else:
            # 0 is common for undefined numeric tags.
            if seek_value == 0:
                return None
            return seek_value

    def __getattr__(self, name: str) -> Union[str, int, List[int], None]:
        """
        Enables attribute-like access (e.g., entry.artist) for tag values.
        It calls get_parsed_tag_value internally.
        """
        # Allow direct access to standard instance properties.
        if name in ["tag_seek", "flag", "_loaded_tag_files", "size"]:
            return object.__getattribute__(self, name)

        # Convert the attribute name to a TagTypeEnum member for lookup.
        try:
            tag_enum: TagTypeEnum = TagTypeEnum[name]
        except KeyError:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}' (not a recognized tag)."
            )

        return self.get_parsed_tag_value(tag_enum)

    def __repr__(self) -> str:
        """Provides a developer-friendly string representation."""
        return f"IndexFileEntry(flag={hex(self.flag)}, flags={self.get_flag_names()})"
