# index_file.py
import os
from rockbox_db_py.utils.defs import TAG_MAGIC, TAG_COUNT
from rockbox_db_py.utils.struct_helpers import read_uint32, write_uint32
from index_file_entry import (
    IndexFileEntry,
)  # Assuming index_file_entry.py is in the same directory


class IndexFile:
    """
    Represents the master index file (database_idx.tcd).
    Corresponds to struct master_header in tagcache.c.
    """

    def __init__(self):
        self.magic = TAG_MAGIC
        self.datasize = 0  # Will be calculated upon writing
        self.entry_count = 0  # Will be calculated upon writing
        self.serial = 0
        self.commitid = 0
        self.dirty = 0
        self.entries = []  # List of IndexFileEntry objects

    @classmethod
    def from_file(cls, filepath):
        """
        Reads an IndexFile from a specified file path.
        :param filepath: Path to the database_idx.tcd file.
        """
        index_file = cls()

        with open(filepath, "rb") as f:
            # Read master header
            index_file.magic = read_uint32(f)
            index_file.datasize = read_uint32(f)
            index_file.entry_count = read_uint32(f)
            index_file.serial = read_uint32(f)
            index_file.commitid = read_uint32(f)
            index_file.dirty = read_uint32(f)

            if index_file.magic != TAG_MAGIC:
                raise ValueError(
                    f"Invalid magic number in {filepath}. Expected {TAG_MAGIC}, got {index_file.magic}"
                )

            # Read entries
            for _ in range(index_file.entry_count):
                entry = IndexFileEntry.from_file(f)
                index_file.entries.append(entry)

        return index_file

    def to_file(self, filepath):
        """
        Writes the IndexFile object to a specified file path.
        Recalculates datasize and entry_count before writing.
        """
        self.entry_count = len(self.entries)
        # Datasize calculation: header size (6 uint32s) + sum of all entry sizes
        self.datasize = (6 * 4) + sum(entry.size for entry in self.entries)

        with open(filepath, "wb") as f:
            # Write master header
            write_uint32(f, self.magic)
            write_uint32(f, self.datasize)
            write_uint32(f, self.entry_count)
            write_uint32(f, self.serial)
            write_uint32(f, self.commitid)
            write_uint32(f, self.dirty)

            # Write entries
            for entry in self.entries:
                f.write(entry.to_bytes())

    def add_entry(self, entry: IndexFileEntry):
        """Adds an IndexFileEntry to this IndexFile."""
        self.entries.append(entry)

    def __repr__(self):
        return (
            f"IndexFile(magic={hex(self.magic)}, datasize={self.datasize}, "
            f"entry_count={self.entry_count}, serial={self.serial}, "
            f"commitid={self.commitid}, dirty={bool(self.dirty)}, "
            f"entries_len={len(self.entries)})"
        )

    def __len__(self):
        return len(self.entries)
