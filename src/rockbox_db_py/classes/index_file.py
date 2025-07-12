# index_file.py
#
# Represents the master index file (database_idx.tcd) from Rockbox.
# This file contains a collection of IndexFileEntry objects, each linking
# a specific audio track to its various tag values.
# It also manages the loading of associated TagFile objects for resolving the
# other tag data.

import os
from typing import Optional, List, Dict

from rockbox_db_py.utils.struct_helpers import read_uint32, write_uint32
from rockbox_db_py.classes.index_file_entry import IndexFileEntry
from rockbox_db_py.classes.db_file_type import RockboxDBFileType
from rockbox_db_py.classes.tag_file import TagFile


class IndexFile:
    """
    Models the master index file (database_idx.tcd) from Rockbox.

    This class handles the overall database structure, including its header
    and the collection of IndexFileEntry objects, and manages the loading
    of associated TagFile objects.
    """

    def __init__(self):
        self.db_file_type: RockboxDBFileType = RockboxDBFileType.INDEX
        self.magic: int = self.db_file_type.magic

        self.datasize: int = 0
        self.entry_count: int = 0
        self.serial: int = 0
        self.commitid: int = 1
        self.dirty: int = 0
        self.entries: List[IndexFileEntry] = []
        self._loaded_tag_files: Dict[int, TagFile] = {}

    @classmethod
    def from_file(
        cls, filepath: str, tag_files_to_load: Optional[List[RockboxDBFileType]] = None
    ) -> "IndexFile":
        """
        Reads an IndexFile from a specified file path, and loads associated TagFiles.

        Args:
            filepath: Path to the database_idx.tcd file.
            tag_files_to_load: Optional list of specific TagFile types to load.
                               If None, all known tag files will be loaded.

        Returns:
            A new IndexFile instance.

        Raises:
            ValueError: If the filepath does not point to the master index file.
            FileNotFoundError: If a required TagFile is not found.
            RuntimeError: If a TagFile fails to load.
        """
        filename: str = os.path.basename(filepath)
        db_directory: str = os.path.dirname(filepath)

        if filename != RockboxDBFileType.INDEX.filename:
            raise ValueError(
                f"Expected {RockboxDBFileType.INDEX.filename}, got {filename}"
            )

        index_file: "IndexFile" = cls()

        # Determine which TagFiles to load.
        if tag_files_to_load is None:
            # Load all known TagFile types if not specified.
            tag_files_to_load = [
                ft
                for ft in RockboxDBFileType
                if ft != RockboxDBFileType.INDEX and ft.tag_index is not None
            ]

        # Load the required TagFiles.
        for db_type in tag_files_to_load:
            tag_filepath: str = os.path.join(db_directory, db_type.filename)
            if not os.path.exists(tag_filepath):
                raise FileNotFoundError(
                    f"Tag file {db_type.filename} not found at {tag_filepath}"
                )

            try:
                tag_file: TagFile = TagFile.from_file(tag_filepath)
                index_file._loaded_tag_files[db_type.tag_index] = tag_file
            except Exception as e:
                raise RuntimeError(
                    f"Failed to load tag file {db_type.filename}: {e}"
                ) from e

        with open(filepath, "rb") as f:
            # Read master header fields.
            index_file.magic = read_uint32(f)
            index_file.datasize = read_uint32(f)
            index_file.entry_count = read_uint32(f)
            index_file.serial = read_uint32(f)
            index_file.commitid = read_uint32(f)
            index_file.dirty = read_uint32(f)

            if index_file.magic != RockboxDBFileType.INDEX.magic:
                raise ValueError(
                    f"Invalid magic number in {filepath}. Expected {hex(RockboxDBFileType.INDEX.magic)}, got {hex(index_file.magic)}"
                )

            # Read IndexFileEntry objects, linking them to loaded TagFiles.
            for _ in range(index_file.entry_count):
                entry: IndexFileEntry = IndexFileEntry.from_file(
                    f, loaded_tag_files=index_file._loaded_tag_files
                )
                index_file.entries.append(entry)

        return index_file

    def to_file(self, filepath: str):
        """
        Writes the IndexFile object to a specified file path.
        Recalculates datasize and entry_count based on current entries before writing.
        """
        self.entry_count = len(self.entries)

        # Calculate the total database size for the datasize field.
        # This includes the IndexFile's own header and entries, and all associated TagFiles' content.

        # Size of IndexFile's own header.
        calculated_total_db_size: int = 6 * 4

        # Total size of IndexFile's entries.
        calculated_total_db_size += sum(entry.size for entry in self.entries)

        # Add the content sizes of all associated TagFiles (excluding filename).
        for tag_file_obj in self._loaded_tag_files.values():
            if tag_file_obj.db_file_type == RockboxDBFileType.FILENAME:
                continue
            # Add TagFile's content size.
            calculated_total_db_size += tag_file_obj.datasize

        self.datasize = calculated_total_db_size

        with open(filepath, "wb") as f:
            # Write master header fields.
            write_uint32(f, self.magic)
            write_uint32(f, self.datasize)
            write_uint32(f, self.entry_count)
            write_uint32(f, self.serial)
            write_uint32(f, self.commitid)
            write_uint32(f, self.dirty)

            # Write each IndexFileEntry.
            for entry in self.entries:
                f.write(entry.to_bytes())

    def add_entry(self, entry: IndexFileEntry):
        """Adds an IndexFileEntry to this IndexFile."""
        self.entries.append(entry)
        # Ensure new entries also get the reference to loaded TagFile objects for tag resolution.
        entry._loaded_tag_files = self._loaded_tag_files
        return entry

    @property
    def loaded_tag_files(self) -> Dict[int, TagFile]:
        """Returns the dictionary of loaded TagFile objects."""
        return self._loaded_tag_files

    def __repr__(self) -> str:
        """Provides a developer-friendly string representation."""
        return (
            f"IndexFile(type='{self.db_file_type.filename}', magic={hex(self.magic)}, "
            f"datasize={self.datasize}, entry_count={self.entry_count}, serial={self.serial}, "
            f"commitid={self.commitid}, dirty={bool(self.dirty)}, "
            f"entries_len={len(self.entries)})"
        )

    def __len__(self) -> int:
        """Returns the number of IndexFileEntry objects managed by this IndexFile."""
        return len(self.entries)
