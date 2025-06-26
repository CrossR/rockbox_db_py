# tools/db_loader.py
import os
import sys

from rockbox_db_py.classes.db_file_type import RockboxDBFileType
from rockbox_db_py.classes.tag_file import TagFile
from rockbox_db_py.classes.index_file import IndexFile
from rockbox_db_py.utils.defs import TagTypeEnum


def load_and_print_rockbox_database(db_directory: str):
    """Loads all Rockbox database files from the specified directory and prints their contents."""

    print(f"--- Loading Rockbox database from: {db_directory} ---")

    # 1. Load all tag data files first
    loaded_tag_files = {}
    print("\n--- Loading Tag Data Files ---")
    for db_type in RockboxDBFileType:
        if db_type == RockboxDBFileType.INDEX:
            continue

        filepath = os.path.join(db_directory, db_type.filename)
        if os.path.exists(filepath):
            try:
                tag_file = TagFile.from_file(filepath)
                print(f"Successfully loaded {db_type.filename}: {tag_file}")
                loaded_tag_files[db_type.tag_index] = tag_file
            except Exception as e:
                print(f"Error loading {db_type.filename}: {e}")
        else:
            print(f"Warning: {db_type.filename} not found in {db_directory}")

    # 2. Load the main index file, passing the loaded tag files
    index_filepath = os.path.join(db_directory, RockboxDBFileType.INDEX.filename)
    try:
        main_index = IndexFile.from_file(
            index_filepath, loaded_tag_files=loaded_tag_files
        )
        print(f"\nSuccessfully loaded {RockboxDBFileType.INDEX.filename}:")
        print(main_index)
    except Exception as e:
        print(f"\nError loading {RockboxDBFileType.INDEX.filename}: {e}")
        return

    # 3. Collect and Print Unique Album Artist and Album Data
    print("\n--- Unique Artist & Album Combinations ---")  # Changed title

    unique_combinations = set()  # Use a set to store unique (artist, album) tuples

    for i, index_entry in enumerate(main_index.entries):
        artist = index_entry.albumartist
        year = index_entry.year
        album = index_entry.album

        # Handle cases where the tag might not exist
        artist_display = artist if artist is not None else "(N/A)"
        album_display = album if album is not None else "(N/A)"
        year_display = year if year is not None else ""

        # Add the unique combination to the set
        unique_combinations.add((artist_display, album_display, year_display))

    if not unique_combinations:
        print("No artist and album combinations found.")
        return

    # Sort the unique combinations for consistent output
    sorted_unique_combinations = sorted(list(unique_combinations))

    print(f"{'Artist':<30} | {'Album':<50}")
    print("-" * 85)

    for a, al, y in sorted_unique_combinations:
        print(f"{a:<30} | {y} - {al:<50}")

    print("\n--- Database loading and unique artist/album output complete ---")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/print_db.py <path_to_rockbox_db_directory>")
        print("\nExample: python tools/print_db.py /mnt/ipod/.rockbox/database")
        sys.argv.append(
            "D:\\User Files\\Downloads\\rockbox\\files\\"
        )  # For testing without command line arg
        # sys.exit(1) # Uncomment this line if you remove the test arg

    db_path_arg = sys.argv[1]
    if not os.path.isdir(db_path_arg):
        print(f"Error: Database directory '{db_path_arg}' does not exist.")
        sys.exit(1)

    load_and_print_rockbox_database(db_path_arg)
