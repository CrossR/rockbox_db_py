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


def print_unique_genres(main_index: IndexFile):
    """
    Iterates through the loaded database and prints all unique genres.
    """
    print("\n--- Unique Genres ---")

    unique_genres = set()

    for i, index_entry in enumerate(main_index.entries):
        genre = index_entry.genre  # Access genre via __getattr__
        if genre is not None:
            unique_genres.add(genre)
        # Optional: Collect entries with no genre
        # else:
        #     unique_genres.add("(No Genre)")

    if not unique_genres:
        print("No genres found in the database.")
        return

    sorted_genres = sorted(list(unique_genres))

    for genre in sorted_genres:
        print(f"- {genre}")

    print("\n--- Unique genre listing complete ---")


def process_multi_genres(main_index: IndexFile, simulation_limit: int = 5):
    """
    Identifies tracks with multi-valued genre strings (e.g., "Rock; Pop").
    Simulates how these would be split and how new IndexFileEntries would be created.
    Does NOT modify the database.
    """
    print("\n--- Processing Multi-Valued Genres (Simulation Only) ---")

    multi_genre_entries_found = 0
    simulated_new_entries_count = 0

    genre_tag_index = TagTypeEnum.genre.value  # Numerical index for genre
    genre_file_type = RockboxDBFileType.GENRE  # Enum member for genre file
    genre_tag_file = main_index.loaded_tag_files.get(genre_file_type.tag_index)

    if not genre_tag_file:
        print(
            f"Error: Genre tag file ({genre_file_type.filename}) not loaded. Cannot process multi-genres."
        )
        return

    for i, original_entry in enumerate(main_index.entries):
        original_genre_str = original_entry.genre

        # Check if the genre string contains multiple values
        if original_genre_str and ";" in original_genre_str:
            multi_genre_entries_found += 1

            if (
                simulation_limit is not None
                and multi_genre_entries_found > simulation_limit
            ):
                print(
                    f"... Simulation limit ({simulation_limit}) reached. Stopping. ..."
                )
                break

            print(f"\nFound multi-genre entry (Index {i}):")
            print(f"  Original Genre: '{original_genre_str}'")
            print(
                f"  Track: '{original_entry.title}' (File: '{original_entry.filename}')"
            )

            # Split the genre string
            individual_genres = [
                g.strip() for g in original_genre_str.split(";") if g.strip()
            ]

            if not individual_genres:
                print("  Warning: Split resulted in no individual genres. Skipping.")
                continue

            print(f"  Split into: {individual_genres}")

            # Simulate creating new IndexFileEntries for each individual genre
            for j, individual_genre_name in enumerate(individual_genres):
                # Simulate finding or creating the TagFileEntry for this individual genre
                target_genre_tag_entry = genre_tag_file.get_entry_by_tag_data(
                    individual_genre_name
                )
                if not target_genre_tag_entry:
                    # In a real modification, you'd add this new entry to genre_tag_file
                    print(
                        f"    Simulating: Genre '{individual_genre_name}' is NEW. A TagFileEntry would be created."
                    )
                    # For simulation, create a dummy one with a placeholder offset
                    simulated_offset = 0xDEADBEEF + j  # Just for demonstration
                    target_genre_tag_entry = TagFileEntry(
                        tag_data=individual_genre_name,
                        idx_id=0,
                        is_filename_db=False,
                        offset_in_file=simulated_offset,
                    )
                else:
                    print(
                        f"    Simulating: Genre '{individual_genre_name}' EXISTS (offset: {hex(target_genre_tag_entry.offset_in_file)})."
                    )

                # Simulate creating a NEW IndexFileEntry for this combination
                # In a real scenario, you'd make a deep copy of original_entry and modify it.
                simulated_new_entry = (
                    original_entry.tag_seek.copy()
                )  # Copy raw tag_seek array
                simulated_new_entry[genre_tag_index] = (
                    target_genre_tag_entry.offset_in_file
                )  # Set new genre offset

                simulated_new_entries_count += 1
                print(
                    f"    Simulating: New IndexFileEntry for: '{individual_genre_name}' (points to offset {hex(target_genre_tag_entry.offset_in_file)})"
                )

    if multi_genre_entries_found == 0:
        print("No multi-valued genre entries found.")
    else:
        print(f"\n--- Multi-Genre Processing Simulation Complete ---")
        print(f"Total multi-genre entries found: {multi_genre_entries_found}")
        print(
            f"Total IndexFileEntries that would be created/modified: {simulated_new_entries_count}"
        )


