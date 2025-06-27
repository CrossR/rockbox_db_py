# tools/modify_db.py
#
# This tool loads a Rockbox database and provides functionality to inspect and
# later modify its contents.
#
# To start, it loads the database and prints all unique genres found.

import argparse
import copy
import os
import shutil
import sys


# Add the 'src' directory to the Python path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
)

from rockbox_db_py.classes.db_file_type import RockboxDBFileType
from rockbox_db_py.classes.index_file import IndexFile
from rockbox_db_py.classes.index_file_entry import IndexFileEntry
from rockbox_db_py.utils.struct_helpers import calculate_crc32
from rockbox_db_py.utils.defs import (
    TagTypeEnum,
    FLAG_DELETED,
    FILE_TAG_INDICES,
    TAG_COUNT,
)
from rockbox_db_py.classes.tag_file import TagFileEntry


def load_rockbox_database(db_directory: str) -> IndexFile | None:
    """
    Loads all Rockbox database files from the specified directory.
    Returns the loaded IndexFile object or None if loading fails.
    """
    print(f"--- Loading Rockbox database from: {db_directory} ---")

    index_filepath = os.path.join(db_directory, RockboxDBFileType.INDEX.filename)
    main_index: IndexFile = None
    try:
        main_index = IndexFile.from_file(index_filepath)
        print(f"Successfully loaded {main_index.db_file_type.filename}: {main_index}")
    except FileNotFoundError as e:
        print(f"Error: Input database file not found: {e}")
        return None
    except Exception as e:
        print(f"Error loading database: {e}")
        return None

    return main_index


def perform_single_genre_canonicalization(main_index: IndexFile):
    """
    Identifies tracks with multi-valued genre strings (e.g., "Rock; Pop").
    Modifies them to have only the first genre from the split string.
    Modifies the original IndexFileEntry in-place.
    """
    print("\n--- Performing Single Genre Canonicalization (Actual Changes) ---")

    modified_entries_count = 0

    genre_tag_index = TagTypeEnum.genre.value  # Numerical index for genre
    genre_file_type = RockboxDBFileType.GENRE  # Enum member for genre file

    genre_tag_file: TagFile = main_index.loaded_tag_files.get(genre_tag_index)
    if not genre_tag_file:
        print(
            f"Error: Genre tag file ({genre_file_type.filename}) not loaded. Cannot modify genres."
        )
        return

    # Iterate over the entries directly for in-place modification
    for i, entry_to_modify in enumerate(main_index.entries):
        original_genre_str = entry_to_modify.genre

        # Check if the genre string contains multiple values
        if original_genre_str and ";" in original_genre_str:
            modified_entries_count += 1
            print(f"\nProcessing multi-genre entry (Index {i}):")
            print(f"  Original Genre: '{original_genre_str}'")
            print(
                f"  Track: '{entry_to_modify.title}' (File: '{entry_to_modify.filename}')"
            )

            individual_genres = [
                g.strip() for g in original_genre_str.split(";") if g.strip()
            ]

            if not individual_genres:
                print(
                    "  Warning: Split resulted in no individual genres. Skipping modification for this entry."
                )
                continue

            new_single_genre_name = individual_genres[0]
            print(f"  Canonicalizing to single genre: '{new_single_genre_name}'")

            target_genre_tag_entry = genre_tag_file.add_entry(
                TagFileEntry(tag_data=new_single_genre_name, is_filename_db=False)
            )
            print(f"  Ensured TagFileEntry for '{new_single_genre_name}' exists.")

            # Update the genre tag_seek for the entry to point to the TagFileEntry *object*.
            entry_to_modify.tag_seek[genre_tag_index] = target_genre_tag_entry
        else:
            # No modification needed, just print the existing genre
            print(f"\nProcessing single-genre entry (Index {i}):")
            # You might want to print the existing genre here for full clarity
            # print(f"  Existing Genre: '{original_genre_str}'")


    # --- CRITICAL FIX START: Cleanse genre_tag_file.entries of multi-value strings ---
    initial_genre_entries_count = len(genre_tag_file.entries)

    cleaned_genre_entries = []
    removed_genre_strings_count = 0
    for genre_entry in genre_tag_file.entries:
        if ';' in genre_entry.tag_data:
            removed_genre_strings_count += 1
            # print(f"  DEBUG: Removing multi-value genre string from genre_tag_file: '{genre_entry.tag_data}'") # Optional debug
        else:
            cleaned_genre_entries.append(genre_entry)

    genre_tag_file.entries = cleaned_genre_entries

    # Clear and rebuild entries_by_tag_data to reflect the cleaned list
    # This is critical because TagFile.to_file relies on entries_by_tag_data being consistent.
    genre_tag_file.entries_by_tag_data = {} # Clear the dict
    for entry in genre_tag_file.entries: # Rebuild from the cleaned list
        genre_tag_file.entries_by_tag_data[entry.tag_data.casefold()] = entry

    print(f"\n--- Genre TagFile Cleanup ---")
    print(f"  Original genre_tag_file entries count: {initial_genre_entries_count}")
    print(f"  Multi-value genre strings removed from genre_tag_file: {removed_genre_strings_count}")
    print(f"  Final genre_tag_file entries count: {len(genre_tag_file.entries)}")
    # --- CRITICAL FIX END ---


    if modified_entries_count == 0:
        print("No multi-valued genre entries found to modify.")
    else:
        print(f"\n--- Single Genre Canonicalization Complete ---")
        print(f"Total entries modified: {modified_entries_count}")
        print(f"Database now has {len(main_index.entries)} entries (count unchanged).")



