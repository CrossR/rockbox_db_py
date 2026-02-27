import concurrent.futures
import os
import threading
import time
from typing import Optional
from tkinter import messagebox

from src.logic import scan_for_files, populate_sync_db, copy_files, populate_rockbox_db


class WorkerManager:
    def __init__(self, parent_app) -> None:
        self.parent_app = parent_app
        self.worker_running = False

    def _worker_apply_changes(self) -> None:
        """This function runs in a separate thread for file copy/sync."""
        try:
            self.parent_app.queue.put(("progress", 0))
            input_folder = os.path.normpath(self.parent_app.input_path_entry.get())
            output_folder = os.path.normpath(self.parent_app.output_path_entry.get())
            dry_run = self.parent_app.dry_run_var.get()

            if not input_folder or not output_folder:
                self.parent_app.queue.put(
                    ("error", "Please select both input and output folders.")
                )
                return

            # Get all file items (not folders) from the treeviews
            files_to_copy = self.parent_app.tree_manager.get_all_files_from_tree(
                self.parent_app.add_tree
            )
            files_to_update = self.parent_app.tree_manager.get_all_files_from_tree(
                self.parent_app.update_tree
            )
            files_to_delete = self.parent_app.tree_manager.get_all_files_from_tree(
                self.parent_app.delete_tree
            )

            # Create a thread pool with a low number of workers.
            # This process isn't so I/O intensive that it needs many threads.
            # The actually heavy bits deal with their own workers anyways.
            max_workers = 2
            self.parent_app.queue.put(
                ("message", f"Using {max_workers} parallel workers for file operations")
            )

            self.parent_app.queue.put(
                (
                    "message",
                    "Starting file operations... "
                    "This may take a while depending on the number of files.",
                )
            )

            self.parent_app.queue.put(
                (
                    "message",
                    "On most older devices, we are simply IO bound, so don't be "
                    "alarmed by the low number of workers.",
                )
            )

            # Track progress across all operations
            total_files = (
                len(files_to_copy) + len(files_to_update) + len(files_to_delete)
            )
            processed_files = 0
            progress_lock = threading.Lock()

            def update_progress(
                update_type: Optional[str] = None, file_path: Optional[str] = None
            ):
                nonlocal processed_files, dry_run
                with progress_lock:
                    processed_files += 1
                    progress = (
                        (processed_files / total_files) * 100
                        if total_files > 0
                        else 100
                    )
                    self.parent_app.queue.put(("progress", progress))
                # If we aren't in dry run mode, remove the file from the tree
                if update_type and file_path and not dry_run:
                    self.parent_app.queue.put(
                        ("remove_from_tree", (update_type, file_path))
                    )

            # Function for copy operations to run in thread pool
            def copy_file_task(file_path: str, overwrite: bool = False):
                try:
                    success = copy_files(
                        os.path.join(input_folder, file_path),
                        os.path.join(output_folder, file_path),
                        overwrite=overwrite,
                        dry_run=dry_run,
                    )
                    if not success:
                        self.parent_app.queue.put(
                            (
                                "error",
                                f"Failed to {'update' if overwrite else 'copy'} {file_path}",
                            )
                        )
                    update_progress(file_path)
                except Exception as e:
                    self.parent_app.queue.put(
                        ("error", f"Error processing {file_path}: {e}")
                    )
                    update_progress()

            # Function for delete operations to run in thread pool
            def delete_file_task(file_path: str):
                try:
                    full_path = os.path.join(output_folder, file_path)
                    if dry_run:
                        print(f"Would delete {full_path} (dry run)")
                    else:
                        os.remove(full_path)
                    update_progress(file_path)
                except Exception as e:
                    self.parent_app.queue.put(
                        ("error", f"Failed to delete {file_path}: {e}")
                    )
                    update_progress()

            # Process files in parallel using ThreadPoolExecutor
            if total_files > 0:
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=max_workers
                ) as executor:
                    # Submit all copy tasks
                    copy_futures = [
                        executor.submit(copy_file_task, file_path)
                        for file_path in files_to_copy
                    ]

                    # Submit all update tasks
                    update_futures = [
                        executor.submit(copy_file_task, file_path, True)
                        for file_path in files_to_update
                    ]

                    # Submit all delete tasks
                    delete_futures = [
                        executor.submit(delete_file_task, file_path)
                        for file_path in files_to_delete
                    ]

                    # Wait for all tasks to complete
                    all_futures = copy_futures + update_futures + delete_futures
                    concurrent.futures.wait(all_futures)

                self.parent_app.queue.put(("progress", 100))
            else:
                self.parent_app.queue.put(("progress", 100))

            # If we reach here, all operations were successful
            # Only clear trees and update DB if not in dry run mode
            if not dry_run:
                self.parent_app.tree_manager.update_tab_titles()
                self.parent_app.queue.put(("clear_all_trees_gui", None))

                # Update the DB to reflect the current state
                self.parent_app.queue.put(("message", "Complete! Updating database..."))
                self._worker_verify_device_files()

            # Notify the user that the operation is complete
            if dry_run:
                self.parent_app.queue.put(
                    ("message", "Dry run completed. No changes were made.")
                )
            else:
                self.parent_app.queue.put(
                    ("message", "File operations completed successfully!")
                )
        except Exception as e:
            self.parent_app.queue.put(("error", f"An unexpected error occurred: {e}"))
        finally:
            self.parent_app.queue.put(("done", None))

    def _worker_refresh_lists(self) -> None:
        """This function runs in a separate thread to populate treeviews."""
        try:
            # There can sometimes be a giant number of files to process,
            # where putting all the items in the queue one by one could be inefficient.
            # Instead, we can batch the items and put them in the queue in chunks.
            add_batch, update_batch, delete_batch = [], [], []
            last_flush = time.time()
            BATCH_SIZE = 500
            FLUSH_INTERVAL = 1.0  # seconds

            files_to_add = 0
            files_to_update = 0
            files_to_delete = 0

            def flush_batches(force: bool = False):
                nonlocal add_batch, update_batch, delete_batch, last_flush
                nonlocal files_to_add, files_to_update, files_to_delete

                if (
                    force
                    or len(add_batch) >= BATCH_SIZE
                    or len(update_batch) >= BATCH_SIZE
                    or len(delete_batch) >= BATCH_SIZE
                    or (time.time() - last_flush) >= FLUSH_INTERVAL
                ):
                    if add_batch:
                        self.parent_app.queue.put(
                            ("add_to_tree", ("add", list(add_batch)))
                        )
                        files_to_add += len(add_batch)
                        add_batch = []
                    if update_batch:
                        self.parent_app.queue.put(
                            ("add_to_tree", ("update", list(update_batch)))
                        )
                        files_to_update += len(update_batch)
                        update_batch = []
                    if delete_batch:
                        self.parent_app.queue.put(
                            ("add_to_tree", ("delete", list(delete_batch)))
                        )
                        files_to_delete += len(delete_batch)
                        delete_batch = []
                    last_flush = time.time()

            # Pass a callback to the external scan_for_files function
            def list_and_progress_callback(msg_type: str, data: Optional[str] = None):
                """Internal callback for scan_for_files."""
                if msg_type == "clear_all_lists":
                    self.parent_app.queue.put(("clear_all_trees_gui", None))
                elif msg_type == "add":
                    add_batch.append(data)
                    flush_batches()
                elif msg_type == "update":
                    update_batch.append(data)
                    flush_batches()
                elif msg_type == "delete":
                    delete_batch.append(data)
                    flush_batches()
                elif msg_type == "progress":
                    self.parent_app.queue.put(("progress", data))

            input_folder = self.parent_app.input_path_entry.get()
            output_folder = self.parent_app.output_path_entry.get()

            if not input_folder or not output_folder:
                self.parent_app.queue.put(
                    (
                        "error",
                        "Please select both input and output folders to refresh lists.",
                    )
                )
                return

            self.parent_app.queue.put(("message", "Scanning for files..."))
            scan_for_files(
                input_folder,
                output_folder,
                self.parent_app.user_config,
                add_callback=lambda f: list_and_progress_callback("add", f),
                update_callback=lambda f: list_and_progress_callback("update", f),
                delete_callback=lambda f: list_and_progress_callback("delete", f),
                progress_callback=list_and_progress_callback,
            )
            flush_batches(force=True)

            self.parent_app.queue.put(("message", "Music files found!"))
            self.parent_app.queue.put(
                (
                    "message",
                    f"Files to add: {files_to_add}, "
                    f"Files to update: {files_to_update}, "
                    f"Files to delete: {files_to_delete}",
                )
            )
        except Exception as e:
            self.parent_app.queue.put(
                ("error", f"An error occurred during list refresh: {e}")
            )
        finally:
            self.parent_app.queue.put(("done", None))

    def _worker_verify_device_files(self) -> None:
        """
        This function runs in a separate thread to verify device files.
        By that, we mean it syncs the state of the on-device files with the
        on-device, sync database.

        This does not modify the Rockbox database at all, it only
        updates the local sync database with the current state of the device.
        """
        try:
            input_folder = self.parent_app.input_path_entry.get()
            output_folder = self.parent_app.output_path_entry.get()

            if not input_folder or not output_folder:
                self.parent_app.queue.put(
                    (
                        "error",
                        "Please select both input and output folders to populate DB.",
                    )
                )
                return

            populate_sync_db(
                output_folder,
                self.parent_app.user_config,
                progress_callback=lambda p: self.parent_app.queue.put(("progress", p)),
            )

            self.parent_app.queue.put(
                ("message", "Database populated with current state of output folder.")
            )
        except Exception as e:
            self.parent_app.queue.put(
                ("error", f"An error occurred while populating the database: {e}")
            )
        finally:
            self.parent_app.queue.put(("done", None))

    def _worker_build_rockbox_db(self) -> None:
        """This function runs in a separate thread to build the Rockbox database."""
        try:
            input_folder = self.parent_app.input_path_entry.get()
            rockbox_output_folder = self.parent_app.rockbox_db_path_entry.get()

            if not input_folder or not rockbox_output_folder:
                self.parent_app.queue.put(
                    (
                        "error",
                        "Please select both the input folder, and the Rockbox DB output folder.",
                    )
                )
                return

            # Define a progress callback to update the GUI
            def progress_callback(msg_type: str, data: Optional[str] = None):
                if msg_type == "progress":
                    self.parent_app.queue.put(("progress", data))
                elif msg_type == "message":
                    self.parent_app.queue.put(("message", data))

            self.parent_app.queue.put(
                ("message", "Processing music files for Rockbox database...")
            )
            self.parent_app.queue.put(
                (
                    "message",
                    "This has to load all the file tags, so may take a few seconds...",
                )
            )
            # Call the rockbox database building logic
            # This will deal with all the required steps to scan, build and write the database
            populate_rockbox_db(
                music_folder=input_folder,
                rockbox_output_folder=rockbox_output_folder,
                progress_callback=progress_callback,
            )

            self.parent_app.queue.put(
                (
                    "message",
                    "Rockbox database files populated with current state of music files.",
                )
            )
        except Exception as e:
            self.parent_app.queue.put(
                ("error", f"An error occurred while populating the database: {e}")
            )
        finally:
            self.parent_app.queue.put(("done", None))

    def start_get_changes(self) -> None:
        """Starts the file operations in a separate thread."""
        if self.worker_running:
            self.parent_app.log_message(
                "Another operation is already in progress.", "warning"
            )
            return

        self.worker_running = True
        self.parent_app.load_lists_button.config(state="disabled")
        self.parent_app.apply_updates_button.config(state="disabled")
        self.parent_app.progress_manager.reset_progress()
        self.parent_app.progress_manager.start_time_estimation()
        threading.Thread(target=self._worker_refresh_lists, daemon=True).start()

    def verify_device_files(self) -> None:
        """Starts the process of verifying device files in a separate thread."""
        if self.worker_running:
            self.parent_app.log_message(
                "Another operation is already in progress.", "warning"
            )
            return

        self.worker_running = True
        self.parent_app.tree_manager.clear_all_trees()
        self.parent_app.disable_all_buttons()
        self.parent_app.progress_manager.reset_progress()
        threading.Thread(target=self._worker_verify_device_files, daemon=True).start()

    def build_rockbox_db(self) -> None:
        """Starts the process of building a final Rockbox database in a separate thread."""
        if self.worker_running:
            self.parent_app.log_message(
                "Another operation is already in progress.", "warning"
            )
            return

        self.worker_running = True
        self.parent_app.tree_manager.clear_all_trees()
        self.parent_app.disable_all_buttons()
        self.parent_app.progress_manager.reset_progress()
        self.parent_app.progress_manager.start_time_estimation()
        threading.Thread(target=self._worker_build_rockbox_db, daemon=True).start()

    def start_apply_changes(self) -> None:
        """Starts the file copy/sync operations in a separate thread."""
        if self.worker_running:
            self.parent_app.log_message(
                "Another operation is already in progress.", "warning"
            )
            return

        # Count all files in each tree
        add_count = self.parent_app.tree_manager._count_files_in_tree(
            self.parent_app.add_tree
        )
        update_count = self.parent_app.tree_manager._count_files_in_tree(
            self.parent_app.update_tree
        )
        delete_count = self.parent_app.tree_manager._count_files_in_tree(
            self.parent_app.delete_tree
        )

        # Check if there are any files to process
        if add_count == 0 and update_count == 0 and delete_count == 0:
            self.parent_app.log_message(
                "There are no files to process in the lists.", "error"
            )
            return

        # Add confirmation dialog that mentions dry run status and accurate file counts
        mode = "DRY RUN" if self.parent_app.dry_run_var.get() else "LIVE"
        confirm = messagebox.askyesno(
            "Confirm Operation",
            f"Ready to proceed with {mode} mode?\n\n"
            f"This will process {add_count} additions, "
            f"{update_count} updates, and "
            f"{delete_count} deletions.",
        )

        if not confirm:
            return

        self.worker_running = True
        self.parent_app.disable_all_buttons()
        self.parent_app.progress_manager.reset_progress()
        self.parent_app.progress_manager.start_time_estimation()
        threading.Thread(target=self._worker_apply_changes, daemon=True).start()

    def on_worker_finished(self) -> None:
        """Called when a worker thread signals completion."""
        self.worker_running = False
        self.parent_app.on_worker_finished_gui()
