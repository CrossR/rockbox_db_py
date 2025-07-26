import os
import sys
import time

from src.file import File


def iter_with_progress(iterable, prefix: str = "", size: int = 60, item_details=None):
    """
    Display a progress bar for an iterable with estimated time remaining.

    Args:
        iterable: The iterable to process
        prefix: Text to display before the progress bar
        size: Width of the progress bar in characters

    Yields:
        Each item from the iterable
    """
    count = len(iterable)
    start = time.time()

    if count == 0:
        return

    def show(j: float, item=None):
        if j <= 0:
            j = 0.1

        x = int(size * j / count)
        elapsed = time.time() - start
        remaining = (elapsed / j) * (count - j) if j > 0 else 0

        mins, sec = divmod(remaining, 60)
        time_str = f"{int(mins):02}:{sec:05.2f}"

        details = f" ({item_details(item)})" if item_details and item else ""

        print(
            f"{prefix} [{'█' * x}{('.' * (size - x))}] {j}/{count} Est wait {time_str}{details}",
            end="\r",
            file=sys.stdout,
            flush=True,
        )

    # Initial display
    show(0.1)

    # Process each item
    for i, item in enumerate(iterable):
        yield item
        show(i + 1, item)

    # Add newline after completion
    print("", flush=True, file=sys.stdout)


def normalise_path(file: File, root: str) -> str:
    """
    Normalise the file path to be relative to the given root directory.

    :param file: File object to normalize.
    :param root: Root directory to normalize against.
    """
    if not os.path.isabs(root):
        raise ValueError("Root directory must be an absolute path.")

    return os.path.relpath(file.path, root)
