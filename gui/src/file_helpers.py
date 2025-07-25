import os
import shutil

from src.config import FILES_TO_TRACK
from src.db_helpers import (
    insert_record,
    delete_record,
    SYNC_TABLE_NAME,
    get_sync_table,
    batch_insert_records,
    update_record,
)
from src.file import File
from src.utils import iter_with_progress, normalise_path

from typing import Dict, Any, List


def process_file_collection(
    files, operation_name, process_func, dry_run=False, item_details_func=None
):
    """
    Process a collection of files with progress reporting.

    Args:
        files: List of files to process
        operation_name: Name of the operation (for logging)
        process_func: Function to call for each file
        dry_run: Whether to skip actual processing
        item_details_func: Optional function to get details for progress display

    Returns:
        Number of files processed
    """
    if not files:
        return 0

    count = 0
    for file in iter_with_progress(
        files, prefix=f"{operation_name} files", item_details=item_details_func
    ):
        if not dry_run:
            process_func(file)
        count += 1
    return count


def find_file_differences(input_files_set, output_files_set):
    """
    Find files to add, update, and delete by comparing input and output sets.

    Args:
        input_files_set: Dictionary of input files keyed by normalized path
        output_files_set: Dictionary of output files keyed by normalized path

    Returns:
        Tuple of (files_to_add, files_to_update, files_to_delete)
    """
    files_to_add = []
    files_to_update = []
    files_to_delete = []

    # Find files to add or update
    for file_path, input_file in input_files_set.items():
        if file_path not in output_files_set:
            files_to_add.append(input_file)
        else:
            output_file = output_files_set[file_path]
            size_match = input_file.size == output_file.size
            newer_mod_time = (
                input_file.mod_time > output_file.mod_time
                if output_file.mod_time is not None
                else False
            )
            if not size_match or newer_mod_time:
                files_to_update.append(input_file)

    # Find files to delete
    for file_path, output_file in output_files_set.items():
        if file_path not in input_files_set:
            files_to_delete.append(output_file)

    return files_to_add, files_to_update, files_to_delete


def build_file_set(folder_path, extensions, log_func=print):
    """Build a dictionary of files keyed by normalized path"""
    log_func(f"Building file list from folder: {folder_path}")
    files = []
    for root, _, filenames in os.walk(folder_path):
        for filename in filenames:
            if filename.endswith(tuple(extensions)):
                file_path = os.path.join(root, filename)
                try:
                    files.append(File(file_path))
                except FileNotFoundError as e:
                    log_func(f"Skipping file {file_path}: {e}")

    log_func(f"Found {len(files)} files in folder.")
    return {normalise_path(file, folder_path): file for file in files}


def build_file_set_from_sync_table(sync_table, output_folder, log_func=print):
    """Build a dictionary of files from sync table records"""
    log_func(f"Building file list from sync table for: {output_folder}")
    files = []
    for record in sync_table:
        path, size, mod_time = record["path"], record["size"], record["mod_time"]
        full_path = os.path.join(output_folder, path)
        files.append(File(full_path, size=size, mod_time=mod_time))

    log_func(f"Found {len(files)} files in sync table.")
    return {normalise_path(file, output_folder): file for file in files}


