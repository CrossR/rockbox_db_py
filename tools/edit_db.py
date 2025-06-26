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

    genre_tag_index = TagTypeEnum.genre.value
    genre_file_type = RockboxDBFileType.GENRE

    genre_tag_file = main_index.loaded_tag_files.get(genre_file_type.tag_index)
    if not genre_tag_file:
        print(
            f"Error: Genre tag file ({genre_file_type.filename}) not loaded. Cannot modify genres."
        )
        return

    final_entries_list = []

    for original_entry_idx, original_entry in enumerate(main_index.entries):
        if original_entry.flag & FLAG_DELETED:
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
                g.strip() for g in original_genre_str.split("; ") if g.strip()
            ]

            if not individual_genres:
                print(
                    "  Warning: Split resulted in no individual genres. Skipping modification for this entry."
                )
                continue

            print(f"  Split into: {individual_genres}")

            # 1. Mark the original entry as DELETED
            original_entry.flag |= FLAG_DELETED
            original_entries_deleted_count += 1
            print(f"  Marked original entry (Index {original_entry_idx}) as DELETED.")

            # Update to set the deleted entries to have a CRC32 checksum
            for tag_idx in FILE_TAG_INDICES:
                original_tag_value_str = getattr(
                    original_entry, TagTypeEnum(tag_idx).name
                )

                if original_tag_value_str is not None:
                    crc_checksum = calculate_crc32(original_tag_value_str)
                    original_entry.tag_seek[tag_idx] = crc_checksum
                else:
                    original_entry.tag_seek[tag_idx] = 0xFFFFFFFF

            final_entries_list.append(original_entry)

            # 2. For each individual genre, create a new IndexFileEntry
            for individual_genre_name in individual_genres:
                # Get or create the TagFileEntry for this individual genre string
                # This ensures genre_tag_file contains all necessary unique genre strings.
                target_genre_tag_entry = genre_tag_file.add_entry(
                    TagFileEntry(tag_data=individual_genre_name, is_filename_db=False)
                )
                print(f"    Ensured TagFileEntry for '{individual_genre_name}' exists.")

                # Create a copy of the original IndexFileEntry for the new combination.
                # Using copy.deepcopy here is incredibly slow, so we manually create a new entry.
                new_entry = IndexFileEntry(
                    tag_seek=[0] * TAG_COUNT,
                    flag=original_entry.flag & ~FLAG_DELETED,
                )

                # Copy the tag_seek from the original entry
                for idx in range(TAG_COUNT):
                    if idx != genre_tag_index:
                        new_entry.tag_seek[idx] = original_entry.tag_seek[idx]

                # Set the genre tag_seek for the new entry to point to the TagFileEntry *object*.
                # This offset will be finalized to an integer value in finalize_index_for_write().
                new_entry.tag_seek[genre_tag_index] = target_genre_tag_entry

                # Assign the _loaded_tag_files reference to the new entry so its __getattr__ works.
                new_entry._loaded_tag_files = main_index.loaded_tag_files

                # Add the new entry to the main_index's list of entries
                main_index.add_entry(new_entry)
                new_entries_added_count += 1

                print(f"    Created new IndexFileEntry for: '{individual_genre_name}'.")
        else:
            # If the genre string is not multi-valued, just keep the original entry
            final_entries_list.append(original_entry)

    # After processing all entries, replace the main_index's entries with the final list
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

    # Get the genre tag index for efficiency
    genre_tag_index = TagTypeEnum.genre.value

    for index_entry in main_index.entries:
        # Check if the entry is deleted; no need to finalize its offsets if it won't be used
        if index_entry.flag & FLAG_DELETED:
            continue

        # Iterate through all file-based tags to update their offsets
        for tag_idx in FILE_TAG_INDICES:
            # Access the raw tag_seek value; it might be an integer or a TagFileEntry object
            raw_seek_value = index_entry.tag_seek[tag_idx]

            # If it's already an integer (e.g., loaded from disk), keep it unless it's the genre being modified
            if isinstance(raw_seek_value, int):
                # If it's the genre tag and we're in the modification context, it *should* be an object if modified
                # This branch means it's an unmodified genre, or other unmodified file-based tag.
                # Just ensure it's not the sentinel if its content is None.
                if (
                    raw_seek_value == 0xFFFFFFFF
                    and getattr(index_entry, TagTypeEnum(tag_idx).name) is not None
                ):
                    print(
                        f"  Warning: Tag {TagTypeEnum(tag_idx).name} has sentinel offset but data exists (Index {main_index.entries.index(index_entry)}). Setting to 0."
                    )
                    index_entry.tag_seek[tag_idx] = 0
                continue

            # If it's a TagFileEntry object, get its final offset
            elif isinstance(raw_seek_value, TagFileEntry):
                target_tag_entry = raw_seek_value  # Already the object

                if target_tag_entry.offset_in_file is not None:
                    index_entry.tag_seek[tag_idx] = target_tag_entry.offset_in_file
                else:
                    # This is a critical error: a TagFileEntry object was assigned,
                    # but after writing its TagFile, it still doesn't have an offset.
                    # This means it was never properly written or added to its TagFile.
                    print(
                        f"  CRITICAL ERROR: TagFileEntry '{target_tag_entry.tag_data}' (Tag {TagTypeEnum(tag_idx).name}) has no assigned offset_in_file AFTER TagFile write. Setting to sentinel."
                    )
                    index_entry.tag_seek[tag_idx] = 0xFFFFFFFF
            else:
                # This case should not happen if all tag_seek values are either int or TagFileEntry
                print(
                    f"  ERROR: Unexpected type for tag_seek[{tag_idx}] (Tag {TagTypeEnum(tag_idx).name}): {type(raw_seek_value)}. Setting to sentinel."
                )
                index_entry.tag_seek[tag_idx] = 0xFFFFFFFF

    print("IndexFileEntry tag_seek values finalized.")


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