def perform_multi_genre_modification(main_index: IndexFile):
    """
    Performs the actual modification of multi-valued genre strings.
    For each track with a multi-valued genre:
    1. Marks the original IndexFileEntry as DELETED.
    2. Creates new IndexFileEntry copies for each individual genre.
    3. Adds/ensures TagFileEntries exist for each individual genre.
    Modifies the main_index object in-place.
    """
    print("\n--- Performing Multi-Valued Genre Modification (Actual Changes) ---")

    modified_entries_count = 0
    new_entries_added_count = 0
    original_entries_deleted_count = 0

    genre_tag_index = TagTypeEnum.genre.value  # Numerical index for genre
    genre_file_type = RockboxDBFileType.GENRE  # Enum member for genre file

    genre_tag_file: TagFile = main_index.loaded_tag_files.get(genre_file_type.tag_index)
    if not genre_tag_file:
        print(
            f"Error: Genre tag file ({genre_file_type.filename}) not loaded. Cannot modify genres."
        )
        return

    final_entries_list = []  # We'll build the final list here.

    for original_entry_idx, original_entry in enumerate(main_index.entries):
        if original_entry.flag & FLAG_DELETED:
            final_entries_list.append(original_entry)
            continue

        original_genre_str = original_entry.genre

        if original_genre_str and ";" in original_genre_str:
            modified_entries_count += 1
            print(
                f"\nProcessing multi-genre entry (Original Index {original_entry_idx}):"
            )
            print(f"  Original Genre: '{original_genre_str}'")
            print(
                f"  Track: '{original_entry.title}' (File: '{original_entry.filename}')"
            )

            individual_genres = [
                g.strip() for g in original_genre_str.split(";") if g.strip()
            ]

            if not individual_genres:
                print(
                    "  Warning: Split resulted in no individual genres. Skipping modification for this entry."
                )
                final_entries_list.append(original_entry)
                continue

            print(f"  Split into: {individual_genres}")

            # Capture a pristine copy of original_entry.tag_seek BEFORE it's modified for CRC32s.
            # This copy holds the original integer offsets/values for all tags.
            original_tag_seek_values_for_new_entries = original_entry.tag_seek.copy()

            # 1b. Mark the original entry as DELETED (this mutates original_entry)
            original_entry.flag |= FLAG_DELETED
            original_entries_deleted_count += 1
            print(f"  Marked original entry (Index {original_entry_idx}) as DELETED.")

            # This loop now modifies original_entry.tag_seek in place with CRC32s.
            for tag_idx in FILE_TAG_INDICES:
                original_tag_value_str = getattr(
                    original_entry, TagTypeEnum(tag_idx).name
                )
                if original_tag_value_str is not None:
                    crc_checksum = calculate_crc32(original_tag_value_str)
                    original_entry.tag_seek[tag_idx] = crc_checksum
                    print(
                        f"    Set '{TagTypeEnum(tag_idx).name}' tag_seek to CRC32: {hex(crc_checksum)}"
                    )
                else:
                    original_entry.tag_seek[tag_idx] = 0xFFFFFFFF
                    print(
                        f"    Set '{TagTypeEnum(tag_idx).name}' tag_seek to sentinel (no original value)."
                    )

            final_entries_list.append(
                original_entry
            )  # Keep the now-deleted-and-CRC'd entry in the list

            # 2. For each individual genre, create a new IndexFileEntry
            for individual_genre_name in individual_genres:
                target_genre_tag_entry = genre_tag_file.add_entry(
                    TagFileEntry(tag_data=individual_genre_name, is_filename_db=False)
                )
                print(f"    Ensured TagFileEntry for '{individual_genre_name}' exists.")

                # Initialize new_entry's tag_seek from the pristine copy (original_tag_seek_values_for_new_entries).
                # This ensures the new entry gets the original offsets for non-genre tags.
                new_tag_seek = original_tag_seek_values_for_new_entries.copy()

                # Now, set the genre tag_seek for the new entry to point to the TagFileEntry *object*.
                new_tag_seek[genre_tag_index] = target_genre_tag_entry

                new_entry = IndexFileEntry(
                    tag_seek=new_tag_seek,  # Pass the correctly constructed list
                    flag=original_entry.flag
                    & ~FLAG_DELETED,  # Copy original flag, clear DELETED
                )

                new_entry._loaded_tag_files = main_index.loaded_tag_files

                final_entries_list.append(new_entry)
                new_entries_added_count += 1

                print(f"    Created new IndexFileEntry for: '{individual_genre_name}'.")

        else:
            final_entries_list.append(original_entry)

    main_index.entries = final_entries_list

    if modified_entries_count == 0:
        print("No multi-valued genre entries found to modify.")
    else:
        print(f"\n--- Multi-Genre Modification Complete ---")
        print(f"Total original multi-genre entries processed: {modified_entries_count}")
        print(
            f"Total original IndexFileEntries marked as DELETED: {original_entries_deleted_count}"
        )
        print(f"Total new IndexFileEntries added: {new_entries_added_count}")
        print(
            f"Database now has {len(main_index.entries)} entries (including deleted ones)."
        )


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
        "--genres",
        action="store_true",
        help="Print all unique genres (default action).",
    )
    parser.add_argument(
        "--process-multi-genres-simulate",
        action="store_true",
        help="Simulate processing multi-valued genre strings into individual entries (no actual change).",
    )
    parser.add_argument(
        "--process-multi-genres-actual",
        action="store_true",
        help="PERFORM actual modification of multi-valued genre strings into individual entries.",
    )
    parser.add_argument(
        "--limit-simulation",
        type=int,
        default=5,
        help="Limit the number of multi-genre entries processed during simulation.",
    )
    parser.add_argument(
        "--output-db-path",
        type=str,
        help="Path to save the modified database. Required with --process-multi-genres-actual.",
    )

    args = parser.parse_args()

    # Default action if no specific action is requested
    if not any(
        [
            args.genres,
            args.process_multi_genres_simulate,
            args.process_multi_genres_actual,
        ]
    ):
        args.genres = True

    if args.process_multi_genres_actual and not args.output_db_path:
        parser.error(
            "--output-db-path is required when performing actual modifications."
        )

    return args


def main():

    args = parser_args()
    main_index = load_rockbox_database(args.db_path)

    if main_index is None:
        print("Failed to load the Rockbox database.")
        return

    if args.genres:
        print_unique_genres(main_index)

    if args.process_multi_genres_simulate:
        process_multi_genres(main_index, simulation_limit=args.limit_simulation)

    if args.process_multi_genres_actual:
        perform_multi_genre_modification(main_index)

        try:
            save_modified_database(main_index, args.output_db_path)
        except Exception as e:
            print(f"Failed to save modified database: {e}")
            return


if __name__ == "__main__":
    main()