def finalize_index_for_write(main_index: IndexFile):
    """
    Ensures all tag_seek values in IndexFileEntries point to valid numerical offsets.
    This should be called AFTER all TagFiles have been written (and thus have
    their TagFileEntry.offset_in_file properties updated).
    """
    print("\nFinalizing IndexFileEntry tag_seek values for writing...")

    # We iterate through all entries, deleted or not, because their offsets need to be valid
    # if they are written to the database.

    for index_entry in main_index.entries:
        # We process this entry for finalization regardless of DELETED flag,
        # as it will be written to the database.

        # Iterate through ALL file-based tags to update their offsets
        for tag_idx in FILE_TAG_INDICES:
            tag_name_str = TagTypeEnum(tag_idx).name  # Get the string name of the tag

            # Get the current string value of the tag from the IndexFileEntry
            current_tag_value_str = getattr(index_entry, tag_name_str)

            target_tag_file_obj: TagFile = main_index.loaded_tag_files.get(tag_idx)

            if target_tag_file_obj is None:
                # This could happen if the TagFile was not loaded (e.g., if tag_files_to_load was specified
                # and didn't include this tag file, or if the file was missing on disk).
                print(
                    f"  Warning: TagFile for index {tag_idx} ({tag_name_str}) not loaded. Setting tag_seek to sentinel for related entries."
                )
                index_entry.tag_seek[tag_idx] = 0xFFFFFFFF
                continue

            target_tag_entry_in_file = None
            if current_tag_value_str is not None:
                # Find the TagFileEntry by its string data from the now-written TagFile
                target_tag_entry_in_file = target_tag_file_obj.get_entry_by_tag_data(
                    current_tag_value_str
                )

            if (
                target_tag_entry_in_file
                and target_tag_entry_in_file.offset_in_file is not None
            ):
                # Set the tag_seek to the actual numerical offset from the *newly written* TagFile
                index_entry.tag_seek[tag_idx] = target_tag_entry_in_file.offset_in_file
            else:
                # If tag data is None, or entry not found in file (shouldn't happen if data exists), set sentinel
                # print(f"  Warning: Tag '{tag_name_str}' value '{current_tag_value_str}' could not be found in TagFile '{target_tag_file_obj.db_file_type.filename}' to get offset. Setting to sentinel.")
                index_entry.tag_seek[tag_idx] = 0xFFFFFFFF

    print(
        f"IndexFileEntry tag_seek values finalized. Active entries processed: {len(main_index.entries)}"
    )


def save_modified_database(main_index: IndexFile, output_db_dir: str):
    print(f"\n--- Saving modified database to: {output_db_dir} ---")

    # Ensure the output directory exists
    if not os.path.exists(output_db_dir):
        try:
            os.makedirs(output_db_dir)
            print(f"Created output directory: {output_db_dir}")
        except OSError as e:
            print(f"Error creating output directory: {e}")
            raise

    # If the output directory already exists, clear it
    elif os.path.exists(output_db_dir) and os.listdir(output_db_dir):
        print(f"Output directory {output_db_dir} already exists. Clearing it...")
        try:
            shutil.rmtree(output_db_dir)
            os.makedirs(output_db_dir)
            print(f"Cleared and recreated output directory: {output_db_dir}")
        except OSError as e:
            print(f"Error clearing output directory: {e}")
            raise

    try:
        # 1. Write all associated tag files FIRST.
        loaded_tag_files = main_index.loaded_tag_files
        for tag_index, tag_file_obj in loaded_tag_files.items():
            if not tag_file_obj:
                continue
            db_file_type = RockboxDBFileType.from_tag_index(tag_index)
            output_tag_filepath = os.path.join(output_db_dir, db_file_type.filename)
            tag_file_obj.to_file(
                output_tag_filepath
            )  # This updates entry.offset_in_file for all entries
            print(f"Successfully wrote {db_file_type.filename} (and updated offsets)")

        # 2. After TagFiles are written and their offsets are updated,
        finalize_index_for_write(main_index)  # Call the finalization step here!

        # 3. Write the main index file
        output_index_filepath = os.path.join(
            output_db_dir, RockboxDBFileType.INDEX.filename
        )
        main_index.to_file(output_index_filepath)
        print(f"Successfully wrote {RockboxDBFileType.INDEX.filename}")

        print("\nModified database saved successfully.")

    except Exception as e:
        print(f"Error saving modified database: {e}")
        raise  # Re-raise the exception to indicate failure


def parser_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load and inspect/modify a Rockbox database."
    )
    parser.add_argument(
        "db_path",
        type=str,
        help="Path to the directory containing Rockbox database files.",
    )
    parser.add_argument(
        "output_db_path",
        type=str,
        help="Path to save the modified database"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Simulate processing, but do not modify the database.",
    )

    return parser.parse_args()


def main():

    args = parser_args()
    main_index = load_rockbox_database(args.db_path)

    if main_index is None:
        print("Failed to load the Rockbox database.")
        return

    perform_single_genre_canonicalization(main_index)

    if args.dry_run:
        print("\n--- Dry run complete. No changes made to the database. ---")
        return

    try:
        save_modified_database(main_index, args.output_db_path)
    except Exception as e:
        print(f"Failed to save modified database: {e}")
        return


if __name__ == "__main__":
    main()
