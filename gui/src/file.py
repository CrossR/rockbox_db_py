# File Class

import os
from typing import Optional

class File:
    """
    Represents a file with its path and size.

    :param path: Path to the file.
    :param size: Size of the file in bytes.
    """

    def __init__(
        self, path: str, size: Optional[int] = None, mod_time: Optional[float] = None
    ):
        self.path = path

        if not os.path.exists(path) and (size is None or mod_time is None):
            raise FileNotFoundError(f"File not found: {path}")

        self.size = os.path.getsize(path) if size is None else size
        self.mod_time = os.path.getmtime(path) if mod_time is None else mod_time

    def __eq__(self, other):
        if not isinstance(other, File):
            return NotImplemented
        return (
            self.path == other.path
            and self.size == other.size
            and self.mod_time == other.mod_time
        )

    def __repr__(self):
        return f"File(path={self.path}, size={self.size}, mod_time={self.mod_time})"

