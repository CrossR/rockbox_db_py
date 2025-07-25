import os
from tkinter import ttk


class TreeViewManager:
    def __init__(self, parent_app, root):
        self.parent_app = parent_app
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(pady=10, padx=10, expand=True, fill="both")

        self.add_tab = ttk.Frame(self.notebook)
        self.update_tab = ttk.Frame(self.notebook)
        self.delete_tab = ttk.Frame(self.notebook)

        # Add tabs with initial titles
        self.notebook.add(self.add_tab, text="To Add (0)")
        self.notebook.add(self.update_tab, text="To Update (0)")
        self.notebook.add(self.delete_tab, text="To Delete (0)")

        # Create Treeviews with scrollbars for each tab
        self.add_tree = self._create_treeview(self.add_tab)
        self.update_tree = self._create_treeview(self.update_tab)
        self.delete_tree = self._create_treeview(self.delete_tab)

    def _create_treeview(self, parent):
        """Helper method to create a treeview with scrollbars"""
        # Create a frame to hold the treeview and scrollbars
        frame = ttk.Frame(parent)
        frame.pack(expand=True, fill="both", padx=5, pady=5)

        # Create vertical scrollbar
        vsb = ttk.Scrollbar(frame, orient="vertical")
        vsb.pack(side="right", fill="y")

        # Create horizontal scrollbar
        hsb = ttk.Scrollbar(frame, orient="horizontal")
        hsb.pack(side="bottom", fill="x")

        # Create the treeview
        tree = ttk.Treeview(
            frame, selectmode="extended", yscrollcommand=vsb.set, xscrollcommand=hsb.set
        )

        # Configure the scrollbars
        vsb.config(command=tree.yview)
        hsb.config(command=tree.xview)

        # Set up the treeview columns
        tree["columns"] = ("fullpath",)
        tree.column("#0", width=300, minwidth=200)
        tree.column("fullpath", width=0, stretch=False, anchor="w")

        # And the headings
        tree.heading("#0", text="File", anchor="w")
        tree.heading("fullpath", text="Full Path", anchor="w")

        tree.pack(expand=True, fill="both")
        return tree

    def add_to_treeview(self, tree, file_path, size=0):
        """Add a file path to a treeview with proper hierarchy, removing input/output prefixes"""
        # Get input and output folders from parent app
        input_folder = os.path.normpath(self.parent_app.input_path_entry.get())
        output_folder = os.path.normpath(self.parent_app.output_path_entry.get())
        file_path = os.path.normpath(file_path)

        # Remove either input or output folder prefix to get relative path
        rel_path = None

        if file_path.startswith(input_folder):
            # File is in input folder
            rel_path = file_path[len(input_folder) :].lstrip(os.sep)
        elif file_path.startswith(output_folder):
            # File is in output folder
            rel_path = file_path[len(output_folder) :].lstrip(os.sep)

        # If no match found, remove drive letter and continue with shortened path
        if not rel_path:
            parts = file_path.split(os.sep)
            if parts and ":" in parts[0]:
                rel_path = os.sep.join(parts[1:])
            else:
                rel_path = file_path

        # Split into path parts for the tree hierarchy
        path_parts = (
            rel_path.split(os.sep) if rel_path else [os.path.basename(file_path)]
        )

        # Skip if we have no valid parts
        if not path_parts or all(not part for part in path_parts):
            tree.insert(
                "",
                "end",
                text=f"🗋 {os.path.basename(file_path)}",
                values=(file_path, f"{size/1024:.2f}" if size else ""),
            )
            return

        # Build the tree
        current_path = ""
        parent = ""

        for i, part in enumerate(path_parts):
            if not part:
                continue

            # Build current level path
            current_path = part if not current_path else f"{current_path}_{part}"

            # Create ID for this node
            item_id = f"item_{current_path}"

            # Check if node exists or create it
            if not tree.exists(item_id):
                is_file = i == len(path_parts) - 1
                size_display = f"{size/1024:.2f}" if is_file and size > 0 else ""
                icon = "🗋" if is_file else "📁"

                tree.insert(
                    parent,
                    "end",
                    item_id,
                    text=f"{icon} {part}",
                    values=(file_path if is_file else "", size_display),
                )
            parent = item_id

        # Expand root level
        if path_parts and path_parts[0]:
            root_id = f"item_{path_parts[0]}"
            if tree.exists(root_id):
                tree.item(root_id, open=True)

        # Finally, update the tab titles to reflect the new item
        self.update_tab_titles()

    def clear_treeview(self, tree):
        """Clear all items from a treeview"""
        for item in tree.get_children():
            tree.delete(item)

    def clear_all_trees(self):
        """Clears all treeviews"""
        self.clear_treeview(self.add_tree)
        self.clear_treeview(self.update_tree)
        self.clear_treeview(self.delete_tree)

        # Update tab titles after clearing
        self.update_tab_titles()

    def update_tab_titles(self):
        """Update tab titles to show the number of files in each tab"""
        # Count all files in each tree
        add_count = self._count_files_in_tree(self.add_tree)
        update_count = self._count_files_in_tree(self.update_tree)
        delete_count = self._count_files_in_tree(self.delete_tree)

        # Update the tab titles
        self.notebook.tab(self.add_tab, text=f"To Add ({add_count})")
        self.notebook.tab(self.update_tab, text=f"To Update ({update_count})")
        self.notebook.tab(self.delete_tab, text=f"To Delete ({delete_count})")

    def _count_files_in_tree(self, tree, parent=""):
        """
        Recursively count all file items in the tree

        Args:
            tree: The treeview to count files in
            parent: The parent node ID to start counting from (empty for root)

        Returns:
            Total number of file nodes (not folders)
        """
        count = 0
        for item_id in tree.get_children(parent):
            item_text = tree.item(item_id, "text")
            if "🗋" in item_text:
                count += 1

            # Recursively count files in children
            count += self._count_files_in_tree(tree, item_id)

        return count

    def get_all_files_from_tree(self, tree, parent=""):
        """
        Recursively collect all file paths from the tree

        Args:
            tree: The treeview to collect files from
            parent: The parent node ID to start from (empty for root)

        Returns:
            List of all file paths (not folders)
        """
        file_paths = []
        for item_id in tree.get_children(parent):
            # Check if this is a file by its icon
            item_text = tree.item(item_id, "text")
            values = tree.item(item_id, "values")

            if "🗋" in item_text and values and values[0]:
                # Extract just the relative path by removing input/output folder prefixes
                input_folder = os.path.normpath(self.parent_app.input_path_entry.get())
                output_folder = os.path.normpath(
                    self.parent_app.output_path_entry.get()
                )
                file_path = os.path.normpath(values[0])

                # Get the relative path
                if file_path.startswith(input_folder):
                    rel_path = file_path[len(input_folder) :].lstrip(os.sep)
                    file_paths.append(rel_path)
                elif file_path.startswith(output_folder):
                    rel_path = file_path[len(output_folder) :].lstrip(os.sep)
                    file_paths.append(rel_path)
                else:
                    # If we can't determine the relative path, use the full path
                    file_paths.append(file_path)

            # Recursively get files from child nodes
            file_paths.extend(self.get_all_files_from_tree(tree, item_id))

        return file_paths
