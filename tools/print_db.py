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
    index_filepath = os.path.join(db_directory, RockboxDBFileType.INDEX.name)
    try:
        main_index = IndexFile.from_file(index_filepath)
        print(f"\nSuccessfully loaded {RockboxDBFileType.INDEX.name}:")
        print(main_index)  # Uses __repr__ of IndexFile
    except Exception as e:
        print(f"\nError loading {RockboxDBFileType.INDEX.name}: {e}")
        return

    # 2. Load all tag data files
    loaded_tag_files = {}
    print("\n--- Loading Tag Data Files ---")
    for db_type in RockboxDBFileType:
        if db_type == RockboxDBFileType.INDEX:
            continue  # Skip the index file, already loaded

        filepath = os.path.join(db_directory, db_type.name)
        if os.path.exists(filepath):
            try:
                tag_file = TagFile.from_file(filepath)
                print(f"Successfully loaded {db_type.name}: {tag_file}")
                loaded_tag_files[db_type.tag_index] = tag_file
            except Exception as e:
                print(f"Error loading {db_type.name}: {e}")
        else:
            print(f"Warning: {db_type.name} not found in {db_directory}")

    # 3. Print Sample Data from Index File Entries and link to TagFile data (where possible)
    print("\n--- Sample Data from Index File Entries ---")
    if not main_index.entries:
        print("No entries found in the main index file.")
        return

    for i, index_entry in enumerate(
        main_index.entries[:20]
    ):  # Print first 20 entries for brevity
        print(f"\n--- Index Entry {i} ---")
        print(f"  Raw Flags: {hex(index_entry.flag)} ({index_entry.get_flag_names()})")

        for tag_idx, seek_value in enumerate(index_entry.tag_seek):
            tag_name = TAG_TYPES[tag_idx]

            if tag_idx in FILE_TAG_INDICES:  # This is an offset into a tag file
                if tag_idx in loaded_tag_files:
                    tag_file = loaded_tag_files[tag_idx]
                    # To get the actual string, TagFile needs `get_entry_by_offset`
                    # For a robust solution, TagFile.from_file should build a map:
                    # self.entries_by_offset = {entry.offset_in_file: entry for entry in self.entries}

                    # For now, let's just indicate the offset and suggest a manual lookup or a simpler iteration
                    # A basic way to find it without modifying TagFile significantly:
                    found_tag_entry = None
                    for tf_entry in tag_file.entries:
                        # We need TagFileEntry to store the offset it was read from.
                        # For testing, let's temporarily assume it has `offset_in_file`
                        if (
                            hasattr(tf_entry, "offset_in_file")
                            and tf_entry.offset_in_file == seek_value
                        ):
                            found_tag_entry = tf_entry
                            break

                    if found_tag_entry:
                        print(
                            f"  {tag_name} (File Tag): '{found_tag_entry.tag_data}' (Offset: {seek_value})"
                        )
                    else:
                        print(
                            f"  {tag_name} (File Tag): Offset = {seek_value} (Entry not found at offset in loaded TagFile)"
                        )

                else:
                    print(
                        f"  {tag_name} (File Tag): Offset = {seek_value} (Tag file not loaded or missing)"
                    )
            else:  # This is an embedded numeric value
                print(f"  {tag_name} (Embedded Numeric): Value = {seek_value}")

    print("\n--- Database loading and sample data print complete ---")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/db_loader.py <path_to_rockbox_db_directory>")
        print("\nExample: python tools/db_loader.py /mnt/ipod/.rockbox/database")
        sys.exit(1)

    db_path_arg = sys.argv[1]
    if not os.path.isdir(db_path_arg):
        print(f"Error: Database directory '{db_path_arg}' does not exist.")
        sys.exit(1)

    # Run the loader
    load_and_print_rockbox_database(db_path_arg)
