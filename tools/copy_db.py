# Debugging and verification script for Rockbox database files.
#
# This script is useful for verifying the code can correctly both load and write
# a set of Rockbox database files.
#
# Given an input rockbox DB, it will read and then write out a new set of files
# to a specified output directory. It will then compare the original files with
# the newly written files to ensure they match byte-for-byte.

import argparse
import os
import filecmp

from rockbox_db_py.classes.db_file_type import RockboxDBFileType
from rockbox_db_py.classes.index_file import IndexFile
from rockbox_db_py.utils.defs import TAG_TYPES
from rockbox_db_py.utils.helpers import (
    load_rockbox_database,
    write_rockbox_database,
)

from typing import Optional


def load_and_write_rockbox_database(
    input_db_dir: str,
    output_db_dir: str,
):
    """
    Loads a Rockbox database from input_db_dir and writes it to output_db_dir
    using the new helper functions.
    """
    print(f"--- Processing Rockbox database ---")
    print(f"Input Directory: {input_db_dir}")
    print(f"Output Directory: {output_db_dir}")

    # The directory cleaning and creation logic is now handled by write_rockbox_database
    # but let's replicate the print for consistency with the original function's output.
    if os.path.exists(output_db_dir):
        print(f"Cleaning existing output directory: {output_db_dir}")

    # 1. Load the database using the helper function
    main_index: Optional[IndexFile] = load_rockbox_database(input_db_dir)

    if main_index is None:
        print("Failed to load the Rockbox database.")
        return  # Exit if loading failed

    # 2. Write the database to the new location using the helper function
    # auto_finalize is True by default in write_rockbox_database
    try:
        write_rockbox_database(main_index, output_db_dir, auto_finalize=False)
        print("Database writing and saving complete.")
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
        return True
    else:
        print("\nSome files differ from original. Review differences manually.")
        print(
            "  (Consider using a binary diff tool like 'diff' (Linux) or 'Beyond Compare' for detailed analysis.)"
        )

    return False


