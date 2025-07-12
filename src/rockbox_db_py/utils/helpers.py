# helpers.py
#
# General utility functions, mostly to help power users of the library.

from multiprocessing import Pool
import os
import shutil
from typing import Optional, List, Dict, Union

from rockbox_db_py.classes.db_file_type import RockboxDBFileType
from rockbox_db_py.classes.index_file import IndexFile
from rockbox_db_py.classes.index_file_entry import IndexFileEntry
from rockbox_db_py.classes.music_file import MusicFile, SUPPORTED_MUSIC_EXTENSIONS
from rockbox_db_py.classes.tag_file import TagFile
from rockbox_db_py.classes.tag_file_entry import TagFileEntry
from rockbox_db_py.utils.defs import TagTypeEnum, FILE_TAG_INDICES, TAG_COUNT

from tqdm import tqdm


def load_rockbox_database(db_directory: str) -> Optional[IndexFile]:
    """
    Loads the Rockbox database from the specified directory.
    This includes the main index file and all associated tag data files.

    Args:
        db_directory: Path to the directory containing Rockbox database files.

    Returns:
        The loaded IndexFile object, or None if loading fails.
    """
    index_filepath: str = os.path.join(db_directory, RockboxDBFileType.INDEX.filename)
    try:
        # IndexFile.from_file handles loading all associated TagFiles internally.
        main_index: IndexFile = IndexFile.from_file(index_filepath)
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Index file not found in directory '{db_directory}': {e}"
        ) from e
    except Exception as e:
        raise RuntimeError(
            f"Failed to load IndexFile from '{index_filepath}': {e}"
        ) from e

    return main_index


def finalize_index_for_write(main_index: IndexFile):
    """
    Ensures all file-based tag_seek values in IndexFileEntries point to valid
    numerical offsets (from the newly written TagFiles) before writing the IndexFile.

    Args:
        main_index: The IndexFile object ready for finalization.
    """

    # Iterate through all entries in the database.
    # Their tag_seek values for file-based tags are currently either original offsets
    # or TagFileEntry objects (for modified genres).
    for index_entry in main_index.entries:
        # Process this entry regardless of DELETED flag, as it will be written.

        # Iterate through ALL file-based tags to update their offsets.
        for tag_idx in FILE_TAG_INDICES:
            current_tag_seek_value: Union[int, TagFileEntry] = index_entry.tag_seek[
                tag_idx
            ]

            # Case 1: The tag_seek is currently a TagFileEntry object (this tag was modified)
            # Case 2: The tag_seek is already an integer offset (e.g., loaded from file, or not modified)
            # Case 3: The tag_seek is None or an unexpected type (set to sentinel value)
            if isinstance(current_tag_seek_value, TagFileEntry):
                target_tag_entry_in_file: TagFileEntry = current_tag_seek_value

                # Ensure the TagFileEntry has a valid offset_in_file.
                # If it was modified, it should have been written to a file.
                # If it has no offset, we set it to 0xFFFFFFFF as a sentinel
                if target_tag_entry_in_file.offset_in_file is not None:
                    index_entry.tag_seek[tag_idx] = (
                        target_tag_entry_in_file.offset_in_file
                    )
                else:
                    index_entry.tag_seek[tag_idx] = 0xFFFFFFFF
            elif isinstance(current_tag_seek_value, int):
                # Check for '0' offset, which can be ambiguous but often means 'no data' for strings.
                if current_tag_seek_value == 0:
                    index_entry.tag_seek[tag_idx] = 0xFFFFFFFF
            else:
                index_entry.tag_seek[tag_idx] = 0xFFFFFFFF


