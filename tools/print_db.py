# Debugging and verification script for Rockbox database files.
#
# This script is useful for verifying that the code can correctly read and process
# a set of Rockbox database files.
import argparse
from collections import defaultdict

from rockbox_db_py.classes.music_file import MusicFile
from rockbox_db_py.classes.db_file_type import RockboxDBFileType
from rockbox_db_py.classes.tag_file import TagFile
from rockbox_db_py.classes.index_file import IndexFile
from rockbox_db_py.utils.defs import TagTypeEnum, FLAG_DELETED, FILE_TAG_INDICES
from rockbox_db_py.utils.helpers import load_rockbox_database


def valid_entry(entry, prop) -> bool:
    """Check if the entry is valid (not deleted and has the specified property)."""
    return not (entry.flag & FLAG_DELETED) and getattr(entry, prop) is not None


def print_album_artist_album_data(main_index: IndexFile):
    print("\n--- Unique Artist & Album Combinations ---")

    unique_combinations = set()

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


def get_db_stats(main_index: IndexFile):
    """Prints statistics about the Rockbox database."""
    print("\n--- Database Statistics ---")
    print(f"Total Entries: {main_index.entry_count}")
    print(f"Database Serial: {main_index.serial}")
    print(f"Commit ID: {main_index.commitid}")
    print(f"Dirty Flag: {main_index.dirty}")

    # Count all the tags
    tag_set_list = defaultdict(list)
    tags = main_index._loaded_tag_files.values()

    for entry in main_index.entries:
        tag_set = {}
        for tag_type in TagTypeEnum:
            result = getattr(entry, tag_type.name)
            tag_set_list[tag_type].append(result)

    print("\n--- Tag Counts ---")
    for tag_type, result in tag_set_list.items():
        print(f"{tag_type.name}: {len(set(result))} unique values")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print Rockbox database contents.")
    parser.add_argument(
        "db_path",
        type=str,
        help="Path to the directory containing Rockbox database files.",
    )

    # Options for additional functionality
    parser.add_argument(
        "--stats", action="store_true", help="Print statistics about the database."
    )
    parser.add_argument(
        "--albums",
        action="store_true",
        help="Print unique artist and album combinations.",
    )
    parser.add_argument("--artists", action="store_true", help="Print unique artists.")
    parser.add_argument("--tracks", action="store_true", help="Print unique tracks.")
    parser.add_argument("--genres", action="store_true", help="Print unique genres.")

    args = parser.parse_args()

    # If nothing is specified, default to printing albums
    if not any([args.stats, args.artists, args.tracks, args.genres]):
        args.albums = True

    return args


def main():

    args = parse_args()
    main_index = load_rockbox_database(args.db_path)

    if main_index is None:
        print("Failed to load the Rockbox database.")
        return

    print(f"Loaded Rockbox database from: {args.db_path}")
    print(f"Database Serial: {main_index.serial}")
    print(f"Commit ID: {main_index.commitid}")
    print(f"Dirty Flag: {main_index.dirty}")
    print(f"Total Entries: {main_index.entry_count}")

    if args.albums:
        print_album_artist_album_data(main_index)

    if args.artists:
        print("\n--- Unique Artists ---")
        unique_artists = set()
        for entry in main_index.entries:
            if valid_entry(entry, "artist"):
                unique_artists.add(entry.artist)
        for artist in sorted(unique_artists):
            print(artist)

    if args.tracks:
        print("\n--- Unique Tracks ---")
        unique_tracks = set()
        for entry in main_index.entries:
            if valid_entry(entry, "title"):
                unique_tracks.add(entry.title)
        for track in sorted(unique_tracks):
            print(track)

    if args.genres:
        print("\n--- Unique Genres ---")
        unique_genres = set()
        genre_count = {}
        for entry in main_index.entries:
            if not valid_entry(entry, "genre"):
                continue
            unique_genres.add(entry.genre)
            genre_count[entry.genre] = genre_count.get(entry.genre, 0) + 1

        for genre in sorted(unique_genres):
            print(f"{genre} ({genre_count.get(genre, 0)})")

    if args.stats:
        get_db_stats(main_index)


if __name__ == "__main__":
    main()
