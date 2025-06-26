# tools/debug_db_links.py
#
# A debugging tool to analyze tag links (offsets) between original and
# newly generated Rockbox database files, focusing on file-based tags.

import argparse
import os
import sys

from rockbox_db_py.classes.db_file_type import RockboxDBFileType
from rockbox_db_py.classes.index_file import IndexFile
from rockbox_db_py.classes.tag_file import TagFile
from rockbox_db_py.classes.index_file_entry import IndexFileEntry
from rockbox_db_py.classes.tag_file_entry import TagFileEntry
from rockbox_db_py.utils.defs import TagTypeEnum, FILE_TAG_INDICES, FLAG_DELETED


def load_database_from_dir(db_directory: str, db_name: str) -> IndexFile | None:
    """Helper to load a database from a given directory."""
    index_filepath = os.path.join(db_directory, RockboxDBFileType.INDEX.filename)
    try:
        db = IndexFile.from_file(index_filepath)
        print(f"Loaded {db_name} DB from '{db_directory}': {db}")
        return db
    except FileNotFoundError:
        print(f"Error: {db_name} DB directory '{db_directory}' not found or missing index file.")
        return None
    except Exception as e:
        print(f"Error loading {db_name} DB from '{db_directory}': {e}")
        return None


def resolve_tag_data(entry: IndexFileEntry, tag_enum: TagTypeEnum) -> str | int | None:
    """Resolves a tag's value (string or int), handling raw offsets and objects."""
    # This function needs to be careful: entry.tag_seek[tag_enum.value] could be
    # an int (offset/CRC32) or a TagFileEntry object (during modification).
    # get_parsed_tag_value already handles this, so we'll just use it.
    return getattr(entry, tag_enum.name)


def get_first_multi_genre_entries(db: IndexFile, limit: int = 5) -> list[IndexFileEntry]:
    """Retrieves a list of the first few non-deleted multi-genre entries."""
    multi_genre_entries = []
    for entry in db.entries:
        if not (entry.flag & FLAG_DELETED):
            genre_str = entry.genre
            if genre_str and ';' in genre_str:
                multi_genre_entries.append(entry)
                if len(multi_genre_entries) >= limit:
                    break
    return multi_genre_entries


def find_entry_by_filename(db: IndexFile, filename_to_find: str) -> IndexFileEntry | None:
    """Finds a non-deleted entry in a DB by its filename."""
    for entry in db.entries:
        if not (entry.flag & FLAG_DELETED) and entry.filename == filename_to_find:
            return entry
    return None


def debug_db_links(original_db_dir: str, modified_db_dir: str):
    """
    Loads original and modified databases and debugs tag linking issues.
    """
    print("--- Debugging Database Links ---")

    original_db = load_database_from_dir(original_db_dir, "Original")
    if not original_db: return

    modified_db = load_database_from_dir(modified_db_dir, "Modified")
    if not modified_db: return

    # Get a few problematic entries from the ORIGINAL database
    problem_entries_original = get_first_multi_genre_entries(original_db, limit=10)
    if not problem_entries_original:
        print("No multi-genre entries found in original DB to debug.")
        return

    print("\n--- Detailed Link Comparison for Problematic Entries ---")
    file_based_tags_to_check = [
        TagTypeEnum.filename, TagTypeEnum.title, TagTypeEnum.artist,
        TagTypeEnum.album, TagTypeEnum.composer, TagTypeEnum.comment,
        TagTypeEnum.albumartist, TagTypeEnum.grouping, TagTypeEnum.canonicalartist,
        TagTypeEnum.genre # Include genre to see its direct change
    ]

    for i, orig_entry in enumerate(problem_entries_original):
        print(f"\n===== ENTRY {i+1} =====")
        print(f"Original filename: '{orig_entry.filename}'")
        print(f"Original title:    '{orig_entry.title}'")
        print(f"Original genre:    '{orig_entry.genre}'") # This is the multi-genre string

        # Capture all original resolved values into a dictionary first
        orig_resolved_values = {}
        for tag_enum in file_based_tags_to_check:
            orig_resolved_values[tag_enum] = resolve_tag_data(orig_entry, tag_enum)


        print("\n  >>> Original DB Link Details <<<")
        for tag_enum in file_based_tags_to_check:
            raw_offset_orig = orig_entry.tag_seek[tag_enum.value]
            # Use the pre-captured value for printing
            resolved_value_orig_current = orig_resolved_values[tag_enum]
            print(f"    {tag_enum.name:<18}: Raw={hex(raw_offset_orig) if isinstance(raw_offset_orig, int) else raw_offset_orig} | Resolved='{resolved_value_orig_current}'")

        # Find corresponding entry in the modified DB by filename
        corresponding_mod_entry = find_entry_by_filename(modified_db, orig_entry.filename)
        if not corresponding_mod_entry:
            print(f"  Warning: Could not find corresponding entry for filename '{orig_entry.filename}' in modified DB.")
            continue

        print("\n  >>> Modified DB Link Details <<<")
        for tag_enum in file_based_tags_to_check:
            raw_offset_mod = corresponding_mod_entry.tag_seek[tag_enum.value]
            resolved_value_mod = resolve_tag_data(corresponding_mod_entry, tag_enum)
            print(f"    {tag_enum.name:<18}: Raw={hex(raw_offset_mod) if isinstance(raw_offset_mod, int) else raw_offset_mod} | Resolved='{resolved_value_mod}'")

            # Perform direct comparison here
            # Retrieve the correct original value from the dictionary for comparison
            original_value_for_this_tag = orig_resolved_values[tag_enum]

            if tag_enum != TagTypeEnum.genre: # Genre is expected to change
                if original_value_for_this_tag != resolved_value_mod:
                    print(f"      ❌ MISMATCH! Original='{original_value_for_this_tag}' | Modified='{resolved_value_mod}'")
            else: # This is the genre tag
                # For genre, we expect it to be individual, not multi-valued
                if resolved_value_mod and ';' in resolved_value_mod:
                    print(f"      ❌ MISMATCH! Modified genre is still multi-valued: '{resolved_value_mod}'")
                elif resolved_value_mod and original_value_for_this_tag == resolved_value_mod:
                    # This means the original multi-genre string is still present, which is also a mismatch for the goal.
                    print(f"      ❌ MISMATCH! Modified genre '{resolved_value_mod}' is same as original multi-genre.")


    print("\n--- Debugging Complete ---")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Debugs links between original and modified Rockbox database files."
    )
    parser.add_argument(
        "original_db_path",
        type=str,
        help="Path to the directory containing the ORIGINAL Rockbox database files.",
    )
    parser.add_argument(
        "modified_db_path",
        type=str,
        help="Path to the directory containing the NEWLY WRITTEN (modified) Rockbox database files.",
    )

    args = parser.parse_args()

    debug_db_links(args.original_db_path, args.modified_db_path)