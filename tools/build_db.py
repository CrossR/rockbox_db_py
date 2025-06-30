# Tool to build a Rockbox database on the PC filesystem, using Python.
#
# Your database must be structured identically to the Rockbox database
# on the device, with the same file types and directory structure.
#
# This will find all files in the input directory, parse their metadata,
# and write the database files to the output directory.
#
# Usage:
#   python build_py.py <input_music_dir> <rockbox_root_music_dir> <output_db_dir> [--stats]
#
#  <input_music_dir> is the path to the directory containing music files to index.
#  <rockbox_root_music_dir> is the relative path to the music directory in Rockbox.
#        For example, if your music is in "Music" in the root of the rockbox drive,
#        you would use "Music" as the relative path.
#  <output_db_dir> is the path to the directory where the new database files will be written.


import argparse
import os

from rockbox_db_py.utils.helpers import (
    write_rockbox_database,
    scan_music_directory,
    build_rockbox_database_from_music_files,
)
from rockbox_db_py.utils.defs import TagTypeEnum

from canonicalize import (
    build_genre_canonical_map,
    perform_single_genre_canonicalization,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build a Rockbox database from music files on the filesystem."
    )
    parser.add_argument(
        "input_music_dir",
        type=str,
        help="Path to the directory containing music files to index.",
    )
    parser.add_argument(
        "output_rockbox_path",
        type=str,
        help="Relative path to the files in Rockbox relative to the root (i.e. /Music/)",
    )
    parser.add_argument(
        "output_db_dir",
        type=str,
        help="Path to the directory where the new database files will be written (will be cleaned if it exists).",
    )

    # Optional args
    parser.add_argument(
        "--num_processes",
        type=int,
        default=None,
        help="Number of processes to use for parsing music files. Defaults to all available CPU cores.",
    )
    parser.add_argument(
        "--genre-file",
        type=str,
        default=None,
        help="Path to a genre file for canonicalizing genres. If provided, will canonicalize genres in the database using this file.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_false",
        dest="progress",
        help="Disable progress bar when scanning music files.",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="After building the database, print statistics by loading the database and printing stats.",
    )

    args = parser.parse_args()
    return args


def main():
    args = parse_args()

    input_music_dir = args.input_music_dir
    output_db_dir = args.output_db_dir

    print(f"Processing music files from: {input_music_dir}")
    music_files = scan_music_directory(
        input_music_dir, num_processes=args.num_processes, show_progress=args.progress
    )

    if not music_files:
        print("No music files found to index. Exiting.")
        return

    print(f"Found {len(music_files)} music files to index.")

    # Process the music files to swap the paths to the Rockbox relative paths
    print("Processing music files to set Rockbox relative paths...")
    for mf in music_files:
        # Remove the input_music_dir prefix from the filepath
        # I.e. F:/Music/Artist/Album/Song.mp3 becomes
        # Artist/Album/Song.mp3
        relative_path = os.path.relpath(mf.filepath, start=input_music_dir)

        # Then, move to the Rockbox relative path
        # I.e. Artist/Album/Song.mp3 becomes /Music/Artist/Album/Song.mp3
        rockbox_relative_path = os.path.join(args.output_rockbox_path, relative_path)

        # Replace any errant backslashes with forward slashes
        rockbox_relative_path = rockbox_relative_path.replace("\\", "/")

        # Set the new filepath
        mf.filepath = rockbox_relative_path

    print("Example music file:")
    print(music_files[0].info())

    # Build the Rockbox database in memory
    print("Building Rockbox database in memory...")
    main_index = build_rockbox_database_from_music_files(
        music_files,
    )
    print("Rockbox database built in memory.")

    # Use canonicalize.py to canonicalize the genres
    if args.genre_file:
        print(f"Using genre file: {args.genre_file}")
        genre_canonical_map = build_genre_canonical_map(
            args.genre_file, roll_up_threshold=10
        )

        print("Canonicalizing genres in the database...")
        perform_single_genre_canonicalization(
            main_index,
            genre_canonical_map,
        )
        print("Genres canonicalized successfully.")
    else:
        print("No genre file provided. Skipping genre canonicalization.")

    # Build a sort map for sorting entries in a consistent way
    print("Building sort map for titles...")
    sort_map = {TagTypeEnum.title: {}}
    sort_map[TagTypeEnum.title] = {
        mf.title: mf.filepath for mf in music_files if mf.title
    }
    print("Sort map for titles built.")

    # Write the database to the output directory
    print(f"Writing Rockbox database to: {output_db_dir}")
    write_rockbox_database(
        main_index, output_db_dir, auto_finalize=True, sort_map=sort_map
    )
    print("Rockbox database written successfully.")

    print("Finished!")


if __name__ == "__main__":
    main()
