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
from collections import Counter, deque
import os
import shutil
import string
import sys
from typing import Optional, List, Dict

import yaml

from rockbox_db_py.classes.db_file_type import RockboxDBFileType
from rockbox_db_py.classes.index_file import IndexFile
from rockbox_db_py.utils.defs import TagTypeEnum, FILE_TAG_INDICES, FLAG_DELETED
from rockbox_db_py.classes.tag_file import TagFile
from rockbox_db_py.classes.tag_file_entry import TagFileEntry
from rockbox_db_py.utils.helpers import load_rockbox_database, write_rockbox_database


def build_genre_canonical_map(
    genre_map_filepath: str, roll_up_threshold: int = 10
) -> Dict[str, str]:
    """
    Parses a YAML file containing genre hierarchies and builds a canonical map.
    This version canonicalizes based on a 'roll_up_threshold' for descendant count.

    Args:
        genre_map_filepath: Path to the YAML file defining genre hierarchies.
        roll_up_threshold: If a genre (at any depth) has fewer descendants than this threshold,
                           it (and its direct children) will roll up to its immediate parent's canonical form.
                           If a genre meets or exceeds the threshold, its direct children will roll up to it.
                           A threshold of 0 means no size-based roll-up (only top-level parents are canonical).

    Returns:
        A dictionary mapping lowercased sub-genre names to their lowercased
        canonical parent names.
    """
    canonical_map: Dict[str, str] = {}

    # Store all nodes encountered, with their parent, depth, and children (initially)
    # {genre_name: {'parent': parent_name, 'depth': d, 'children_names': [c1, c2], 'descendants': 0}}
    all_genre_nodes: Dict[str, Dict] = {}

    # List to store top-level genres for initial traversal
    top_level_genre_names: List[str] = []

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

    # --- Pass 1: Build a flattened graph (all_genre_nodes) with parents and depths ---
    # Use a queue for BFS traversal (current_yaml_node, parent_name, depth)
    q = deque()

    for top_level_entry in genre_data:
        if isinstance(top_level_entry, dict):
            # Top-level is a dict, e.g., "- rock: [...]"
            for top_genre_name, children_data in top_level_entry.items():
                top_genre_name_lower = top_genre_name.strip().casefold()
                top_level_genre_names.append(
                    top_genre_name_lower
                )  # Keep track of top-level names
                all_genre_nodes[top_genre_name_lower] = {
                    "parent": None,
                    "depth": 0,
                    "children_names": [],
                }
                # Add children to queue for processing: (children_data_for_this_genre, this_genre_name, its_depth)
                q.append((children_data, top_genre_name_lower, 0))
        else:  # Simple string top-level genre, e.g., "- Pop"
            top_genre_name_lower = str(top_level_entry).strip().casefold()
            top_level_genre_names.append(top_genre_name_lower)
            all_genre_nodes[top_genre_name_lower] = {
                "parent": None,
                "depth": 0,
                "children_names": [],
            }

    # Process queue to populate all_genre_nodes (the flattened graph)
    while q:
        current_children_data, current_parent_name, current_depth = q.popleft()

        if isinstance(
            current_children_data, list
        ):  # If there are children listed under current_parent_name
            for item in current_children_data:
                if isinstance(item, dict):
                    for child_genre_name, child_children_data in item.items():
                        child_genre_name_lower = child_genre_name.strip().casefold()
                        all_genre_nodes[child_genre_name_lower] = {
                            "parent": current_parent_name,
                            "depth": current_depth + 1,
                            "children_names": [],  # This list will be populated below
                        }
                        # Link child to parent's children_names
                        all_genre_nodes[current_parent_name]["children_names"].append(
                            child_genre_name_lower
                        )
                        # Add child's children to queue
                        q.append(
                            (
                                child_children_data,
                                child_genre_name_lower,
                                current_depth + 1,
                            )
                        )
                else:  # Simple string child, e.g., "- post-britpop"
                    child_genre_name_lower = str(item).strip().casefold()
                    all_genre_nodes[child_genre_name_lower] = {
                        "parent": current_parent_name,
                        "depth": current_depth + 1,
                        "children_names": [],  # Leaves have no children
                    }
                    all_genre_nodes[current_parent_name]["children_names"].append(
                        child_genre_name_lower
                    )

    # --- Pass 2: Calculate descendant counts (bottom-up traversal) ---
    # Initialize descendants to 0 for all nodes (will be calculated)
    for name in all_genre_nodes:
        all_genre_nodes[name]["descendants"] = 0

    # Stack for post-order (bottom-up) traversal: (genre_name, visited_children_count)
    # Use a set to track fully processed nodes whose descendant count is finalized
    processed_descendants_finalized = set()

    # Start the stack with all top-level genres for a full traversal
    traversal_stack = [(name, 0) for name in top_level_genre_names]

    # We need a list of all nodes to ensure we visit them in a way that allows descendant calculation
    # A reverse topological sort or iterating until convergence is safer

    # Better: Iteratively calculate descendants until all are processed
    # Leaves are the easiest to start with (descendants = 1)
    for name, data in all_genre_nodes.items():
        if not data["children_names"]:  # It's a leaf node
            all_genre_nodes[name]["descendants"] = 1
            processed_descendants_finalized.add(name)

    while len(processed_descendants_finalized) < len(all_genre_nodes):
        nodes_updated_in_pass = False
        for name, data in all_genre_nodes.items():
            if name in processed_descendants_finalized:
                continue  # Already processed

            # If all children have their descendants calculated
            if all(
                child_name in processed_descendants_finalized
                for child_name in data["children_names"]
            ):
                # Sum children's descendants and add 1 for self
                data["descendants"] = 1 + sum(
                    all_genre_nodes[child_name]["descendants"]
                    for child_name in data["children_names"]
                )
                processed_descendants_finalized.add(name)
                nodes_updated_in_pass = True

        if not nodes_updated_in_pass and len(processed_descendants_finalized) < len(
            all_genre_nodes
        ):
            # This indicates a cycle in the graph or unreachables if not all processed,
            # but YAML hierarchy should prevent cycles. So, it should converge.
            # If it doesn't, there's an issue with the YAML data structure or logic.
            print(
                "Warning: Could not calculate descendants for all nodes (possible structural issue in YAML)."
            )
            break

    # --- Pass 3: Determine canonical forms based on depth and descendant count ---
    for genre_name_lower, data in all_genre_nodes.items():
        depth = data["depth"]
        descendants = data["descendants"]
        parent_name = data["parent"]

        # Default canonical parent is itself (most specific)
        canonical_parent = genre_name_lower

        # Rule application (based on user's examples):
        # We roll up from deepest to highest, applying thresholds.

        # If it's a sub-genre (depth > 0)
        if depth > 0:
            # Check its immediate parent's (parent_name) descendants count
            parent_data = all_genre_nodes.get(parent_name)
            if parent_data:
                parent_descendants = parent_data["descendants"]

                # If parent is 'heavy metal' and its descendants are >= threshold,
                # then children canonicalize to 'heavy metal'.
                # E.g., 'death metal' -> 'heavy metal' (if 'heavy metal' is large enough)
                # If parent is 'alternative rock' and its descendants are >= threshold,
                # then children canonicalize to 'alternative rock'.
                # E.g., 'britpop' -> 'alternative rock' (if 'alternative rock' is large enough)

                if parent_descendants >= roll_up_threshold:
                    # Current genre's canonical form is its immediate parent
                    canonical_parent = parent_name
                else:
                    # If parent is too small, canonicalize to parent's parent (grandparent),
                    # or ultimately to the top-level parent if it keeps rolling up.
                    # This means we need to find the highest ancestor that IS large enough,
                    # or the top-level parent if none are.

                    # Traverse up to find the canonical parent for this small branch
                    current_ancestor_name = parent_name
                    while current_ancestor_name:
                        ancestor_data = all_genre_nodes.get(current_ancestor_name)
                        if (
                            ancestor_data
                            and ancestor_data["descendants"] >= roll_up_threshold
                        ):
                            canonical_parent = current_ancestor_name
                            break
                        current_ancestor_name = (
                            ancestor_data["parent"] if ancestor_data else None
                        )
                    if (
                        not current_ancestor_name
                    ):  # Reached top without finding large enough parent
                        # Canonicalize to the top-level ancestor
                        current_ancestor_name = genre_name_lower
                        while all_genre_nodes.get(current_ancestor_name, {}).get(
                            "parent"
                        ):
                            current_ancestor_name = all_genre_nodes[
                                current_ancestor_name
                            ]["parent"]
                        canonical_parent = current_ancestor_name

        canonical_map[genre_name_lower] = canonical_parent

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

    modified_entries_count: int = 0

    genre_tag_index: int = TagTypeEnum.genre.value
    genre_file_type: RockboxDBFileType = RockboxDBFileType.GENRE

    genre_tag_file: Optional[TagFile] = main_index.loaded_tag_files.get(genre_tag_index)
    if not genre_tag_file:
        raise ValueError(
            f"Genre TagFile (database_2.tcd) not found in the loaded database. "
            f"Ensure the database is loaded correctly and contains a genre tag file."
        )

    for i, entry_to_modify in enumerate(main_index.entries):
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
            modified_entries_count += 1

            # Ensure the TagFileEntry for this chosen canonical genre exists in the genre TagFile.
            # TagFile.add_entry handles creating new entries or returning existing ones.
            target_genre_tag_entry: TagFileEntry = genre_tag_file.add_entry(
                TagFileEntry(tag_data=chosen_canonical_genre, is_filename_db=False)
            )

            # Update the IndexFileEntry's genre pointer.
            entry_to_modify.tag_seek[genre_tag_index] = target_genre_tag_entry

    # Cleanse the genre TagFile (database_2.tcd) of multi-value strings.
    initial_genre_entries_count: int = len(genre_tag_file.entries)

    cleaned_genre_entries: List[TagFileEntry] = []
    removed_genre_strings_count: int = 0
    for genre_entry in genre_tag_file.entries:
        if ";" in genre_entry.tag_data:
            removed_genre_strings_count += 1
        else:
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
