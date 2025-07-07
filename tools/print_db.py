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


def print_first_n_entries(main_index: IndexFile, n: int = 10):
    """Print the first n entries in the Rockbox database."""
    print(f"\n--- First {n} Entries ---")
    for i, entry in enumerate(main_index.entries[:n]):
        if valid_entry(entry, "title"):
            print(f"{i + 1:>3}: {entry.title} by {entry.artist} ({entry.album})")
            print(f"    Tags:")
            for tag_type in TagTypeEnum:
                tag_value = getattr(entry, tag_type.name)
                if tag_value is not None:
                    print(f"      {tag_type.name}: {tag_value}")
        else:
            print(f"{i + 1:>3}: [Invalid Entry]")

    if len(main_index.entries) > n:
        print(f"... and {len(main_index.entries) - n} more entries.")


def print_album_artist_album_data(main_index: IndexFile):

    albums = defaultdict(list)

    for _, index_entry in enumerate(main_index.entries):

        artist = index_entry.albumartist
        year = index_entry.year
        album = index_entry.album

        if not album or not artist:
            continue

        # Add the unique combination to the set
        if f"{year} - {album}" not in albums[artist]:
            albums[artist].append(f"{year} - {album}")

    if len(albums) == 0:
        print("No artist and album combinations found.")
        return

    # Sort the unique combinations for consistent output
    sorted_artists = sorted(albums.keys())
    sorted_albums = {a: sorted(albums[a]) for a in sorted_artists}

    print(f"{'Artist':<30} | {'Album':<50}")
    print("-" * 85)

    for artist, albums in sorted_albums.items():
        print(f"{artist:<30} | {' ' * 50}")
        for album in albums:
            print(f"{' ' * 30} | {album:<50}")


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
        "--first-n",
        type=int,
        default=10,
        help="Print the first N entries in the database (default: 10).",
    )
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
    parser.add_argument(
        "--composer", action="store_true", help="Print unique composers."
    )

    args = parser.parse_args()

    # If nothing is specified, default to printing first 10 entries
    if not any(
        [
            args.first_n,
            args.stats,
            args.albums,
            args.artists,
            args.tracks,
            args.genres,
            args.composer,
        ]
    ):
        args.first_n = 10

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


    if args.first_n:
        print_first_n_entries(main_index, args.first_n)

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

    if args.composer:
        print("\n--- Unique Composers ---")
        unique_composers = set()
        for entry in main_index.entries:
            if valid_entry(entry, "composer"):
                unique_composers.add(entry.composer)
        for composer in sorted(unique_composers):
            print(composer)

    if args.stats:
        get_db_stats(main_index)


if __name__ == "__main__":
    main()
