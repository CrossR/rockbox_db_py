# index_file.py
# src/rockbox_db_py/classes/index_file.py
import os
from rockbox_db_py.utils.defs import TAG_MAGIC, TAG_COUNT # TAG_TYPES is now imported by IndexFileEntry if needed for __repr__
from rockbox_db_py.utils.struct_helpers import read_uint32, write_uint32
from .index_file_entry import IndexFileEntry
from .db_file_type import RockboxDBFileType
# from rockbox_db_py.classes.tag_file import TagFile # Potentially useful for type hinting in load_rockbox_database

class IndexFile:
    """
    Represents the master index file (database_idx.tcd).
    Corresponds to struct master_header in tagcache.c.
    """
    def __init__(self):
        self.db_file_type = RockboxDBFileType.INDEX
        self.magic = self.db_file_type.magic
        self.datasize = 0
        self.entry_count = 0
        self.serial = 0
        self.commitid = 0
        self.dirty = 0
        self.entries  = []
        self._loaded_tag_files = {}

    @classmethod
    def from_file(cls, filepath: str, loaded_tag_files=None):
        """
        Reads an IndexFile from a specified file path.
        :param filepath: Path to the database_idx.tcd file.
        :param loaded_tag_files: A dictionary of loaded TagFile objects (tag_index: TagFile).
                                 This will be passed to each IndexFileEntry.
        """
        filename = os.path.basename(filepath)
        if filename != RockboxDBFileType.INDEX.filename:
            raise ValueError(f"File '{filename}' is not the expected master index file ({RockboxDBFileType.INDEX.filename}).")

        index_file = cls()
        if loaded_tag_files is not None:
            index_file._loaded_tag_files = loaded_tag_files # Set the reference

        with open(filepath, 'rb') as f:
            # Read master header
            magic_read = read_uint32(f)
            datasize_read = read_uint32(f)
            entry_count_read = read_uint32(f)
            index_file.serial = read_uint32(f)
            index_file.commitid = read_uint32(f)
            index_file.dirty = read_uint32(f)

            if magic_read != index_file.magic:
                raise ValueError(f"Invalid magic number in {filepath}. Expected {hex(index_file.magic)}, got {hex(magic_read)}")

            index_file.magic = magic_read
            index_file.datasize = datasize_read
            index_file.entry_count = entry_count_read

            # Read entries, passing the loaded_tag_files
            for _ in range(index_file.entry_count):
                entry = IndexFileEntry.from_file(f, loaded_tag_files=index_file._loaded_tag_files)
                index_file.entries.append(entry)

        return index_file

    def to_file(self, filepath: str):
        """
        Writes the IndexFile object to a specified file path.
        Recalculates datasize and entry_count before writing.
        """
        self.entry_count = len(self.entries)
        self.datasize = (6 * 4) + sum(entry.size for entry in self.entries)

        with open(filepath, 'wb') as f:
            write_uint32(f, self.magic)
            write_uint32(f, self.datasize)
            write_uint32(f, self.entry_count)
            write_uint32(f, self.serial)
            write_uint32(f, self.commitid)
            write_uint32(f, self.dirty)

            for entry in self.entries:
                f.write(entry.to_bytes())

    def add_entry(self, entry: IndexFileEntry):
        self.entries.append(entry)
        entry._loaded_tag_files = self._loaded_tag_files

    def __repr__(self):
        return (
            f"IndexFile(type='{self.db_file_type.filename}', magic={hex(self.magic)}, "
            f"datasize={self.datasize}, entry_count={self.entry_count}, serial={self.serial}, "
            f"commitid={self.commitid}, dirty={bool(self.dirty)}, "
            f"entries_len={len(self.entries)})"
        )

    def __len__(self):
        return len(self.entries)