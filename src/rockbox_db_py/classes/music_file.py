# src/rockbox_db_py/classes/music_file.py

import os
from typing import Optional, List, Union, Dict, Any  # Added Any for generic type
import mutagen
from mutagen.asf import ASF
from mutagen.apev2 import APEv2File as APE
from mutagen.flac import FLAC
from mutagen.easyid3 import EasyID3FileType as ID3
from mutagen.mp3 import EasyMP3 as MP3
from mutagen.oggvorbis import OggVorbis as Vorbis
from mutagen.wavpack import WavPack
from mutagen.mp4 import MP4
from mutagen.musepack import Musepack

from rockbox_db_py.utils.utils import mtime_to_fat  # For FAT32 mtime conversion


# Define supported formats for mutagen.File.
# These are passed to mutagen.File to help it identify file types.
SUPPORTED_MUTAGEN_FORMATS = [ASF, APE, FLAC, ID3, MP3, Vorbis, WavPack, MP4, Musepack]


class _MusicFileTags:
    """
    Internal helper class to abstract audio file metadata access using Mutagen.
    Provides a consistent attribute-like interface for various tag fields
    across different audio file formats.
    """

    # --- Converters ---
    # These static methods convert raw values from Mutagen into standardized formats.
    @staticmethod
    def _conv_string(value: Any) -> Optional[str]:
        """Converts a value to a single string, taking the first item if it's a list."""
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return str(value[0]) if value else None
        return str(value)

    @staticmethod
    def _conv_string_list(value: Any) -> Optional[List[str]]:
        """Converts a value to a list of strings."""
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return [str(v) for v in value if v is not None]
        return [str(value)]

    @staticmethod
    def _conv_int(value: Any) -> Optional[int]:
        """Converts a value to a single integer."""
        if value is None:
            return None
        try:
            if isinstance(value, (list, tuple)):
                value = value[0] if value else None
            return int(value) if value is not None else None
        except (ValueError, TypeError):
            return None

    # --- Standard Tag Mappings ---
    # This dictionary defines how standard tag names (keys) map to Mutagen's internal
    # getters and the converter functions. This is a class attribute.
    _tag_field_map: Dict[str, Dict[str, callable]] = {
        # File information (Mutagen often stores original filepath as 'filename' attribute)
        "filepath": {
            "getter": lambda obj: obj.get("filename"),
            "convert": _conv_string,
        },
        "length": {
            "getter": lambda obj: obj.info.length,
            "convert": _conv_int,
        },  # Mutagen's info.length is in seconds (float)
        "bitrate": {
            "getter": lambda obj: obj.info.bitrate,
            "convert": _conv_int,
        },  # Mutagen's info.bitrate is in bits/s (int)
        # Common audio tags (Mutagen 'easy' handler often maps these directly)
        "title": {"getter": lambda obj: obj.get("title"), "convert": _conv_string},
        "artist": {"getter": lambda obj: obj.get("artist"), "convert": _conv_string},
        "album": {"getter": lambda obj: obj.get("album"), "convert": _conv_string},
        "genre": {"getter": lambda obj: obj.get("genre"), "convert": _conv_string},
        "composer": {
            "getter": lambda obj: obj.get("composer"),
            "convert": _conv_string,
        },
        "comment": {"getter": lambda obj: obj.get("comment"), "convert": _conv_string},
        "albumartist": {
            "getter": lambda obj: obj.get("albumartist"),
            "convert": _conv_string,
        },
        "grouping": {
            "getter": lambda obj: obj.get("grouping"),
            "convert": _conv_string,
        },
        # Numeric tags (often come as lists in Mutagen, need to extract single int)
        "year": {
            "getter": lambda obj: obj.get("date"),
            "convert": _conv_int,
        },  # Mutagen 'date' might be year or YYYY-MM-DD
        "discnumber": {
            "getter": lambda obj: obj.get("discnumber"),
            "convert": _conv_int,
        },
        "tracknumber": {
            "getter": lambda obj: obj.get("tracknumber"),
            "convert": _conv_int,
        },
    }

    def __init__(self, mutagen_tags: Optional[mutagen.File]):
        self._mutagen_tags = mutagen_tags

    def __getattr__(self, name: str) -> Optional[Union[str, int, List[str], List[int]]]:
        """
        Enables attribute-like access (e.g., tags.artist) for tag values.
        Looks up the appropriate getter and converter in _tag_field_map.
        """
        if name in self._tag_field_map:
            mapping_info = self._tag_field_map[name]
            try:
                raw_value = mapping_info["getter"](self._mutagen_tags)
                return mapping_info["convert"](raw_value)
            except (KeyError, AttributeError, ValueError, IndexError):
                return None
        elif (
            name == "_mutagen_tags"
        ):  # Allow direct access to the internal mutagen object
            return object.__getattribute__(self, name)
        else:
            return None  # Return None for unmapped or non-existent attributes


class MusicFile:
    """
    Represents an audio file on the PC filesystem, encapsulating its path,
    size, modification time, and parsed metadata tags.
    """

    def __init__(
        self,
        filepath: str,
        filesize: int,
        modtime_unix: int,
        mutagen_tags: Optional[mutagen.File] = None,
    ):
        self.filepath: str = filepath
        self.filesize: int = filesize
        self.modtime_unix: int = modtime_unix
        # Convert to Rockbox's FAT32 mtime format
        self.modtime_fat32: int = mtime_to_fat(modtime_unix)

        self._tags: _MusicFileTags = _MusicFileTags(mutagen_tags)

    @classmethod
    def from_filepath(cls, path: str) -> Optional["MusicFile"]:
        """
        Creates a MusicFile instance by reading file system info and audio tags.

        Args:
            path: The filesystem path to the audio file.

        Returns:
            A MusicFile instance, or None if the file cannot be read or tags parsed.
        """
        try:
            stat_info = os.stat(path)
            filesize: int = stat_info.st_size
            modtime_unix: int = int(stat_info.st_mtime)

            mutagen_tags: Optional[mutagen.File] = mutagen.File(path, easy=True)

            if mutagen_tags is None:
                return None

            return cls(
                filepath=path,
                filesize=filesize,
                modtime_unix=modtime_unix,
                mutagen_tags=mutagen_tags,
            )
        except FileNotFoundError:
            return None
        except Exception as e:
            return None

    def __getattr__(self, name: str) -> Any:
        """Delegates tag attribute access (e.g., music_file.artist) to the internal _tags helper."""
        if hasattr(self._tags, name):
            return getattr(self._tags, name)
        return object.__getattribute__(self, name)

    def __repr__(self) -> str:
        """Provides a developer-friendly string representation."""
        # Attempt to get title and artist for a more informative representation
        title_val = getattr(self, "title", "(No Title)")
        artist_val = getattr(self, "artist", "(No Artist)")
        return f"MusicFile(filepath='{self.filepath}', title='{title_val}', artist='{artist_val}')"
