# File to represent the overall Rockbox index DB file.

import os
from rockbox_db_py.utils.struct_helpers import read_uint32, write_uint32
from rockbox_db_py.classes.index_file_entry import IndexFileEntry
from rockbox_db_py.classes.db_file_type import RockboxDBFileType
from rockbox_db_py.classes.tag_file import TagFile

from typing import List, Dict, Optional


class IndexFile:
    """
    Represents the master index file (database_idx.tcd).
    Corresponds to struct master_header in tagcache.c.
    """

    def __init__(self):
        self.db_file_type = RockboxDBFileType.INDEX
        self.magic = self.db_file_type.magic # Magic number from the enum
        self.datasize = 0 # Will be calculated upon writing
        self.entry_count = 0 # Will be calculated upon writing
        self.serial = 0 # Serial from master header
        self.commitid = 0 # Commit ID from master header
        self.dirty = 0 # Dirty flag from master header
        self.entries = [] # List of IndexFileEntry objects
        self._loaded_tag_files = {} # Holds references to loaded TagFile objects

    @classmethod
    def from_file(cls, filepath: str, tag_files_to_load: Optional[List[RockboxDBFileType]] = None):
        """
        Reads an IndexFile from a specified file path, and optionally loads associated TagFiles.
        :param filepath: Path to the database_idx.tcd file.
        :param tag_files_to_load: An optional list of RockboxDBFileType enum members
                                  specifying which tag files to load. If None, all known
                                  tag files will be loaded.
        """
        filename = os.path.basename(filepath)
        db_directory = os.path.dirname(filepath)

        if filename != RockboxDBFileType.INDEX.filename:
            raise ValueError(
                f"Expected {RockboxDBFileType.INDEX.filename}, got {filename}"
            )

        index_file = cls()

        # Work out which tag files to load, assuming it is all of them if not specified.
        if tag_files_to_load is None:
            all_tag_file_types = [
                ft
                for ft in RockboxDBFileType
                if ft != RockboxDBFileType.INDEX and ft.tag_index is not None
            ]
            tag_files_to_load = all_tag_file_types

        # Actually load the required tag files.
        for db_type in tag_files_to_load:
            tag_filepath = os.path.join(db_directory, db_type.filename)
            if not os.path.exists(tag_filepath):
                # Optionally warn and skip, or raise error. Current code raises.
                raise FileNotFoundError(
                    f"Tag file {db_type.filename} not found at {tag_filepath}"
                )

            try:
                tag_file = TagFile.from_file(tag_filepath)
                index_file._loaded_tag_files[db_type.tag_index] = tag_file
                # Log internal loading: Logged by `TagFile.from_file` and `IndexFile.from_file` in print_db.py
            except Exception as e:
                raise RuntimeError(
                    f"Failed to load tag file {db_type.filename}: {e}"
                ) from e

        with open(filepath, "rb") as f:
            # Read master header
            magic_read = read_uint32(f)
            datasize_read = read_uint32(f)
            entry_count_read = read_uint32(f)
            index_file.serial = read_uint32(f)
            index_file.commitid = read_uint32(f)
            index_file.dirty = read_uint32(f)

            if magic_read != index_file.magic:
                raise ValueError(
                    f"Invalid magic number in {filepath}. Expected {hex(index_file.magic)}, got {hex(magic_read)}"
                )

            index_file.magic = magic_read
            index_file.datasize = datasize_read
            index_file.entry_count = entry_count_read

            # Read entries, passing the loaded_tag_files
            for _ in range(index_file.entry_count):
                entry = IndexFileEntry.from_file(
                    f, loaded_tag_files=index_file._loaded_tag_files
                )
                index_file.entries.append(entry)

        return index_file

    def to_file(self, filepath: str):
        self.entry_count = len(self.entries)

        # Calculate the total size of the index file.
        calculated_total_db_size = (6 * 4)
        calculated_total_db_size += sum(entry.size for entry in self.entries)

        # Add the sizes of all associated TagFiles, EXCLUDING the FILENAME tag file
        for tag_file_obj in self._loaded_tag_files.values():
            if tag_file_obj.db_file_type == RockboxDBFileType.FILENAME:
                continue
            calculated_total_db_size += tag_file_obj.datasize

        self.datasize = calculated_total_db_size


        with open(filepath, "wb") as f:
            write_uint32(f, self.magic)
            write_uint32(f, self.datasize)
            write_uint32(f, self.entry_count)
            write_uint32(f, self.serial)
            write_uint32(f, self.commitid)
            write_uint32(f, self.dirty)

            for entry in self.entries:
                f.write(entry.to_bytes())

    def add_entry(self, entry: IndexFileEntry):
        """Adds an IndexFileEntry to this IndexFile."""
        self.entries.append(entry)
        # Ensure new entries also get the loaded_tag_files reference
        entry._loaded_tag_files = self._loaded_tag_files

    # Property to allow external access to loaded tag files without directly exposing _loaded_tag_files
    @property
    def loaded_tag_files(self) -> Dict[int, TagFile]:
        """Returns the dictionary of loaded TagFile objects (tag_index: TagFile)."""
        return self._loaded_tag_files

    def __repr__(self):
        return (
            f"IndexFile(type='{self.db_file_type.filename}', magic={hex(self.magic)}, "
            f"datasize={self.datasize}, entry_count={self.entry_count}, serial={self.serial}, "
            f"commitid={self.commitid}, dirty={bool(self.dirty)}, "
            f"entries_len={len(self.entries)})"
        )

    def __len__(self):
        return len(self.entries)