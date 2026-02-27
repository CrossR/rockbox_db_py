# tag_file.py
#
# The represents one of the Rockbox Tag Files (database_X.tcd),
# which contains a collection of TagFileEntry objects.
#
# This class handles reading from and writing to these files,
# managing their header, and the list of TagFileEntry objects they contain.

import os
from typing import Optional, List, Dict

from rockbox_db_py.utils.defs import TAG_TYPES
from rockbox_db_py.classes.db_file_type import RockboxDBFileType
from rockbox_db_py.utils.struct_helpers import read_uint32, write_uint32
from rockbox_db_py.classes.tag_file_entry import TagFileEntry


class TagFile:
    """
    Models a Rockbox Tag File (database_X.tcd), which stores collections of tag data entries.
    This class handles reading from and writing to these files, managing their header
    and the list of TagFileEntry objects they contain.
    """

    def __init__(self, db_file_type: RockboxDBFileType):
        # Ensure this TagFile instance is associated with a valid tag data file type.
        if db_file_type.tag_index is None:
            raise ValueError(
                "RockboxDBFileType must be a tag data file type (e.g., ARTIST, FILENAME) for TagFile."
            )

        self.db_file_type: RockboxDBFileType = db_file_type
        self.duplicates_possible: bool = db_file_type.duplicates_possible
        self.magic: int = self.db_file_type.magic

        # Total size of entries (excluding header), calculated on write.
        self.datasize: int = 0
        # Number of TagFileEntry objects, calculated on write.
        self.entry_count: int = 0
        # List of all TagFileEntry objects.
        self.entries: List[TagFileEntry] = []
        # Map offsets to TagFileEntry objects for quick lookup by byte offset.
        self.entries_by_offset: Dict[int, TagFileEntry] = {}
        # Map case-folded tag data strings to their canonical (unique) TagFileEntry object.
        self.entries_by_tag_data: Dict[str, TagFileEntry] = {}

    @classmethod
    def from_file(cls, filepath: str) -> "TagFile":
        """
        Reads a TagFile from a specified file path, populating its entries and lookups.

        Args:
            filepath: Path to the .tcd file.

        Returns:
            A new TagFile instance.

        Raises:
            EOFError: If the end of the file is reached unexpectedly.
        """
        filename: str = os.path.basename(filepath)
        db_file_type: RockboxDBFileType = RockboxDBFileType.from_filename(filename)
        duplicates_possible: bool = db_file_type.duplicates_possible

        if db_file_type.tag_index is None:
            raise ValueError(f"File '{filename}' is not a tag data file.")

        tag_file: "TagFile" = cls(db_file_type=db_file_type)

        with open(filepath, "rb") as f:
            # Read TagFile header.
            magic_read: int = read_uint32(f)
            datasize_read: int = read_uint32(f)
            entry_count_read: int = read_uint32(f)

            if magic_read != tag_file.magic:
                raise ValueError(
                    f"Invalid magic number in {filepath}. Expected {hex(tag_file.magic)}, got {hex(magic_read)}"
                )

            tag_file.magic = magic_read
            tag_file.datasize = datasize_read
            tag_file.entry_count = entry_count_read

            # This ensures `tag_file.entries` matches the exact `entry_count` from the header.
            # Deduplication for functional purposes will happen in `add_entry` or during processing.
            for _ in range(tag_file.entry_count):
                entry: TagFileEntry = TagFileEntry.from_file(
                    f, db_file_type=db_file_type
                )

                tag_file.add_entry(entry)

                # Store entry in entries_by_offset by its original offset.
                # This map needs to contain ALL entries read from the file.
                if entry.offset_in_file is not None:
                    tag_file.entries_by_offset[entry.offset_in_file] = entry

                # Store entry in entries_by_tag_data as canonical lookup.
                key = entry.key if duplicates_possible else entry.tag_data
                tag_file.entries_by_tag_data[key] = entry
        return tag_file

    def to_file(self, filepath: str, sort_map: Optional[Dict[str, str]] = None) -> None:
        """
        Writes the TagFile object to a specified file path.
        Recalculates datasize and entry_count before writing based on current entries.
        """
        self.entry_count = len(self.entries)
        self.datasize = sum(entry.size for entry in self.entries)

        # Clear and rebuild lookup dictionaries to reflect the state of entries being written.
        self.entries_by_offset = {}
        self.entries_by_tag_data = {}

        # Sort entries before writing if the TagFile type expects it (e.g., genre, artist).
        # However, filename databases are not sorted by tag data.
        if self.db_file_type != RockboxDBFileType.FILENAME:
            # If a sort_map is provided, use it to sort entries by the mapped tag data.
            # This allows for custom sorting based on external criteria, or simply breaking
            # ties in a consistent way.
            if sort_map:
                self.entries.sort(key=lambda e: sort_map.get(e.tag_data, e.tag_data))
            else:
                # Sort entries by tag_data (case-insensitive)
                self.entries.sort(key=lambda e: e.tag_data.lower())

        with open(filepath, "wb") as f:
            # Write TagFile header.
            write_uint32(f, self.magic)
            write_uint32(f, self.datasize)
            write_uint32(f, self.entry_count)

            # Write each TagFileEntry.
            current_offset: int = f.tell()
            for entry in self.entries:
                entry.is_filename_db = self.db_file_type.is_filename_db

                # Update entry's offset to its new position in this file.
                entry.offset_in_file = current_offset

                entry_bytes: bytes = entry.to_bytes()
                f.write(entry_bytes)

                current_offset += len(entry_bytes)
                key = entry.key if self.duplicates_possible else entry.tag_data

                # Update internal lookups with the newly assigned offset and data.
                self.entries_by_offset[entry.offset_in_file] = entry
                self.entries_by_tag_data[key] = entry

    def get_entry_by_offset(self, offset: int) -> Optional[TagFileEntry]:
        """Retrieves a TagFileEntry by its byte offset in the file."""
        return self.entries_by_offset.get(offset)

    def get_entry_by_tag_data(self, tag_data: str) -> Optional[TagFileEntry]:
        """
        Retrieves a TagFileEntry by its tag data string (case-insensitive).
        Returns the canonical entry (the last one loaded/written for that string) if found.
        """
        return self.entries_by_tag_data.get(tag_data)

    def add_entry(self, entry: TagFileEntry) -> TagFileEntry:
        """
        Adds a TagFileEntry to this TagFile, ensuring uniqueness by string content.
        This method is primarily used when building a database from scratch or adding
        new canonical genre strings during modification.
        """
        entry_key: str = entry.tag_data

        if self.duplicates_possible:
            entry_key = entry.key
        else:
            # If duplicates are not allowed, we use the tag_data directly.
            entry_key = entry.tag_data.lower()

        # If the string content is not already in our canonical map, add this entry.
        if entry_key not in self.entries_by_tag_data:
            # Add to the main list of entries (will be sorted/written).
            self.entries.append(entry)
            # Store as the canonical entry for this string.
            self.entries_by_tag_data[entry_key] = entry
            return entry
        else:
            # If the string content already exists, return the existing canonical entry.
            existing_canonical_entry: TagFileEntry = self.entries_by_tag_data[entry_key]
            return existing_canonical_entry

    def __repr__(self) -> str:
        """Provides a developer-friendly string representation of the TagFile object."""
        tag_name: str = TAG_TYPES[self.db_file_type.tag_index]
        return (
            f"TagFile(type='{tag_name}' ({self.db_file_type.filename}), magic={hex(self.magic)}, "
            f"datasize={self.datasize}, entry_count={self.entry_count}, "
            f"is_filename_db={self.db_file_type.is_filename_db}, "
            f"entries_len={len(self.entries)}, lookup_offset_len={len(self.entries_by_offset)}, "
            f"lookup_tagdata_len={len(self.entries_by_tag_data)})"
        )

    def __len__(self) -> int:
        """Returns the number of TagFileEntry objects managed by this TagFile."""
        return len(self.entries)
