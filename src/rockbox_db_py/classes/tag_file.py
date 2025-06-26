# tag_file.py
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
        if db_file_type.tag_index is None:
            raise ValueError(
                "RockboxDBFileType must be a tag data file type (e.g., ARTIST, FILENAME) for TagFile."
            )

        self.db_file_type = db_file_type
        self.magic = self.db_file_type.magic
        self.datasize = 0
        self.entry_count = 0
        self.entries = []
        self.entries_by_offset = {} # Dict to map offsets to TagFileEntry

    @classmethod
    def from_file(cls, filepath: str):
        filename = os.path.basename(filepath)
        db_file_type = RockboxDBFileType.from_filename(filename)

        if db_file_type.tag_index is None:
            raise ValueError(f"File '{filename}' is not a tag data file.")

        tag_file = cls(db_file_type=db_file_type)

        with open(filepath, 'rb') as f:
            magic_read = read_uint32(f)
            datasize_read = read_uint32(f)
            entry_count_read = read_uint32(f)

            if magic_read != tag_file.magic:
                raise ValueError(f"Invalid magic number in {filepath}. Expected {hex(tag_file.magic)}, got {hex(magic_read)}")

            tag_file.magic = magic_read
            tag_file.datasize = datasize_read
            tag_file.entry_count = entry_count_read

            for _ in range(tag_file.entry_count):
                entry = TagFileEntry.from_file(f, is_filename_db=tag_file.db_file_type.is_filename_db)
                tag_file.entries.append(entry)
                # Store the entry in the dictionary by its offset for quick lookup
                if entry.offset_in_file is not None:
                    tag_file.entries_by_offset[entry.offset_in_file] = entry

        return tag_file

    def to_file(self, filepath: str):
        self.entry_count = len(self.entries)
        self.datasize = sum(entry.size for entry in self.entries)

        with open(filepath, 'wb') as f:
            write_uint32(f, self.magic)
            write_uint32(f, self.datasize)
            write_uint32(f, self.entry_count)

            for entry in self.entries:
                entry.is_filename_db = self.db_file_type.is_filename_db
                f.write(entry.to_bytes())
                # TODO:  When writing, we might want to update `offset_in_file`
                # for the entries if we want to use this TagFile object
                # immediately after writing without re-reading.
                # This could be added here: entry.offset_in_file = f.tell() - entry.size

    def get_entry_by_offset(self, offset: int) -> TagFileEntry | None: # Python 3.10+ type hint
        """Retrieves a TagFileEntry by its byte offset in the file."""
        return self.entries_by_offset.get(offset)

    def add_entry(self, entry: TagFileEntry):
        entry.is_filename_db = self.db_file_type.is_filename_db
        self.entries.append(entry)
        if entry.offset_in_file is not None:
            self.entries_by_offset[entry.offset_in_file] = entry

    def __repr__(self):
        tag_name = TAG_TYPES[self.db_file_type.tag_index]
        return (
            f"TagFile(type='{tag_name}' ({self.db_file_type.filename}), magic={hex(self.magic)}, "
            f"datasize={self.datasize}, entry_count={self.entry_count}, "
            f"is_filename_db={self.db_file_type.is_filename_db}, "
            f"entries_len={len(self.entries)}, lookup_len={len(self.entries_by_offset)})" # Added lookup_len
        )

    def __len__(self):
        return len(self.entries)