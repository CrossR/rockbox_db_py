# tools/canonicalize.py
#
# This tool loads a Rockbox database, performs genre canonicalization,
# and saves the modified database. Canonicalization means converting
# here means taking a specific genre, say "Acid House" and moving it
# to a more general genre, such as "House".
#
# Usage:
# python canonicalize.py <db_path> <output_db_path> <genre-file> [--dry-run]

import argparse
from collections import Counter
import string
import sys
from typing import Optional, List, Dict

import yaml

from rockbox_db_py.classes.index_file import IndexFile
from rockbox_db_py.utils.defs import TagTypeEnum, FLAG_DELETED
from rockbox_db_py.classes.tag_file import TagFile
from rockbox_db_py.classes.tag_file_entry import TagFileEntry
from rockbox_db_py.utils.helpers import load_rockbox_database, write_rockbox_database

# Define a type alias for a genre map
# A genre map is a dictionary where keys are genre names
# and values are either:
# - a string representing a parent genre, or
# - a list of sub-genres (which can be strings or nested dictionaries).
GenreMap = Dict[str, str | List[str | Dict[str, List]]]


def get_sub_genres(
    parent_genre: str, genres: str | List[str] | GenreMap
) -> Dict[str, str]:
    """Recursively retrieves all sub-genres for a given genre.
    Args:
        parent_genre: The name of the parent genre.
        genres: A dictionary representing a genre and its sub-genres.
    Returns:
        A dictionary mapping sub-genre names to their parent genre name.
    """

    sub_genres = {}

    # Deal with the easiest case first: Is the GenreMap a simple string?
    if isinstance(genres, str):
        # If it's a string, it means this is a leaf genre with no sub-genres.
        sub_genres[genres.casefold()] = parent_genre.casefold()
        return sub_genres

    # Is it a list?
    elif isinstance(genres, list):
        # If it's a list, we need to iterate through each item,
        # recursively calling this function for each item.
        for item in genres:
            results = get_sub_genres(parent_genre, item)
            sub_genres.update(results)

    # Finally, if its a dictionary, we assume it has a single key
    # which is the genre name, and its value is either a string or a list of
    # sub-genres.
    # This is the case for nested genres.
    elif isinstance(genres, dict):
        sub_genre = next(iter(genres))  # Get the first (and only) key
        sub_genre_value = genres[sub_genre]

        # Add the sub-genre to the map, pointing to itself.
        sub_genres[sub_genre.casefold()] = sub_genre.casefold()

        # Recursively get sub-genres for this sub-genre
        results = get_sub_genres(sub_genre.casefold(), sub_genre_value)
        sub_genres.update(results)

    else:
        raise ValueError(
            f"Invalid genre structure: expected str, list, or dict, got {type(genres)}"
        )

    return sub_genres


def build_genre_canonical_map(genre_map_filepath: str) -> Dict[str, str]:
    """
    Parses a YAML file containing genre hierarchies and builds a canonical map.

    Args:
        genre_map_filepath: Path to the YAML file defining genre hierarchies.

    Returns:
        A dictionary mapping lowercased sub-genre names to their lowercased
        canonical parent names.
    """
    canonical_map: Dict[str, str] = {}

    try:
        with open(genre_map_filepath, "r", encoding="utf-8") as f:
            genre_data = yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Genre mapping file '{genre_map_filepath}' does not exist."
        )
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Error parsing YAML file '{genre_map_filepath}': {e}")

    if not isinstance(genre_data, list):
        raise ValueError("Genre mapping YAML should be a list of top-level genres.")

    # Build a map between sub-genres and their canonical parents
    # Entries here look like:
    # {"rock": ["rock", "hard rock", "soft rock", {"alternative rock": ["indie-rock", "britpop"]]}
    for genre_dict in genre_data:
        if len(genre_dict.keys()) != 1:
            raise ValueError(
                "Each top-level genre in the YAML file should be a single key."
            )

        genre = str(list(genre_dict.keys())[0])
        sub_genres = genre_dict.values()

        # Add the top-level genre itself to the map
        canonical_map[genre.casefold()] = genre.casefold()

        for sub_genre in sub_genres:
            result = get_sub_genres(genre.casefold(), sub_genre)
            canonical_map.update(result)

    # At this point we have a map where keys are sub-genres and values are their
    # canonical parent genres, all in lowercase.
    return canonical_map


