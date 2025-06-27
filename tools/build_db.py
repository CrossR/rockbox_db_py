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
import multiprocessing

from rockbox_db_py.utils.helpers import (
    load_rockbox_database,
    write_rockbox_database,
    scan_music_directory,
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
        input_music_dir, num_processes=args.num_processes
    )

    if not music_files:
        print("No music files found to index. Exiting.")
        return

    print(f"Found {len(music_files)} music files to index.")

    # Debug print the first 10 music files
    print("First 10 music files:")
    for i, music_file in enumerate(music_files[:10]):
        print(f"{i + 1}: {music_file.filepath} - {music_file.title or 'No Title'}")
        print(f"    Album: {music_file.album or 'No Album'}")
        print(f"    Artist: {music_file.artist or 'No Artist'}")
        print(f"    Track: {music_file.tracknumber or 'No Track Number'}")
        print(f"    Genre: {music_file.genre or 'No Genre'}")
        print(f"    Year: {music_file.year or 'Unknown'}")
        print(f"    Length: {music_file.length} seconds")
        print(f"    Bitrate: {music_file.bitrate} bps")


    print("Finished!")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
