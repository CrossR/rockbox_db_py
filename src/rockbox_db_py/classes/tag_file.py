# src/rockbox_db_py/classes/tag_file.py
import os

from rockbox_db_py.utils.defs import TAG_TYPES
from rockbox_db_py.classes.db_file_type import RockboxDBFileType
from rockbox_db_py.utils.struct_helpers import read_uint32, write_uint32
from rockbox_db_py.classes.tag_file_entry import TagFileEntry


class TagFile:
    """
    Represents an entire tag data file (e.g., database_0.tcd for artist).
    Corresponds to struct tagcache_header in tagcache.c for its header.
    """

    def __init__(self, db_file_type: RockboxDBFileType):
        # Validate that this is a tag data file type
        if db_file_type.tag_index is None:
            raise ValueError(
                "RockboxDBFileType must be a tag data file type (e.g., ARTIST, FILENAME) for TagFile."
            )

        self.db_file_type = db_file_type
        self.magic = self.db_file_type.magic
        self.datasize = 0
        self.entry_count = 0
        self.entries = []

        # Dictionary to map offsets to TagFileEntry objects for quick lookup
        self.entries_by_offset = {}
        # Dictionary to map tag data strings to lists of TagFileEntry objects
        self.entries_by_tag_data = {}

    @classmethod
    def from_file(cls, filepath: str):
        """
        Reads a TagFile from a specified file path.
        Determines the file type from the path to correctly initialize.
        """
        filename = os.path.basename(filepath)
        db_file_type = RockboxDBFileType.from_filename(filename)

        # Validate that it's actually a tag data file, not the index file
        if db_file_type.tag_index is None:
            raise ValueError(f"File '{filename}' is not a tag data file.")

        with open(filepath, "rb") as f:
            # Read header
            magic_read = read_uint32(f)
            datasize_read = read_uint32(f)
            entry_count_read = read_uint32(f)

            tag_file = cls(db_file_type=db_file_type)

            if magic_read != tag_file.magic:
                raise ValueError(
                    f"Invalid magic number in {filepath}. Expected {hex(tag_file.magic)}, got {hex(magic_read)}"
                )

            tag_file.magic = magic_read
            tag_file.datasize = datasize_read
            tag_file.entry_count = entry_count_read

            # Read entries
            for i in range(tag_file.entry_count):
                entry = TagFileEntry.from_file(
                    f, is_filename_db=tag_file.db_file_type.is_filename_db
                )
                tag_file.entries.append(entry)
                tag_file.entries_by_tag_data[entry.tag_data.casefold()] = entry
                # Store the entry in the dictionary by its offset for quick lookup
                if entry.offset_in_file is not None:
                    tag_file.entries_by_offset[entry.offset_in_file] = entry

        return tag_file

    def to_file(self, filepath: str):
        """
        Writes the TagFile object to a specified file path.
        Recalculates datasize and entry_count before writing.
        """
        self.entry_count = len(self.entries)
        self.datasize = sum(entry.size for entry in self.entries)

        # Clear and rebuild the lookup dictionaries
        self.entries_by_offset = {}
        self.entries_by_tag_data = {}

        if self.db_file_type != RockboxDBFileType.FILENAME:
            self.entries.sort(key=lambda e: e.tag_data.lower())

        with open(filepath, "wb") as f:
            # Write header: magic, datasize, entry_count
            write_uint32(f, self.magic)
            write_uint32(f, self.datasize)
            write_uint32(f, self.entry_count)

            # Write entries
            # We track current position to update offset_in_file for newly added entries
            current_offset = f.tell()  # Start after header (12 bytes)
            for entry in self.entries:
                entry.is_filename_db = self.db_file_type.is_filename_db
                entry.offset_in_file = current_offset
                entry_bytes = entry.to_bytes()
                f.write(entry_bytes)

                # Update current_offset for the next entry
                current_offset += len(entry_bytes)

                # Also update our internal lookup for consistency if needed
                # after write
                self.entries_by_offset[entry.offset_in_file] = entry
                self.entries_by_tag_data[entry.tag_data.casefold()] = entry

    def get_entry_by_offset(self, offset: int) -> TagFileEntry | None:
        """Retrieves a TagFileEntry by its byte offset in the file."""
        return self.entries_by_offset.get(offset)

    def get_entry_by_tag_data(self, tag_data: str) -> TagFileEntry | None:
        """Retrieves a TagFileEntry by its tag data string."""
        return self.entries_by_tag_data.get(tag_data.casefold())

    def add_entry(self, entry: TagFileEntry) -> TagFileEntry:
        entry_tag_data_casefolded = entry.tag_data.casefold()
        if entry_tag_data_casefolded not in self.entries_by_tag_data:
            self.entries.append(entry)
            self.entries_by_tag_data[entry_tag_data_casefolded] = entry
            return entry
        else:
            existing_canonical_entry = self.entries_by_tag_data[entry_tag_data_casefolded]
            return existing_canonical_entry

    def __repr__(self):
        tag_name = TAG_TYPES[self.db_file_type.tag_index]
        return (
            f"TagFile(type='{tag_name}' ({self.db_file_type.filename}), magic={hex(self.magic)}, "
            f"datasize={self.datasize}, entry_count={self.entry_count}, "
            f"is_filename_db={self.db_file_type.is_filename_db}, "
            f"entries_len={len(self.entries)}, lookup_len={len(self.entries_by_offset)})"
        )

    def __len__(self):
        return len(self.entries)