def _select_canonical_genre_for_entry(
    original_genre_str: Optional[str], genre_canonical_map: Dict[str, str]
) -> Optional[str]:
    """
    Selects the most appropriate single canonical genre for an entry from its
    original (potentially multi-valued) genre string, using a canonicalization map.

    Logic:
    1. Splits the original genre string into individual genres.
    2. Maps each individual genre to its canonical form using genre_canonical_map.
    3. Counts occurrences of each canonical genre.
    4. Chooses the most frequent canonical genre.
    5. In case of a tie in frequency, selects the canonical genre that appeared
       first in the original split list.

    Args:
        original_genre_str: The original genre string for the entry (e.g., "Rock; Pop").
        genre_canonical_map: A dictionary mapping sub-genres to their canonical forms.

    Returns:
        The chosen single canonical genre string (lowercase), or None if no valid
        genre can be determined.
    """
    if not original_genre_str:
        # If original is None or empty, check if it maps to a default canonical genre.
        # This handles tracks with no genre, or just whitespace.
        return genre_canonical_map.get("", "") if "" in genre_canonical_map else None

    # Split the original string into individual genres, stripping whitespace.
    individual_genres: List[str] = [
        g.strip() for g in original_genre_str.split(";") if g.strip()
    ]

    if not individual_genres:
        # If splitting results in no genres (e.g., just whitespace or ";;"), canonicalize to None.
        return None

    # Map each individual genre to its canonical form
    canonical_genres_for_entry: List[str] = []
    for ind_genre in individual_genres:
        # Look up the canonical form. If not found, map to itself (casefolded).
        canonical_form = genre_canonical_map.get(
            ind_genre.casefold(), ind_genre.casefold()
        )
        canonical_genres_for_entry.append(canonical_form)

    if not canonical_genres_for_entry:
        return None
    elif len(set(canonical_genres_for_entry)) == 1:
        # If all individual genres canonicalized to the same single genre, choose that one.
        return canonical_genres_for_entry[0]

    # Count occurrences of each canonical genre
    canonical_genre_counts = Counter(canonical_genres_for_entry)

    # Find the maximum count
    max_count = max(canonical_genre_counts.values())

    # Find all canonical genres that have the maximum count
    most_frequent_canonical_genres = [
        g for g, count in canonical_genre_counts.items() if count == max_count
    ]

    if len(most_frequent_canonical_genres) == 1:
        # If there's a single most frequent, choose it.
        return most_frequent_canonical_genres[0]

    # If there's a tie, choose the one that appeared first in the original individual_genres list.
    chosen_canonical_genre: Optional[str] = None
    for ind_genre in individual_genres:  # Preserve original order
        # Find the canonical form of this individual genre
        canonical_form = genre_canonical_map.get(
            ind_genre.casefold(), ind_genre.casefold()
        )
        if canonical_form in most_frequent_canonical_genres:
            chosen_canonical_genre = canonical_form
            break  # Found the tie-breaker
    return chosen_canonical_genre  # Returns None if no tie-breaker found (shouldn't happen with valid data)