def write_rockbox_database(
    main_index: IndexFile,
    output_db_dir: str,
    auto_finalize: bool = True,
    sort_map: Optional[Dict[TagTypeEnum, Dict[str, str]]] = None,
) -> bool:
    """
    Saves the modified Rockbox database (IndexFile and its associated TagFiles)
    to the specified output directory.

    Args:
        main_index: The modified IndexFile object ready for saving.
        output_db_dir: The directory where the database files will be written.
        auto_finalize: If True, automatically calls finalize_index_for_write
                       before writing the IndexFile.
        sort_map: Optional mapping for sorting TagFile entries by tag data.
                  This can be useful to ensure consistent ordering, especially
                  in cases where duplicates are allowed. You can pass a dictionary
                  containing a full file path as the value, allowing
                  for deterministic sorting of entries in TagFiles.
    """

    # Ensure output directory exists and is ready for writing.
    if not os.path.exists(output_db_dir):
        try:
            os.makedirs(output_db_dir)
        except OSError:
            raise
    elif os.path.exists(output_db_dir) and os.listdir(output_db_dir):
        try:
            shutil.rmtree(output_db_dir)
            os.makedirs(output_db_dir)
        except OSError:
            raise

    try:
        # Write all associated tag files FIRST.
        # This is critical as it assigns correct `offset_in_file` values
        # to the TagFileEntry objects, including any newly added ones.
        loaded_tag_files: Dict[int, TagFile] = main_index.loaded_tag_files
        for tag_index, tag_file_obj in loaded_tag_files.items():
            db_file_type: RockboxDBFileType = RockboxDBFileType.from_tag_index(
                tag_index
            )
            output_tag_filepath: str = os.path.join(
                output_db_dir, db_file_type.filename
            )

            # If a sort_map is provided for this TagFile, get it.
            if sort_map and tag_file_obj in sort_map:
                tag_file_sort_map = sort_map[tag_file_obj]
            else:
                tag_file_sort_map = None

            # This updates entry.offset_in_file for all entries
            tag_file_obj.to_file(output_tag_filepath, sort_map=tag_file_sort_map)

        # After TagFiles are written and their offsets are updated,
        # finalize IndexFile entries to point to the *new* numerical offsets.
        if auto_finalize:
            finalize_index_for_write(main_index)

        # Write the main index file.
        output_index_filepath: str = os.path.join(
            output_db_dir, RockboxDBFileType.INDEX.filename
        )
        main_index.to_file(output_index_filepath)

        return True
    except Exception as e:
        print(f"Error saving modified database: {e}")
        raise


def _process_file(path: str) -> Optional[MusicFile]:
    """
    Helper function to process a single audio file path.
    """
    return MusicFile.from_filepath(path)


def scan_music_directory(
    directory_path: str, num_processes: Optional[int] = None, show_progress: bool = True
) -> List[MusicFile]:
    """
    Recursively scans a directory for music files and returns a list of MusicFile objects.
    Uses multiprocessing to parallelize file parsing.

    Args:
        directory_path: The root directory to scan.
        num_processes: Number of parallel processes to use. If None, uses CPU count.
        show_progress: If True, shows progress bar for file processing.

    Returns:
        A list of MusicFile objects found and successfully parsed.
    """

    # Phase 1: Collect all potential audio file paths (filtered by extension)
    all_potential_audio_paths: List[str] = []

    for root, _, files in os.walk(directory_path):
        for file in files:
            file_path: str = os.path.join(root, file)
            file_extension: str = os.path.splitext(file_path)[1].lower()

            if file_extension in SUPPORTED_MUSIC_EXTENSIONS:
                all_potential_audio_paths.append(file_path)

    # Phase 2: Parallel parse audio files
    if num_processes is None or num_processes <= 0:
        num_processes = os.cpu_count()

    music_files: List[MusicFile] = []

    with Pool(processes=num_processes) as pool:
        # Use imap_unordered for better memory management and progress reporting for large lists
        for result in tqdm(
            pool.imap_unordered(_process_file, all_potential_audio_paths),
            total=len(all_potential_audio_paths),
            disable=not show_progress,
        ):
            if result:
                music_files.append(result)

    if not music_files:
        print("No valid music files found or parsed successfully.")

    return music_files


