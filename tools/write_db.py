# Debugging and verification script for Rockbox database files.
#
# This script is useful for verifying the code can correctly both load and write
# a set of Rockbox database files.

import argparse
import os
import shutil
import filecmp

from rockbox_db_py.classes.db_file_type import RockboxDBFileType
from rockbox_db_py.classes.index_file import IndexFile
from rockbox_db_py.classes.tag_file import (
    TagFile,
)

from typing import Dict


def load_and_write_rockbox_database(
    input_db_dir: str,
    output_db_dir: str,
):
    """
    Loads a Rockbox database from input_db_dir and writes it to output_db_dir.
    """
    print(f"--- Processing Rockbox database ---")
    print(f"Input Directory: {input_db_dir}")
    print(f"Output Directory: {output_db_dir}")

    # Ensure output directory exists and is empty (or clean it)
    if os.path.exists(output_db_dir):
        print(f"Cleaning existing output directory: {output_db_dir}")
        shutil.rmtree(output_db_dir)
    os.makedirs(output_db_dir, exist_ok=True)

    # 1. Load the database
    index_filepath = os.path.join(input_db_dir, RockboxDBFileType.INDEX.filename)
    main_index: IndexFile = None
    try:
        print(f"\nLoading database from '{input_db_dir}'...")
        main_index = IndexFile.from_file(index_filepath)
        print(f"Successfully loaded {main_index.db_file_type.filename}: {main_index}")
    except FileNotFoundError as e:
        print(f"Error: Input database file not found: {e}")
        return
    except Exception as e:
        print(f"Error loading database: {e}")
        return

    # 2. Write the database to the new location
    print(f"\nWriting database to '{output_db_dir}'...")
    try:
        # Write the main index file
        output_index_filepath = os.path.join(
            output_db_dir, RockboxDBFileType.INDEX.filename
        )
        main_index.to_file(output_index_filepath)
        print(f"Successfully wrote {RockboxDBFileType.INDEX.filename}")

        # Write all associated tag files
        # main_index._loaded_tag_files holds TagFile objects (tag_index: TagFile instance)
        loaded_tag_files: Dict[int, TagFile] = (
            main_index.loaded_tag_files
        )  # Access via public property
        for tag_index, tag_file_obj in loaded_tag_files.items():
            db_file_type = RockboxDBFileType.from_tag_index(
                tag_index
            )  # Get the enum member
            output_tag_filepath = os.path.join(output_db_dir, db_file_type.filename)
            tag_file_obj.to_file(output_tag_filepath)
            print(f"Successfully wrote {db_file_type.filename}")

        print("\nDatabase writing complete.")

    except Exception as e:
        print(f"Error writing database: {e}")
        return


def compare_files(input_db_dir, output_db_dir):
    print("\n--- Comparing original and written files ---")
    all_files_match = True
    files_to_compare = [RockboxDBFileType.INDEX.filename] + [
        ft.filename
        for ft in RockboxDBFileType
        if ft != RockboxDBFileType.INDEX and ft.tag_index is not None
    ]

    for filename in files_to_compare:
        original_path = os.path.join(input_db_dir, filename)
        written_path = os.path.join(output_db_dir, filename)

        if not os.path.exists(original_path):
            print(f"  Warning: Original file not found for comparison: {original_path}")
            continue
        if not os.path.exists(written_path):
            print(f"  Warning: Written file not found for comparison: {written_path}")
            all_files_match = False
            continue

        if filecmp.cmp(original_path, written_path, shallow=False):
            print(f"  ✅ {filename} matches original (byte-for-byte)")
        else:
            print(f"  ❌ {filename} differs from original!")
            all_files_match = False

    if all_files_match:
        print("\nAll compared files match byte-for-byte!")
    else:
        print("\nSome files differ from original. Review differences manually.")
        print(
            "  (Consider using a binary diff tool like 'diff' (Linux) or 'Beyond Compare' for detailed analysis.)"
        )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Load a Rockbox database and write it to a new directory."
    )
    parser.add_argument(
        "input_db_dir",
        type=str,
        help="Path to the directory containing original Rockbox database files.",
    )
    parser.add_argument(
        "output_db_dir",
        type=str,
        help="Path to the directory where the new database files will be written (will be cleaned if it exists).",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="After writing, compare the new files byte-for-byte with the originals.",
    )

    args = parser.parse_args()
    return args


def main():
    args = parse_args()
    load_and_write_rockbox_database(args.input_db_dir, args.output_db_dir)

    if args.compare:
        compare_files(args.input_db_dir, args.output_db_dir)

    print("\n--- Process finished ---")


if __name__ == "__main__":
    main()
