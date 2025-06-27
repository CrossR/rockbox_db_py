# Debugging and verification script for Rockbox database files.
#
# This script is useful for verifying that the code can correctly read and process
# a set of Rockbox database files.
import argparse
from collections import defaultdict
import os

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


def debug_database_integrity(main_index: IndexFile):
    """
    Performs integrity checks on a loaded database, focusing on post-modification state.
    - Verifies CRC32 values for DELETED entries (type check).
    - Checks data integrity of newly created (non-DELETED) entries.
    - Confirms sorting of the genre TagFile.
    """
    print("\n--- Running Database Integrity Debug Checks ---")

    genre_file_type = RockboxDBFileType.GENRE
    genre_tag_file = main_index.loaded_tag_files.get(genre_file_type.tag_index)

    if not genre_tag_file:
        print(
            f"  Warning: Genre tag file ({genre_file_type.filename}) not loaded. Skipping genre-specific checks."
        )

    # --- Section 1: Check Deleted Entries for CRC32 ---
    print("\n  >> Section 1: Verifying DELETED Entries (CRC32 Check) <<")
    deleted_entries_checked = 0
    for i, entry in enumerate(main_index.entries):
        if entry.flag & FLAG_DELETED:
            deleted_entries_checked += 1
            # Note: get_parsed_tag_value for deleted string tags will return None
            # because the tag_seek is now a CRC32, not an offset.
            print(f"    - DELETED Entry {i}: ")

            all_crc32_ok_type = True
            for tag_idx in FILE_TAG_INDICES:
                raw_seek_val = entry.tag_seek[tag_idx]
                tag_name = TagTypeEnum(tag_idx).name

                # For DELETED entries, tag_seek for FILE_TAG_INDICES should be an int (CRC32 or sentinel)
                if not isinstance(raw_seek_val, int):
                    print(
                        f"      ❌ {tag_name} (tag_seek): Expected int (CRC32/sentinel), got {type(raw_seek_val).__name__} ({raw_seek_val})"
                    )
                    all_crc32_ok_type = False
                elif raw_seek_val == 0xFFFFFFFF:
                    print(
                        f"      ✅ {tag_name} (tag_seek): Sentinel (0xFFFFFFFF) - Correct for missing data."
                    )
                else:
                    # It's an integer. This is what we expect for a CRC32.
                    # We can't verify the exact CRC32 here without the original string data and Rockbox's exact CRC logic,
                    # but we confirm it's an int.
                    print(
                        f"      ✅ {tag_name} (tag_seek): CRC32/Value={hex(raw_seek_val)}"
                    )

            if not all_crc32_ok_type:
                print(f"      Problematic DELETED entry type detected at index {i}.")
            if deleted_entries_checked >= 10:  # Limit output for brevity
                print("    ... (showing first 10 DELETED entries)")
                break

    if deleted_entries_checked == 0:
        print("    No DELETED entries found to check.")
    else:
        print(f"    Checked {deleted_entries_checked} DELETED entries.")

    # --- Section 2: Check New Entry Data Integrity (Non-Genre Fields) ---
    print("\n  >> Section 2: Verifying NEW Entry Data (Non-Genre Fields) <<")
    new_entries_checked = 0
    for i, entry in enumerate(main_index.entries):
        # A "new" entry is one that is NOT DELETED, and whose genre is one of the individual split genres.
        # This is a heuristic. We assume if it's not deleted and its genre is a simple string, it's new.
        if not (entry.flag & FLAG_DELETED):
            genre_val = entry.get_parsed_tag_value(TagTypeEnum.genre)
            if (
                genre_val is not None and ";" not in genre_val
            ):  # If it's an individual genre
                new_entries_checked += 1
                print(f"    - NEW Entry {i} (Genre: '{genre_val}'):")
                print(f"      Filename: '{entry.filename}'")
                print(f"      Title: '{entry.title}'")
                print(f"      Album: '{entry.album}'")
                print(
                    f"      Year: '{entry.year}'"
                )  # Check an embedded numeric tag (like Year)

                # Basic validation: Check if essential tags are present after copy
                if entry.filename is None or entry.title is None:
                    print(f"      ❌ Missing filename or title for new entry {i}.")
                if entry.album is None:
                    print(f"      ❌ Missing album for new entry {i}.")
                if entry.year is None:
                    print(f"      ❌ Missing year for new entry {i}.")

                if new_entries_checked >= 10:  # Limit output
                    print("    ... (showing first 10 new entries)")
                    break

    if new_entries_checked == 0:
        print("    No new (non-deleted, individual genre) entries found to check.")
    else:
        print(f"    Checked {new_entries_checked} new entries.")

    # --- Section 3: Confirm Genre TagFile Sorting ---
    print("\n  >> Section 3: Verifying Genre TagFile Sorting <<")
    if genre_tag_file:
        is_sorted_programmatically = True
        for i in range(len(genre_tag_file.entries) - 1):
            current_entry_tag_data_lower = genre_tag_file.entries[i].tag_data.lower()
            next_entry_tag_data_lower = genre_tag_file.entries[i + 1].tag_data.lower()

            if current_entry_tag_data_lower > next_entry_tag_data_lower:
                print(
                    f"      ❌ Genre TagFile is NOT sorted at index {i}: '{genre_tag_file.entries[i].tag_data}' comes before '{genre_tag_file.entries[i+1].tag_data}'"
                )
                is_sorted_programmatically = False
                break

        if is_sorted_programmatically:
            print(
                "    ✅ Genre TagFile (database_2.tcd) is programmatically confirmed to be sorted alphabetically."
            )
        else:
            print(
                "    ❌ Genre TagFile (database_2.tcd) is NOT sorted. This could cause issues on device."
            )

        print("\n    Visual inspection of first 10 genre TagFileEntries:")
        for i, entry in enumerate(genre_tag_file.entries[:10]):
            print(
                f"      - {entry.tag_data} (offset: {hex(entry.offset_in_file) if entry.offset_in_file is not None else 'N/A'})"
            )
        if len(genre_tag_file.entries) > 10:
            print("    ... (showing first 10 entries)")

            # Visual inspection of first 10 genre TagFileEntries:
            num_genre_entries = len(genre_tag_file.entries)
            print(f"    Total genre entries: {num_genre_entries}")
            print(
                "\n    Visual inspection of first 10 genre TagFileEntries (from sorted unique list):"
            )
            for i, entry in enumerate(genre_tag_file.entries[:10]):
                print(
                    f"      - {entry.tag_data} (offset: {hex(entry.offset_in_file) if entry.offset_in_file is not None else 'N/A'})"
                )
            if len(genre_tag_file.entries) > 10:
                print("    ... (showing first 10 entries)")
    else:
        print("    Genre tag file not loaded. Cannot confirm sorting.")

    print("\n--- Database Integrity Debug Checks Complete ---")


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
    parser.add_argument(
        "--debug", action="store_true", help="Run integrity checks on the database."
    )

    args = parser.parse_args()

    # If nothing is specified, default to printing albums
    if not any([args.stats, args.artists, args.tracks, args.genres, args.debug]):
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

    # Debugging integrity checks
    if args.debug:
        debug_database_integrity(main_index)

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
        for entry in main_index.entries:
            if valid_entry(entry, "genre"):
                unique_genres.add(entry.genre)
        for genre in sorted(unique_genres):
            print(genre)

    if args.stats:
        get_db_stats(main_index)


if __name__ == "__main__":
    main()