def build_rockbox_database_from_music_files(
    music_files: List[MusicFile],
) -> IndexFile:
    """
    Builds a complete Rockbox database (IndexFile and associated TagFiles)
    from a list of MusicFile objects.

    Args:
        music_files: A list of MusicFile objects, representing the music library.

    Returns:
        A new IndexFile object fully populated with all necessary data.
    """

    main_index: IndexFile = IndexFile()

    # Initialize all TagFile objects (one for each file-based tag type).
    for db_type in RockboxDBFileType:
        if db_type == RockboxDBFileType.INDEX or db_type.tag_index is None:
            continue
        tag_file: TagFile = TagFile(db_type)
        main_index._loaded_tag_files[db_type.tag_index] = tag_file

    # Process each MusicFile to create IndexFileEntry and populate TagFiles.
    for song_idx, music_file in tqdm(
        enumerate(music_files), desc="Processing music files into DB"
    ):
        new_index_entry: IndexFileEntry = IndexFileEntry(tag_seek=[0] * TAG_COUNT)

        # Populate embedded numeric tags directly from MusicFile.
        new_index_entry.tag_seek[TagTypeEnum.year.value] = (
            music_file.year if music_file.year is not None else 0
        )
        new_index_entry.tag_seek[TagTypeEnum.discnumber.value] = (
            music_file.discnumber if music_file.discnumber is not None else 0
        )
        new_index_entry.tag_seek[TagTypeEnum.tracknumber.value] = (
            music_file.tracknumber if music_file.tracknumber is not None else 0
        )
        new_index_entry.tag_seek[TagTypeEnum.bitrate.value] = (
            music_file.bitrate if music_file.bitrate is not None else 0
        )
        new_index_entry.tag_seek[TagTypeEnum.length.value] = (
            music_file.length if music_file.length is not None else 0
        )
        new_index_entry.tag_seek[TagTypeEnum.mtime.value] = (
            music_file.modtime_fat32 if music_file.modtime_fat32 is not None else 0
        )
        # Other numeric fields (playcount, rating, playtime, lastplayed, commitid, lastelapsed, lastoffset)
        # will default to 0, which is acceptable for a new database.

        # Generate a unique ID for this entry.
        unique_id: str = music_file.generate_unique_id()

        # Populate file-based string tags.
        for tag_idx in FILE_TAG_INDICES:
            tag_name_str: str = TagTypeEnum(tag_idx).name

            processed_tag_value: Optional[str] = None

            tag_value_from_music_file: Optional[str] = getattr(music_file, tag_name_str)
            if tag_value_from_music_file is not None:
                processed_tag_value = tag_value_from_music_file
            else:
                processed_tag_value = None

            # For the actual song-specific tag data, we need to ensure
            # we pass over an IDX. For others....we want to pass over the known
            # empty value.
            if tag_idx in [TagTypeEnum.title.value, TagTypeEnum.filename.value]:
                computed_idx = song_idx
            else:
                computed_idx = 0xFFFFFFFF

            # Add processed tag value to the corresponding TagFile.
            if processed_tag_value is not None:
                tag_file_for_this_tag: TagFile = main_index._loaded_tag_files[tag_idx]
                target_tag_entry: TagFileEntry = tag_file_for_this_tag.add_entry(
                    TagFileEntry(
                        tag_data=processed_tag_value,
                        db_file_type=RockboxDBFileType.from_tag_index(tag_idx),
                        unique_id=unique_id,
                        idx_id=computed_idx,
                    )
                )
                new_index_entry.tag_seek[tag_idx] = target_tag_entry
            else:
                new_index_entry.tag_seek[tag_idx] = 0xFFFFFFFF

        # Add the constructed IndexFileEntry to the main_index.
        main_index.add_entry(new_index_entry)

    return main_index