def populate_db_with_current_state(
    output_folder: str, user_config, progress_callback=None
):
    """
    Sync the state of the output folder to the database.
    I.e. If there is no DB, create it and populate it with the current state of the output folder.
         If there is a DB, load it and update it with the current state of the output folder.

    :param output_folder: Path to the output folder.
    :param user_config: User configuration object containing database path.
    """
    output_files = build_file_set(output_folder, user_config.extensions_to_track)

    # Load the sync table from the database
    db_folder = user_config.sync_db_path
    db_path = os.path.join(output_folder, db_folder)
    sync_table: List[Dict[str, Any]] = get_sync_table(db_path)

    if len(sync_table) == 0:
        print("No entries found in the sync table. Populating...")
        records = [
            {"path": file.path, "size": file.size, "mod_time": file.mod_time}
            for file in output_files.values()
        ]
        batch_insert_records(db_path, SYNC_TABLE_NAME, records, 250)
        print("Database created and populated with current state of the output folder.")
        return

    print(f"Found {len(sync_table)} entries in the sync table. Updating...")

    # Convert the sync table to a set of File objects
    db_files = build_file_set_from_sync_table(sync_table, output_folder, log_func=print)

    # Find the differences between the output folder and the sync table
    entries_to_add, entries_to_update, entries_to_remove = find_file_differences(
        output_files, db_files
    )

    # Total items to process
    total_items_to_process = (
        len(entries_to_add) + len(entries_to_update) + len(entries_to_remove)
    )

    if total_items_to_process == 0:
        print("No changes detected. The sync table is already up to date.")
        return

    # Process the entries to add, update, and remove
    records_to_add = [
        {"path": file.path, "size": file.size, "mod_time": file.mod_time}
        for file in entries_to_add
    ]
    batch_insert_records(
        db_path,
        SYNC_TABLE_NAME,
        records_to_add,
        250,
    )
    if progress_callback:
        progress_callback(len(entries_to_add) / total_items_to_process * 100)

    # Update existing files in the sync table
    if len(entries_to_update) == 0:
        print("No new entries to update.")
    else:
        i = 0
        for file in iter_with_progress(entries_to_update, prefix="Updating files"):
            update_record(
                db_path,
                SYNC_TABLE_NAME,
                {
                    "path": file.path,
                    "size": file.size,
                    "mod_time": file.mod_time,
                },
                "path",
                file.path,
            )
            if progress_callback:
                progress_callback(
                    (len(entries_to_add) + i + 1) / total_items_to_process * 100
                )
            i += 1

    # Remove files that are no longer in the output folder
    i = 0
    for file in iter_with_progress(entries_to_remove, prefix="Removing files"):
        delete_record(
            db_path,
            SYNC_TABLE_NAME,
            "path",
            file.path,
        )
        if progress_callback:
            progress_callback(
                (len(entries_to_add) + len(entries_to_update) + i + 1)
                / total_items_to_process
                * 100
            )
        i += 1

    print("Sync table updated with the current state of the output folder.")


def log_file_differences(
    files_to_add, files_to_update, files_to_delete, print_all=False, log_func=print
):
    """Log information about the differences between file sets"""
    log_func(f"Files to add: {len(files_to_add)}")
    if print_all and files_to_add:
        log_func("Files to add:", [file.path for file in files_to_add])

    log_func(f"Files to update: {len(files_to_update)}")
    if print_all and files_to_update:
        log_func("Files to update:", [file.path for file in files_to_update])

    log_func(f"Files to delete: {len(files_to_delete)}")
    if print_all and files_to_delete:
        log_func("Files to delete:", [file.path for file in files_to_delete])


def copy_file_and_add_to_db(src: str, dst: str, db_path: str) -> None:
    """
    Copy a file from source to destination and add its information to the database.

    Args:
        src: Source file path
        dst: Destination file path
        db_path: Path to the SQLite database
        table_name: Name of the table to insert the file info
        file_info: Dictionary containing file information (e.g., size, mod_time)
    """

    # Ensure the destination directory exists
    dst_dir = os.path.dirname(dst)
    os.makedirs(dst_dir, exist_ok=True)

    # Copy the file
    shutil.copy2(src, dst)

    # Add file information to the database
    insert_record(
        db_path,
        SYNC_TABLE_NAME,
        {
            "path": dst,
            "source_path": src,
            "size": os.path.getsize(src),
            "mod_time": os.path.getmtime(src),
        },
    )


def remove_file_and_from_db(path: str, db_path: str) -> None:
    """
    Remove a file from the filesystem and delete its record from the database.

    Args:
        path: Path to the file to be removed
        db_path: Path to the SQLite database
    """
    # Remove the file
    if os.path.exists(path):
        os.remove(path)

    # Delete the record from the database
    delete_record(db_path, SYNC_TABLE_NAME, "path", path)


def update_file_and_db(src: str, dest: str, db_path: str) -> None:
    """
    Update a file's path in the filesystem and update its record in the database.

    Args:
        src: Source file path to copy from
        dest: Existing file path to update
        db_path: Path to the SQLite database
    """
    if not os.path.exists(dest):
        raise FileNotFoundError(f"File not found: {dest}")

    # Remove the old file
    remove_file_and_from_db(dest, db_path)

    # Copy the file over to the new path
    copy_file_and_add_to_db(src, dest, db_path)
