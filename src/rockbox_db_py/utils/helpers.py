# src/rockbox_db_py/utils/helpers.py

import os
import shutil
from typing import Optional, List, Dict

# Imports for Rockbox DB classes
from rockbox_db_py.classes.db_file_type import RockboxDBFileType
from rockbox_db_py.classes.index_file import IndexFile
from rockbox_db_py.classes.music_file import MusicFile, SUPPORTED_MUSIC_EXTENSIONS
from rockbox_db_py.classes.tag_file import TagFile
from rockbox_db_py.classes.tag_file_entry import TagFileEntry
from rockbox_db_py.utils.defs import TagTypeEnum, FILE_TAG_INDICES


def load_rockbox_database(db_directory: str) -> Optional[IndexFile]:
    """
    Loads the Rockbox database from the specified directory.
    This includes the main index file and all associated tag data files.

    Args:
        db_directory: Path to the directory containing Rockbox database files.

    Returns:
        The loaded IndexFile object, or None if loading fails.
    """
    index_filepath: str = os.path.join(db_directory, RockboxDBFileType.INDEX.filename)
    try:
        # IndexFile.from_file handles loading all associated TagFiles internally.
        main_index: IndexFile = IndexFile.from_file(index_filepath)
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Index file not found in directory '{db_directory}': {e}"
        ) from e
    except Exception as e:
        raise RuntimeError(
            f"Failed to load IndexFile from '{index_filepath}': {e}"
        ) from e

    return main_index


def finalize_index_for_write(main_index: IndexFile):
    """
    Ensures all file-based tag_seek values in IndexFileEntries point to valid
    numerical offsets (from the newly written TagFiles) before writing the IndexFile.

    Args:
        main_index: The IndexFile object ready for finalization.
    """

    # Iterate through all entries in the database.
    # Their tag_seek values for file-based tags are currently either original offsets
    # or TagFileEntry objects (for modified genres).
    for index_entry in main_index.entries:
        # Process this entry regardless of DELETED flag, as it will be written.

        # Iterate through ALL file-based tags to update their offsets.
        for tag_idx in FILE_TAG_INDICES:
            tag_name_str: str = TagTypeEnum(tag_idx).name

            current_tag_seek_value: Union[int, TagFileEntry] = index_entry.tag_seek[
                tag_idx
            ]

            # Case 1: The tag_seek is currently a TagFileEntry object (this tag was modified)
            # Case 2: The tag_seek is already an integer offset (e.g., loaded from file, or not modified)
            # Case 3: The tag_seek is None or an unexpected type (set to sentinel value)
            if isinstance(current_tag_seek_value, TagFileEntry):
                target_tag_entry_in_file: TagFileEntry = current_tag_seek_value

                # Ensure the TagFileEntry has a valid offset_in_file.
                # If it was modified, it should have been written to a file.
                # If it has no offset, we set it to 0xFFFFFFFF as a sentinel
                if target_tag_entry_in_file.offset_in_file is not None:
                    index_entry.tag_seek[tag_idx] = (
                        target_tag_entry_in_file.offset_in_file
                    )
                else:
                    index_entry.tag_seek[tag_idx] = 0xFFFFFFFF
            elif isinstance(current_tag_seek_value, int):
                # Check for '0' offset, which can be ambiguous but often means 'no data' for strings.
                if current_tag_seek_value == 0:
                    index_entry.tag_seek[tag_idx] = 0xFFFFFFFF
            else:
                index_entry.tag_seek[tag_idx] = 0xFFFFFFFF


def write_rockbox_database(
    main_index: IndexFile, output_db_dir: str, auto_finalize: bool = True
) -> bool:
    """
    Saves the modified Rockbox database (IndexFile and its associated TagFiles)
    to the specified output directory.

    Args:
        main_index: The modified IndexFile object ready for saving.
        output_db_dir: The directory where the database files will be written.
        auto_finalize: If True, automatically calls finalize_index_for_write
                       before writing the IndexFile.
    """

    # Ensure output directory exists and is ready for writing.
    if not os.path.exists(output_db_dir):
        try:
            os.makedirs(output_db_dir)
        except OSError as e:
            raise
    elif os.path.exists(output_db_dir) and os.listdir(output_db_dir):
        try:
            shutil.rmtree(output_db_dir)
            os.makedirs(output_db_dir)
        except OSError as e:
            raise

    try:
        # Write all associated tag files FIRST.
        # This is critical as it assigns correct `offset_in_file` values
        # to the TagFileEntry objects, including any newly added ones.
        loaded_tag_files: Dict[int, TagFile] = main_index.loaded_tag_files
        for tag_index, tag_file_obj in loaded_tag_files.items():
            if not tag_file_obj:
                continue
            db_file_type: RockboxDBFileType = RockboxDBFileType.from_tag_index(
                tag_index
            )
            output_tag_filepath: str = os.path.join(
                output_db_dir, db_file_type.filename
            )

            # This updates entry.offset_in_file for all entries
            tag_file_obj.to_file(output_tag_filepath)

        # After TagFiles are written and their offsets are updated,
        # finalize IndexFile entries to point to the *new* numerical offsets.
        if auto_finalize:
            finalize_index_for_write(main_index)

        # Write the main index file.
        output_index_filepath: str = os.path.join(
            output_db_dir, RockboxDBFileType.INDEX.filename
        )
        main_index.to_file(output_index_filepath)

        return True
    except Exception as e:
        print(f"Error saving modified database: {e}")
        raise


def scan_music_directory(directory_path: str) -> List[MusicFile]:
    """
    Recursively scans a directory for music files and returns a list of MusicFile objects.

    Args:
        directory_path: The root directory to scan.

    Returns:
        A list of MusicFile objects found and successfully parsed.
    """
    music_files: List[MusicFile] = []
    processed_count: int = 0
    skipped_count: int = 0

    for root, _, files in os.walk(directory_path):
        for file in files:
            file_path: str = os.path.join(root, file)

            extension = os.path.splitext(file_path)[1].lower()
            if extension not in SUPPORTED_MUSIC_EXTENSIONS:
                continue

            music_file: Optional[MusicFile] = MusicFile.from_filepath(file_path)

            if music_file:
                music_files.append(music_file)
                processed_count += 1
            else:
                skipped_count += 1

    if skipped_count > 0:
        print(
            f"Skipped {skipped_count} files that could not be parsed as MusicFile objects."
        )

    return music_files
