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

from rockbox_db_py.utils.helpers import (
    load_rockbox_database,
    write_rockbox_database,
    scan_music_directory,
    build_rockbox_database_from_music_files,
)
from rockbox_db_py.utils.defs import TagTypeEnum


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

    # DEBUG: Load the existing database files
    existing_path = "D:\\User Files\\Downloads\\rockbox\\clean"
    existing_db = load_rockbox_database(existing_path)

    old_song_entries = [
        e._loaded_tag_files[TagTypeEnum.filename.value] for e in existing_db.entries
    ][0]
    print(f"Loaded existing database with {len(existing_db.entries)} entries.")
    old_song_paths = [e.tag_data for e in old_song_entries.entries]
    print(f"Found {len(old_song_paths)} existing song paths in the database.")
    print("First 10 existing song paths:")
    for path in old_song_paths[:10]:
        print(f"  {path}")

    # Use the existing database to sort the music files
    old_to_index_map = {old_song_paths[i]: i for i in range(len(old_song_paths))}
    new_to_old_filepath_map = {
        mf.filepath: mf.filepath.replace(input_music_dir, "/Music/").replace("\\", "/")
        for mf in music_files
    }

    print("Mapping new music files to old file paths...")
    music_files.sort(
        key=lambda mf: (
            old_to_index_map.get(
                new_to_old_filepath_map.get(mf.filepath, ""),
                len(old_song_paths) + 1,  # If not found, place at the end
            )
            if new_to_old_filepath_map.get(mf.filepath, "") in old_to_index_map
            else len(old_song_paths)
        )
    )
    print("Finished sorting new music files based on existing database.")

    # Build the Rockbox database in memory
    print("Building Rockbox database in memory...")
    main_index = build_rockbox_database_from_music_files(
        music_files,
        input_folder=input_music_dir,
        output_rockbox_path_prefix=args.output_rockbox_path,
    )
    print("Rockbox database built in memory.")

    # Build a sort map for sorting entries in a consistent way
    print("Building sort map for titles...")
    sort_map = {TagTypeEnum.title: {}}
    sort_map[TagTypeEnum.title] = {
        mf.title: mf.filepath for mf in music_files if mf.title
    }
    print("Sort map for titles built.")

    print("First 10 entries in the sort map:")
    for i, (key, value) in enumerate(sort_map[TagTypeEnum.title].items()):
        if i >= 10:
            break
        print(f"  {key}: {value}")

    # Write the database to the output directory
    print(f"Writing Rockbox database to: {output_db_dir}")
    write_rockbox_database(
        main_index, output_db_dir, auto_finalize=True, sort_map=sort_map
    )
    print("Rockbox database written successfully.")

    print("Finished!")


if __name__ == "__main__":
    main()