def compare_parsed_dbs(original_db: IndexFile, written_db: IndexFile):
    """
    Compares two parsed IndexFile objects field-by-field and entry-by-entry.
    Provides detailed output for any mismatches.
    """
    print("\n--- Comparing Parsed Database Objects (Field-by-Field) ---")
    all_parsed_match = True

    # 1. Compare header fields
    header_fields = ["magic", "datasize", "entry_count", "serial", "commitid", "dirty"]
    print("\n  >> Header Comparison <<")
    for field in header_fields:
        orig_val = getattr(original_db, field)
        written_val = getattr(written_db, field)
        if orig_val != written_val:
            print(
                f"    ❌ Header Field '{field}': Original={orig_val} ({hex(orig_val)}) | Written={written_val} ({hex(written_val)})"
            )
            all_parsed_match = False
        else:
            print(f"    ✅ Header Field '{field}': {orig_val} ({hex(orig_val)})")

    # 2. Compare entry counts
    if len(original_db.entries) != len(written_db.entries):
        print(
            f"    ❌ Entry Count: Original={len(original_db.entries)} | Written={len(written_db.entries)}"
        )
        all_parsed_match = False
    else:
        print(f"    ✅ Entry Count: {len(original_db.entries)}")

    # 3. Compare entries themselves (up to a certain limit or all if small)
    print("\n  >> Entry-by-Entry Comparison <<")
    compare_limit = min(len(original_db.entries), len(written_db.entries), 5)
    mismatch_found_in_entries = False

    for i in range(compare_limit):
        orig_entry = original_db.entries[i]
        written_entry = written_db.entries[i]

        entry_match = True
        # Compare raw tag_seek arrays and flags
        if orig_entry.tag_seek != written_entry.tag_seek:
            print(f"    ❌ Entry {i} (tag_seek) differs.")
            entry_match = False
        else:
            print(f"    ✅ Entry {i} (tag_seek) matches.")
        if orig_entry.flag != written_entry.flag:
            print(
                f"    ❌ Entry {i} (flag) differs: Original={hex(orig_entry.flag)} | Written={hex(written_entry.flag)}"
            )
            entry_match = False
        else:
            print(
                f"    ✅ Entry {i} (flag) matches: {hex(orig_entry.flag)} (matches written)"
            )

        # Also compare parsed tag values for common tags
        for tag_name in TAG_TYPES:
            orig_tag_val = getattr(orig_entry, tag_name)
            written_tag_val = getattr(written_entry, tag_name)
            if orig_tag_val != written_tag_val:
                print(
                    f"      ❌ Entry {i} Tag '{tag_name}': Original='{orig_tag_val}' | Written='{written_tag_val}'"
                )
                entry_match = False
            else:
                print(
                    f"      ✅ Entry {i} Tag '{tag_name}': '{orig_tag_val}' (matches written)"
                )

        if not entry_match:
            mismatch_found_in_entries = True
            all_parsed_match = False
        else:
            if i < 5:
                print(f"    ✅ Entry {i} matches parsed data.")

    if not mismatch_found_in_entries:
        print(f"    All {compare_limit} compared entries match parsed data.")
    elif compare_limit < len(original_db.entries):
        print(f"    ... (Comparison limited to first {compare_limit} entries)")

    # 4. Compare loaded tag files themselves (as objects)
    print("\n  >> Loaded Tag Files Comparison (Metadata) <<")
    orig_loaded_tags = original_db.loaded_tag_files
    written_loaded_tags = written_db.loaded_tag_files

    if len(orig_loaded_tags) != len(written_loaded_tags):
        print(
            f"    ❌ Number of loaded tag files differs: Original={len(orig_loaded_tags)} | Written={len(written_loaded_tags)}"
        )
        all_parsed_match = False
    else:
        print(f"    ✅ Number of loaded tag files matches: {len(orig_loaded_tags)}")

        for tag_idx in orig_loaded_tags:
            orig_tag_file = orig_loaded_tags.get(tag_idx)
            written_tag_file = written_loaded_tags.get(tag_idx)

            if not orig_tag_file or not written_tag_file:
                print(
                    f"      ❌ Tag file {tag_idx} missing from one of the loaded sets."
                )
                all_parsed_match = False
                continue

            tag_filename = orig_tag_file.db_file_type.filename

            # Compare basic properties of TagFile objects
            tag_file_props = ["magic", "datasize", "entry_count"]
            tag_file_match = True
            print(f"      - {tag_filename}:")
            for prop in tag_file_props:
                orig_prop_val = getattr(orig_tag_file, prop)
                written_prop_val = getattr(written_tag_file, prop)
                if orig_prop_val != written_prop_val:
                    print(
                        f"        ❌ Prop '{prop}': Original={orig_prop_val} | Written={written_prop_val}"
                    )
                    tag_file_match = False
                else:
                    print(
                        f"        ✅ Prop '{prop}': {orig_prop_val} (matches written)"
                    )

            # Get all the entries for this tag file
            orig_entires = orig_tag_file.entries
            written_entries = written_tag_file.entries

            # Get the overlap and unique entries for each
            orig_entrys = {entry.tag_data for entry in orig_entires}
            written_entrys = {entry.tag_data for entry in written_entries}
            common_entrys = orig_entrys.intersection(written_entrys)
            orig_uniques = orig_entrys - common_entrys
            written_uniques = written_entrys - common_entrys

            # Print the first 5 common entries
            if len(common_entrys) > 0:
                print(
                    f"        ✅ Common entries found: {len(common_entrys)} (showing first 5):"
                )
                for entry in list(common_entrys)[:5]:
                    print(f"          - Common Entry: {entry}")
            else:
                print("        ❌ No common entries found.")

            if len(orig_uniques) == 0 and len(written_uniques) == 0:
                print(
                    f"        ✅ No unique entries in either tag file: {len(common_entrys)}"
                )
            else:
                print(
                    f"        ❌ Unique entries found: Original={len(orig_uniques)} | Written={len(written_uniques)}"
                )

            if len(orig_uniques) > 0:
                print(
                    f"        ❌ Original tag file '{tag_filename}' has {len(orig_uniques)} unique entries:"
                )
                tag_file_match = False
                for entry in list(orig_uniques)[:5]:  # Show first 5 unique entries
                    print(f"          - Unique Original Entry: {entry}")
            if len(written_uniques) > 0:
                print(
                    f"        ❌ Written tag file '{tag_filename}' has {len(written_uniques)} unique entries:"
                )
                tag_file_match = False
                for entry in list(written_uniques)[:5]:
                    print(f"          - Unique Written Entry: {entry}")

            # Optionally, compare the entries within the TagFile objects
            if len(orig_tag_file.entries) != len(written_tag_file.entries):
                print(
                    f"        ❌ Entry count differs: Original={len(orig_tag_file.entries)} | Written={len(written_tag_file.entries)}"
                )
                tag_file_match = False
            else:
                for j in range(
                    min(len(orig_tag_file.entries), len(written_tag_file.entries), 5)
                ):  # Compare first 5 TagFileEntries
                    orig_tf_entry = orig_tag_file.entries[j]
                    written_tf_entry = written_tag_file.entries[j]
                    if orig_tf_entry.tag_data != written_tf_entry.tag_data:
                        print(
                            f"          ❌ Entry {j} data differs: Original='{orig_tf_entry.tag_data}' | Written='{written_tf_entry.tag_data}'"
                        )
                        tag_file_match = False
                        break
                    if orig_tf_entry.idx_id != written_tf_entry.idx_id:
                        print(
                            f"          ❌ Entry {j} idx_id differs: Original={orig_tf_entry.idx_id} | Written={written_tf_entry.idx_id}"
                        )
                        tag_file_match = False
                        break

            if tag_file_match:
                print(f"        ✅ All parsed metadata for {tag_filename} matches.")
            else:
                print(f"        ❌ Parsed metadata for {tag_filename} differs.")
                all_parsed_match = False

    if all_parsed_match:
        print("\nAll parsed database objects (headers and entries) match!")
    else:
        print("\nDifferences found in parsed database objects. See details above.")


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
        success = compare_files(args.input_db_dir, args.output_db_dir)
        if not success:
            compare_parsed_dbs(
                IndexFile.from_file(
                    os.path.join(args.input_db_dir, RockboxDBFileType.INDEX.filename)
                ),
                IndexFile.from_file(
                    os.path.join(args.output_db_dir, RockboxDBFileType.INDEX.filename)
                ),
            )

    print("\n--- Process finished ---")


if __name__ == "__main__":
    main()
