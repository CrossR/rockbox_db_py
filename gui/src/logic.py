# Logic for the sync_helper GUI application
import os
import shutil
import time

from rockbox_db_py.utils.defs import TagTypeEnum
from rockbox_db_py.utils.helpers import (
    scan_music_directory,
    build_rockbox_database_from_music_files,
    write_rockbox_database,
)

from src.db_helpers import get_sync_table, make_sync_table
from src.file_helpers import (
    build_file_set_from_sync_table,
    build_file_set,
    populate_db_with_current_state,
    find_file_differences,
)


def scan_for_files(
    input_dir,
    output_dir,
    add_callback=None,
    update_callback=None,
    delete_callback=None,
    progress_callback=None,
):
    """
    Scans directories and determines files to add/update/delete.
    Includes a progress callback for the scanning process itself.
    """
    print(f"Scanning input: {input_dir}, output: {output_dir}")

    # Clear current lists at the start of a new scan
    if progress_callback:
        progress_callback("clear_all_lists")

    # TODO: Replace with user loaded config
    DB_PATH = os.path.join(output_dir, ".sync", "sync_helper.db")

    # Get the sync table
    sync_table = get_sync_table(DB_PATH)

    # Get both file sets
    input_file_set = build_file_set(input_dir)
    output_file_set = build_file_set_from_sync_table(sync_table, output_dir)

    # Find the differences between the two states
    files_to_add, files_to_update, files_to_delete = find_file_differences(
        input_file_set, output_file_set
    )

    # Process the files to add, update, and delete
    total_items_to_process = (
        len(files_to_add) + len(files_to_update) + len(files_to_delete)
    )

    for i, file in enumerate(files_to_add):
        if add_callback:
            add_callback(file.path)
        if progress_callback:
            progress_callback(
                "progress", int((i + 1) / total_items_to_process)
            )  # Increment progress for scan

    for i, file in enumerate(files_to_update):
        if update_callback:
            update_callback(file.path)
        if progress_callback:
            progress_callback(
                "progress", int((len(files_to_add) + i + 1) / total_items_to_process)
            )

    for i, file in enumerate(files_to_delete):
        if delete_callback:
            delete_callback(file.path)
        if progress_callback:
            progress_callback(
                "progress",
                int(
                    (len(files_to_add) + len(files_to_update) + i + 1)
                    / total_items_to_process
                ),
            )

    # Final progress update to 100%
    if progress_callback:
        progress_callback("progress", 100)

    print("Scan complete.")
    return True


def populate_sync_db(output_dir, db_path, progress_callback=None):
    """
    Populates the database with the current state of the output directory.
    """
    print(f"Populating database at {db_path} with files from {output_dir}")

    # Ensure the sync table exists
    make_sync_table(db_path)

    # Scan the output directory and update the database
    populate_db_with_current_state(output_dir, db_path, progress_callback)

    print("Database populated with current state of output folder.")


def copy_files(input_path, output_path, overwrite=False, dry_run=False):
    """
    Copies files from input_path to output_path.
    """

    if dry_run:
        print(f"Dry run: Would copy {input_path} to {output_path} (Force: {overwrite})")
        return True

    print(f"Copying files from {input_path} to {output_path}")

    # Ensure the output directory exists
    output_dir = os.path.dirname(output_path)
    for attempt in range(3):
        try:
            os.makedirs(output_dir, exist_ok=True)
            break
        except OSError as e:
            if attempt == 2:
                print(f"Failed to create directory {output_dir} after 3 attempts: {e}")
                return False
            time.sleep(0.5)

    # Copy file from input to output
    try:
        file_exists = os.path.exists(output_path)
        if not file_exists:
            shutil.copy2(input_path, output_path)
            print(f"Copied {input_path} to {output_path}")
        elif file_exists and overwrite:
            os.remove(output_path)
            shutil.copy2(input_path, output_path)
            print(f"Overwritten {output_path} with {input_path}")
        else:
            print(f"File {output_path} already exists. Skipping copy.")
    except Exception as e:
        print(f"Error copying file: {e}")
        return False

    return True


def populate_rockbox_db(
    music_folder: str, rockbox_output_folder: str, progress_callback: callable = None
):
    """
    Populates the Rockbox database with the current state of the output folder.

    This had 3 main steps:
        1. Scan the input music folder, loading all the music file tags.
        2. Build an in-memory rockbox compatible database.
        3. Write the database to the rockbox output folder.
    """
    print(
        f"Populating Rockbox DB at {rockbox_output_folder} with files from {music_folder}"
    )

    progress_callback("message", "Processing music files...")
    music_files = scan_music_directory(
        music_folder, show_progress=False, custom_progress_callback=progress_callback
    )
    progress_callback("message", f"Found {len(music_files)} music files.")

    if not music_files:
        progress_callback("message", "No music files found to index. Exiting.")
        return

    progress_callback("message", "Building Rockbox database...")
    new_database = build_rockbox_database_from_music_files(music_files)
    progress_callback("message", "Rockbox database built in memory.")

    # Build a sort map, to ensure consistent sorting of entries
    progress_callback("message", "Building sort map for database entries...")
    sort_map = {TagTypeEnum.title: {}}
    sort_map[TagTypeEnum.title] = {
        mf.title: mf.filepath for mf in music_files if mf.title
    }

    progress_callback("message", "Writing Rockbox database to disk...")
    write_rockbox_database(new_database, rockbox_output_folder)
    progress_callback("message", "Rockbox database written to disk!")

    print("Rockbox database has been updated!")
