# tools/db_loader.py
import os
import sys

from rockbox_db_py.classes.db_file_type import RockboxDBFileType
from rockbox_db_py.classes.tag_file import TagFile
from rockbox_db_py.classes.index_file import IndexFile
from rockbox_db_py.utils.defs import (
    TAG_TYPES,
    FILE_TAG_INDICES,
)


def load_and_print_rockbox_database(db_directory: str):
    """Loads all Rockbox database files from the specified directory and prints their contents."""

    print(f"--- Loading Rockbox database from: {db_directory} ---")

    # 1. Load the main index file
    index_filepath = os.path.join(db_directory, RockboxDBFileType.INDEX.filename)
    try:
        main_index = IndexFile.from_file(index_filepath)
        print(f"\nSuccessfully loaded {RockboxDBFileType.INDEX.filename}:")
        print(main_index)
    except Exception as e:
        print(f"\nError loading {RockboxDBFileType.INDEX.filename}: {e}")
        return

    # 2. Load all tag data files
    loaded_tag_files = {}
    print("\n--- Loading Tag Data Files ---")
    for db_type in RockboxDBFileType:
        if db_type == RockboxDBFileType.INDEX:
            continue

        # Get the filename and check if it exists
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

        # 3. New: Collect and Print Unique Album Artist and Album Data
    print("\n--- Unique Album Artist & Album Combinations ---")

    album_artist_tag_idx = RockboxDBFileType.ALBUMARTIST.tag_index
    album_tag_idx = RockboxDBFileType.ALBUM.tag_index

    unique_albums = set()  # Use a set to store unique (album_artist, album) tuples

    for i, index_entry in enumerate(main_index.entries):
        album_artist = "(N/A)"
        album = "(N/A)"

        # Retrieve Album Artist
        if album_artist_tag_idx in loaded_tag_files:
            album_artist_offset = index_entry.get_tag_value(album_artist_tag_idx)
            album_artist_entry = loaded_tag_files[
                album_artist_tag_idx
            ].get_entry_by_offset(album_artist_offset)
            if album_artist_entry:
                album_artist = album_artist_entry.tag_data

        # Retrieve Album
        if album_tag_idx in loaded_tag_files:
            album_offset = index_entry.get_tag_value(album_tag_idx)
            album_entry = loaded_tag_files[album_tag_idx].get_entry_by_offset(
                album_offset
            )
            if album_entry:
                album = album_entry.tag_data

        # Add the unique combination to the set
        unique_albums.add((album_artist, album))

    if not unique_albums:
        print("No album artist and album combinations found.")
        return

    # Sort the unique combinations for consistent output
    sorted_unique_albums = sorted(list(unique_albums))

    print(f"{'Album Artist':<30} | {'Album':<50}")
    print("-" * 85)

    for aa, a in sorted_unique_albums:
        print(f"{aa:<30} | {a:<50}")

    print("\n--- Database loading and unique album/artist output complete ---")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/db_loader.py <path_to_rockbox_db_directory>")
        print("\nExample: python tools/db_loader.py /mnt/ipod/.rockbox/database")
        sys.exit(1)

    db_path_arg = sys.argv[1]
    if not os.path.isdir(db_path_arg):
        print(f"Error: Database directory '{db_path_arg}' does not exist.")
        sys.exit(1)

    load_and_print_rockbox_database(db_path_arg)