def perform_single_genre_canonicalization(
    main_index: IndexFile, genre_canonical_map: Dict[str, str]
):
    """
    Modifies the database in-place to canonicalize multi-valued genre strings.
    For each track, it determines a single canonical genre and updates the entry.
    Original entries are modified directly; no new IndexFileEntries are created.
    """

    genre_tag_index: int = TagTypeEnum.genre.value

    genre_tag_file: Optional[TagFile] = main_index.loaded_tag_files.get(genre_tag_index)
    if not genre_tag_file:
        raise ValueError(
            "Genre TagFile (database_2.tcd) not found in the loaded database. "
            "Ensure the database is loaded correctly and contains a genre tag file."
        )

    for entry_to_modify in main_index.entries:
        # Skip entries that are marked as DELETED.
        if entry_to_modify.flag & FLAG_DELETED:
            continue

        original_genre_str: Optional[str] = entry_to_modify.genre

        # Determine the chosen canonical genre using the helper function.
        chosen_canonical_genre: Optional[str] = _select_canonical_genre_for_entry(
            original_genre_str, genre_canonical_map
        )
        chosen_canonical_genre = (
            string.capwords(chosen_canonical_genre) if chosen_canonical_genre else None
        )

        if not chosen_canonical_genre:
            # No genre was chosen (either original was empty or no valid canonical genre found).
            continue

        # Check if a modification is needed.
        # This happens if a canonical genre was chosen AND it differs from the original (casefolded).
        # Or if original was None/empty and a canonical was chosen.
        original_genre_casefolded = (
            original_genre_str.casefold() if original_genre_str else ""
        )
        chosen_canonical_genre_casefolded = (
            chosen_canonical_genre.casefold() if chosen_canonical_genre else ""
        )

        if chosen_canonical_genre_casefolded != original_genre_casefolded:

            # Ensure the TagFileEntry for this chosen canonical genre exists in the genre TagFile.
            # TagFile.add_entry handles creating new entries or returning existing ones.
            target_genre_tag_entry: TagFileEntry = genre_tag_file.add_entry(
                TagFileEntry(tag_data=chosen_canonical_genre)
            )

            # Update the IndexFileEntry's genre pointer.
            entry_to_modify.tag_seek[genre_tag_index] = target_genre_tag_entry

    cleaned_genre_entries: List[TagFileEntry] = []
    for genre_entry in genre_tag_file.entries:
        if ";" not in genre_entry.tag_data:
            cleaned_genre_entries.append(genre_entry)

    genre_tag_file.entries = cleaned_genre_entries

    # Rebuild entries_by_tag_data to reflect the cleaned list of entries.
    genre_tag_file.entries_by_tag_data = {}
    for entry in genre_tag_file.entries:
        genre_tag_file.entries_by_tag_data[entry.tag_data.casefold()] = entry


def parse_args() -> argparse.Namespace:
    """Parses command-line arguments for the script."""
    parser = argparse.ArgumentParser(
        description="Load and inspect/modify a Rockbox database."
    )
    # Positional arguments
    parser.add_argument(
        "db_path",
        type=str,
        help="Path to the directory containing Rockbox database files.",
    )
    parser.add_argument(
        "output_db_path",
        type=str,
        help="Path to save the modified database.",
    )
    parser.add_argument(
        "genre_file",
        type=str,
        help="Path to the genre file containing genre mappings for canonicalization.",
    )

    # Optional flags
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Perform modifications in-memory, but do not write changes to disk (only prints console output).",
    )
    parser.add_argument(
        "--genre-count",
        type=int,
        default=5,
        help="Minimum number of descendants for a genre to be considered for roll-up. "
        "If a genre has fewer descendants than this, it will roll up to its parent.",
    )

    return parser.parse_args()


def main():
    """Main function to parse arguments and execute database operations."""
    args = parse_args()

    # Load the database
    print("Loading Rockbox database from:", args.db_path)
    main_index = load_rockbox_database(args.db_path)

    if main_index is None:
        print("Failed to load the Rockbox database. Exiting.")
        return
    print("Rockbox database loaded successfully.")

    # Get and build the genre canonicalization map
    print("Building genre canonicalization map from:", args.genre_file)
    roll_up_threshold = args.genre_count
    genre_canonical_map = build_genre_canonical_map(
        args.genre_file, roll_up_threshold=roll_up_threshold
    )

    if not genre_canonical_map:
        print("No genre mappings found in the provided genre file. Exiting.")
        return
    print("Genre canonicalization map built successfully.")

    # Perform the genre canonicalization modification
    print("Performing genre canonicalization on the database entries...")
    perform_single_genre_canonicalization(main_index, genre_canonical_map)
    print("Genre canonicalization complete.")

    if args.dry_run:
        print("Dry run complete. No changes written to disk.")
        return

    # Save the modified database if not a dry run
    try:
        print("Saving modified Rockbox database to:", args.output_db_path)
        write_rockbox_database(main_index, args.output_db_path)
    except Exception as e:
        print(f"Failed to save modified database: {e}")
        sys.exit(1)

    print("Modified database saved successfully.")
    print(
        f"Total entries modified: {len(main_index.entries)}. "
        f"Genre entries: {len(main_index.loaded_tag_files[TagTypeEnum.genre.value].entries)}."
    )
    print("Genre canonicalization complete.")


if __name__ == "__main__":
    main()
