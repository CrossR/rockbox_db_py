# tag_file.py
import os
from rockbox_db_py.utils.defs import TAG_TYPES
from rockbox_db_py.classes.db_file_type import RockboxDBFileType
from rockbox_db_py.utils.struct_helpers import read_uint32, write_uint32
from tag_file_entry import TagFileEntry


class TagFile:
    """
    Represents an entire tag data file (e.g., database_0.tcd for artist).
    Corresponds to struct tagcache_header in tagcache.c for its header.
    """

    def __init__(self, db_file_type: RockboxDBFileType):
        if db_file_type.tag_index is None:
            raise ValueError(
                "RockboxDBFileType must be a tag data file type (e.g., ARTIST, FILENAME) for TagFile."
            )

        self.db_file_type = db_file_type
        self.magic = self.db_file_type.magic
        self.datasize = 0
        self.entry_count = 0
        self.entries = []

    @classmethod
    def from_file(cls, filepath: str):
        """
        Reads a TagFile from a specified file path.
        Determines the file type from the path to correctly initialize.
        :param filepath: Path to the .tcd file.
        """
        # Determine the file type based on the filename
        filename = os.path.basename(filepath)
        db_file_type = RockboxDBFileType.from_filename(filename)

        # Validate that it's actually a tag data file, not the index file
        if db_file_type.tag_index is None:
            raise ValueError(f"File '{filename}' is not a tag data file.")

        tag_file = cls(db_file_type=db_file_type)  # Initialize with the enum member

        with open(filepath, "rb") as f:
            # Read header
            magic_read = read_uint32(f)
            datasize_read = read_uint32(f)
            entry_count_read = read_uint32(f)

            if magic_read != tag_file.magic:  # Use magic from the enum
                raise ValueError(
                    f"Invalid magic number in {filepath}. Expected {hex(tag_file.magic)}, got {hex(magic_read)}"
                )

            tag_file.magic = magic_read  # Update in case of foreign endianness support in future, or just for consistency
            tag_file.datasize = datasize_read
            tag_file.entry_count = entry_count_read

            # Read entries
            for _ in range(tag_file.entry_count):
                # Use the new property directly
                entry = TagFileEntry.from_file(
                    f, is_filename_db=tag_file.db_file_type.is_filename_db
                )
                tag_file.entries.append(entry)

        return tag_file

    def to_file(self, filepath: str):
        """
        Writes the TagFile object to a specified file path.
        Recalculates datasize and entry_count before writing.
        """
        self.entry_count = len(self.entries)

        # Calculate datasize by summing up the sizes of all entries
        self.datasize = sum(entry.size for entry in self.entries)

        with open(filepath, "wb") as f:
            # Write header
            write_uint32(f, self.magic)
            write_uint32(f, self.datasize)
            write_uint32(f, self.entry_count)

            # Write entries
            for entry in self.entries:
                # Use the new property directly
                entry.is_filename_db = self.db_file_type.is_filename_db
                f.write(entry.to_bytes())

    def add_entry(self, entry: TagFileEntry):
        """Adds a TagFileEntry to this TagFile."""
        # Ensure the entry's filename db status is consistent with the TagFile
        entry.is_filename_db = self.db_file_type.is_filename_db
        self.entries.append(entry)

    def __repr__(self):
        # Use the tag_index property from the enum for display
        tag_name = (
            TAG_TYPES[self.db_file_type.tag_index]
            if self.db_file_type.tag_index is not None
            else "Unknown"
        )
        return (
            f"TagFile(type='{tag_name}' ({self.db_file_type.name}), magic={hex(self.magic)}, "
            f"datasize={self.datasize}, entry_count={self.entry_count}, "
            f"is_filename_db={self.db_file_type.is_filename_db}, entries_len={len(self.entries)})"
        )

    def __len__(self):
        return len(self.entries)
