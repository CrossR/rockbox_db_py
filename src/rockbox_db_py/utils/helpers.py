# src/rockbox_db_py/utils/helpers.py

import os
import shutil
from typing import Optional, List, Dict  # Used for type hinting

# Imports for Rockbox DB classes
from rockbox_db_py.classes.db_file_type import RockboxDBFileType
from rockbox_db_py.classes.index_file import IndexFile
from rockbox_db_py.classes.index_file_entry import IndexFileEntry
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

            # Get the current string value of the tag from the IndexFileEntry.
            current_tag_value_str: Optional[str] = getattr(index_entry, tag_name_str)

            # Get the corresponding TagFile object.
            # Its entries and offsets are correctly established from its recent write to disk.
            target_tag_file_obj: Optional[TagFile] = main_index.loaded_tag_files.get(
                tag_idx
            )

            if target_tag_file_obj is None:
                print(
                    f"  Warning: TagFile for index {tag_idx} ({tag_name_str}) not loaded. Setting tag_seek to sentinel for related entries."
                )
                index_entry.tag_seek[tag_idx] = 0xFFFFFFFF
                continue

            target_tag_entry_in_file: Optional[TagFileEntry] = None
            if current_tag_value_str is not None:
                # Find the TagFileEntry by its string data from the now-written TagFile.
                target_tag_entry_in_file = target_tag_file_obj.get_entry_by_tag_data(
                    current_tag_value_str
                )

            if (
                target_tag_entry_in_file
                and target_tag_entry_in_file.offset_in_file is not None
            ):
                # Set the tag_seek to the actual numerical offset from the *newly written* TagFile.
                index_entry.tag_seek[tag_idx] = target_tag_entry_in_file.offset_in_file
            else:
                # If tag data is None, or entry not found in TagFile (e.g., if string didn't exist),
                # set the tag_seek to the sentinel value (0xFFFFFFFF).
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
