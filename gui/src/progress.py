import time
import tkinter as tk
from tkinter import ttk
from typing import Optional


class ProgressManager:
    def __init__(self, parent_app) -> None:
        self.parent_app = parent_app
        self.progress_frame: Optional[tk.Frame] = None
        self.progress_bar: Optional[ttk.Progressbar] = None
        self.time_label: Optional[tk.Label] = None

        # Variables for time estimation
        self.start_time: float = 0
        self.last_progress: float = 0
        self.last_progress_time: float = 0
        self.estimated_completion: Optional[float] = None

    def create_progress_bar(self, root: tk.Tk) -> None:
        """Create the progress bar and time estimation components"""
        self.progress_frame = tk.Frame(root, bd=2, relief="groove")
        self.progress_frame.pack(pady=10, padx=10, fill="x")

        tk.Label(self.progress_frame, text="Progress:").pack(side="left", padx=5)
        self.progress_bar = ttk.Progressbar(
            self.progress_frame, orient="horizontal", length=400, mode="determinate"
        )
        self.progress_bar.pack(side="left", expand=True, fill="x", padx=5)

        # Placeholder for time estimation
        self.time_label = tk.Label(self.progress_frame, text="--:--")
        self.time_label.pack(side="right", padx=5)

    def start_time_estimation(self) -> None:
        """Initialize the time estimation parameters"""
        self.start_time = time.time()
        self.last_progress = 0
        self.last_progress_time = self.start_time
        self.estimated_completion = None
        if self.time_label:
            self.time_label.config(text="Estimating...")

    def update_progress(self, value: float) -> None:
        """Updates the progress bar and time estimation"""
        if self.progress_bar:
            self.progress_bar["value"] = value
        self.update_time_estimate(value)

    def update_time_estimate(self, progress: float) -> None:
        """Update the estimated time to completion based on current progress"""
        if not self.time_label:
            return

        current_time = time.time()

        # Only update estimate if progress has actually changed
        if progress > self.last_progress:
            # Calculate elapsed time since start
            elapsed = current_time - self.start_time

            # Calculate time since last progress update
            time_delta = current_time - self.last_progress_time
            progress_delta = progress - self.last_progress

            # Only update if we have a meaningful progress change to reduce
            # fluctuations (i.e. 1% or more)
            if progress_delta >= 1.0:
                if progress > 0:
                    # Calculate estimated time for completion based on a linear
                    # projection based on elapsed time and progress
                    remaining_progress = 100 - progress
                    estimated_seconds = (elapsed / progress) * remaining_progress

                    # Smooth the estimate to avoid rapid fluctuations
                    if self.estimated_completion is None:
                        self.estimated_completion = estimated_seconds
                    else:
                        # Apply exponential smoothing
                        alpha = 0.3
                        self.estimated_completion = (
                            alpha * estimated_seconds
                            + (1 - alpha) * self.estimated_completion
                        )

                    # Format the estimate
                    self._update_time_display(
                        self.estimated_completion, is_estimate=True
                    )

                # Update last progress values
                self.last_progress = progress
                self.last_progress_time = current_time

        # If we're at 100%, show complete
        if progress >= 100:
            total_time = current_time - self.start_time
            self._update_time_display(total_time, is_estimate=False)

    def _update_time_display(self, seconds: float, is_estimate: bool = True) -> None:
        """Update the time label with formatted time"""
        if not self.time_label:
            return

        prefix = "~" if is_estimate else ""

        if seconds < 60:
            # Less than a minute
            self.time_label.config(text=f"{prefix}{int(seconds)}s")
        elif seconds < 3600:
            # Minutes and seconds
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            self.time_label.config(text=f"{prefix}{mins}m {secs}s")
        else:
            # Hours and minutes
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            self.time_label.config(text=f"{prefix}{hours}h {mins}m")

    def reset_progress(self) -> None:
        """Reset the progress bar to 0"""
        if self.progress_bar:
            self.progress_bar["value"] = 0
        if self.time_label:
            self.time_label.config(text="--:--")

    def complete_progress(self) -> None:
        """Set progress to 100% and show completion time"""
        if self.progress_bar:
            self.progress_bar["value"] = 100

        if self.start_time > 0:
            total_time = time.time() - self.start_time
            self._update_time_display(total_time, is_estimate=False)
