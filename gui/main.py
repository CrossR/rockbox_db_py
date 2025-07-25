import time
import queue

import tkinter as tk
from tkinter import filedialog

from src.treeview import TreeViewManager
from src.workers import WorkerManager
from src.progress import ProgressManager
from src.config import UserConfig, get_user_config, save_user_config


class SimpleApp:
    def __init__(self, root):
        self.root = root
        self.root.title("RockBox Sync Helper")
        self.root.geometry("600x800")

        # Create a queue for thread-safe communication
        self.queue = queue.Queue()

        # Initialize managers
        self.worker_manager = WorkerManager(self)
        self.progress_manager = ProgressManager(self)

        # Grab the user config, if it exists
        self.user_config = get_user_config()

        self.create_input_output_frames()
        self.tree_manager = self.create_tabs()
        self.create_progress_bar()
        self.create_message_log()
        self.create_buttons()

        # Start a periodic check for messages from the worker thread
        self.root.after(100, self.process_queue)

        # State variable to track if a worker is running
        self.worker_running = False

    def create_input_output_frames(self):
        # Input Frame
        input_frame = tk.Frame(self.root, bd=2, relief="groove")
        input_frame.pack(pady=10, padx=10, fill="x")

        tk.Label(input_frame, text="Input").pack(side="left", padx=5)
        self.input_path_entry = tk.Entry(input_frame, width=70)
        self.input_path_entry.pack(side="left", expand=True, fill="x", padx=5)
        self.input_path_entry.insert(0, self.user_config.input_folder)
        tk.Button(input_frame, text="Browse", command=self.select_input_folder).pack(
            side="right", padx=5
        )

        # Output Frame
        output_frame = tk.Frame(self.root, bd=2, relief="groove")
        output_frame.pack(pady=5, padx=10, fill="x")

        tk.Label(output_frame, text="Output").pack(side="left", padx=5)
        self.output_path_entry = tk.Entry(output_frame, width=70)
        self.output_path_entry.pack(side="left", expand=True, fill="x", padx=5)
        self.output_path_entry.insert(0, self.user_config.output_folder)
        tk.Button(output_frame, text="Browse", command=self.select_output_folder).pack(
            side="right", padx=5
        )

    def create_message_log(self):
        """Create a scrollable message log area"""
        log_frame = tk.Frame(self.root, bd=2, relief="groove")
        log_frame.pack(pady=10, padx=10, fill="both", expand=False)

        # Add a label at the top
        tk.Label(log_frame, text="Message Log", anchor="w").pack(
            side="top", fill="x", padx=5
        )

        # Create a frame for the text widget and scrollbar
        text_frame = tk.Frame(log_frame)
        text_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Add a scrollbar
        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")

        # Create the text widget
        self.message_log = tk.Text(
            text_frame, height=8, wrap="word", yscrollcommand=scrollbar.set
        )
        self.message_log.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.message_log.yview)

        # Configure text tags for different message types
        self.message_log.tag_configure("info", foreground="black")
        self.message_log.tag_configure("success", foreground="green")
        self.message_log.tag_configure("error", foreground="red")
        self.message_log.tag_configure("warning", foreground="orange")

        # Make the text widget read-only
        self.message_log.config(state="disabled")

    def create_tabs(self):
        # Delegate to tree manager
        tree_manager = TreeViewManager(self, self.root)

        # Keep references for backward compatibility
        self.notebook = tree_manager.notebook
        self.add_tab = tree_manager.add_tab
        self.update_tab = tree_manager.update_tab
        self.delete_tab = tree_manager.delete_tab
        self.add_tree = tree_manager.add_tree
        self.update_tree = tree_manager.update_tree
        self.delete_tree = tree_manager.delete_tree

        return tree_manager

    def create_progress_bar(self):
        # Delegate to progress manager
        self.progress_manager.create_progress_bar(self.root)

        # Keep references for backward compatibility
        self.progress_frame = self.progress_manager.progress_frame
        self.progress_bar = self.progress_manager.progress_bar
        self.time_label = self.progress_manager.time_label

    def create_buttons(self):
        button_frame = tk.Frame(self.root, pady=10)
        button_frame.pack()

        # Add dry run checkbox
        self.dry_run_var = tk.BooleanVar(value=False)
        self.dry_run_checkbox = tk.Checkbutton(
            button_frame,
            text="Dry Run Mode",
            variable=self.dry_run_var,
        )
        self.dry_run_checkbox.pack(side="left", padx=10)

        self.load_lists_button = tk.Button(
            button_frame,
            text="Get Changes",
            command=self.worker_manager.start_get_changes,
        )
        self.load_lists_button.pack(side="left", padx=10)

        self.apply_updates_button = tk.Button(
            button_frame,
            text="Apply Updates",
            command=self.worker_manager.start_apply_changes,
            state=tk.DISABLED,
        )
        self.apply_updates_button.pack(side="left", padx=10)

        self.populate_db_button = tk.Button(
            button_frame,
            text="Populate DB",
            command=self.worker_manager.start_populate_db,
        )
        self.populate_db_button.pack(side="left", padx=10)

        self.clear_all_trees_button = tk.Button(
            button_frame, text="Clear Tree", command=self.tree_manager.clear_all_trees
        )
        self.clear_all_trees_button.pack(side="left", padx=10)

    # Pop-up Folder Selection Methods
    def select_input_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.input_path_entry.delete(0, tk.END)
            self.input_path_entry.insert(0, folder_selected)
        self.user_config.input_folder = folder_selected
        save_user_config(self.user_config)

    def select_output_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.output_path_entry.delete(0, tk.END)
            self.output_path_entry.insert(0, folder_selected)
        self.user_config.output_folder = folder_selected
        save_user_config(self.user_config)

    # GUI Update Methods
    #
    # This is required, as Tkinter isn't happy if you
    # call its methods from a worker thread, rather than the main thread.
    def log_message(self, message, message_type="info"):
        """Add a message to the log area with appropriate styling."""
        self.message_log.config(state="normal")

        timestamp = time.strftime("%H:%M:%S")

        self.message_log.insert(
            "end",
            f"[{timestamp}] {message_type.upper()}: {message}\n",
            message_type,
        )

        self.message_log.see("end")
        self.message_log.config(state="disabled")

    def disable_all_buttons(self):
        """Disables all buttons to prevent re-clicks during long operations."""
        self.load_lists_button.config(state=tk.DISABLED)
        self.apply_updates_button.config(state=tk.DISABLED)
        self.populate_db_button.config(state=tk.DISABLED)
        self.clear_all_trees_button.config(state=tk.DISABLED)

    def start_time_estimation(self):
        """Initialize time estimation - delegate to progress manager"""
        self.progress_manager.start_time_estimation()

    # Queue Processing
    def on_worker_finished_gui(self):
        """Called when a worker thread signals completion."""
        self.load_lists_button.config(state=tk.NORMAL)
        self.populate_db_button.config(state=tk.NORMAL)
        self.clear_all_trees_button.config(state=tk.NORMAL)

        # Enable the refresh button if there is data in the lists
        if (
            self.add_tree.get_children()
            or self.update_tree.get_children()
            or self.delete_tree.get_children()
        ):
            self.apply_updates_button.config(state=tk.NORMAL)
        else:
            self.apply_updates_button.config(state=tk.DISABLED)

        # Ensure progress bar is at 100% on completion
        self.progress_manager.complete_progress()

    def process_queue(self):
        """Checks the queue for messages from the worker thread."""
        try:
            while True:
                msg_type, data = self.queue.get_nowait()
                if msg_type == "progress":
                    self.progress_manager.update_progress(data)
                elif msg_type == "message":
                    self.log_message(data, "info")
                elif msg_type == "error":
                    self.log_message(data, "error")
                elif msg_type == "add_to_tree":
                    list_type, file_path = data
                    if list_type == "add":
                        self.tree_manager.add_to_treeview(self.add_tree, file_path)
                    elif list_type == "update":
                        self.tree_manager.add_to_treeview(self.update_tree, file_path)
                    elif list_type == "delete":
                        self.tree_manager.add_to_treeview(self.delete_tree, file_path)
                elif msg_type == "clear_all_trees_gui":
                    self.tree_manager.clear_all_trees()
                elif msg_type == "done":
                    self.worker_manager.on_worker_finished()
                self.queue.task_done()
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_queue)


if __name__ == "__main__":
    root = tk.Tk()
    app = SimpleApp(root)
    root.mainloop()
