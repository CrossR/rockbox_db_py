# src/rockbox_db_py/classes/music_file.py

from datetime import datetime
import os
from typing import Optional, List, Dict, Any

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

from rockbox_db_py.utils.utils import mtime_to_fat


# Define supported formats for mutagen.File.
# These are passed to mutagen.File to help it identify file types.
SUPPORTED_MUTAGEN_FORMATS = [ASF, APE, FLAC, ID3, MP3, Vorbis, WavPack, MP4, Musepack]

# Commonly used extensions for the above formats.
SUPPORTED_MUSIC_EXTENSIONS: List[str] = [
    ".mp3",
    ".flac",
    ".ogg",
    ".wav",
    ".ape",
    ".wv",
    ".m4a",
    ".mp4",
    ".musepack",
    ".mpc",
]


# Converter functions for extracting and converting tag values
# These functions handle converting mutagen tag values to the appropriate Python types.
# This is necessary as without it...something angers multiprocessing + the pickling that
# happens when passing MusicFile objects between processes.
def _conv_string(value: Any) -> Optional[str]:
    """Converts a value to a single string, taking the first item if it's a list."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else None
    return str(value)


def _conv_int(value: Any) -> Optional[int]:
    """Converts a value to a single integer."""
    if value is None:
        return None
    try:
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        return int(value)
    except (ValueError, TypeError):
        return None


def _conv_float(value: Any) -> Optional[float]:
    """Converts a value to a single float."""
    return float(value) if value is not None else None


def _extract_comment_value(mutagen_tags: mutagen.File) -> Optional[str]:
    """Robustly attempts to retrieve the comment tag from various Mutagen sources."""
    if mutagen_tags is None:
        return None

    # Try 'comment' key directly (mutagen.File(easy=True) maps this)
    comment_val = mutagen_tags.get("comment")
    if comment_val is not None:
        converted_val = _conv_string(comment_val)
        if converted_val:
            return converted_val

    # For ID3 (MP3s), check raw COMM frames.
    if isinstance(mutagen_tags, (EasyMP3, EasyID3)):
        if hasattr(mutagen_tags, "_id3") and hasattr(mutagen_tags._id3, "frames"):
            for frame_id, frame_obj in mutagen_tags._id3.frames.items():
                if frame_id.startswith("COMM"):  # 'COMM' frames store comments
                    if hasattr(frame_obj, "text") and frame_obj.text:
                        # Join all text parts of a COMM frame, if multiple
                        return _conv_string(" ".join(map(str, frame_obj.text)))

    # For ASF (WMA) files, check specific common keys.
    if isinstance(mutagen_tags, ASF):
        if "WM/Comments" in mutagen_tags:
            return _conv_string(mutagen_tags["WM/Comments"])
        if "Description" in mutagen_tags:
            return _conv_string(mutagen_tags["Description"])

    # For MP4 files, check specific common keys.
    if isinstance(mutagen_tags, MP4):
        if "\xa9cmt" in mutagen_tags:  # iTunes 'comment' tag
            return _conv_string(mutagen_tags["\xa9cmt"])
        if "desc" in mutagen_tags:  # General description field in MP4
            return _conv_string(mutagen_tags["desc"])

    return None

def _conv_track_or_disc(value: Any) -> Optional[int]:
    """
    Converts a track or disc string value to an integer.
    I.e. 10/12 -> 10, 1/2 -> 1, etc.
    """
    value_str = _conv_string(value)

    if value_str is None:
        return None

    # Split by '/' and take the first part
    parts = value_str.split('/')
    if parts:
        try:
            return int(parts[0].strip())  # Convert the first part to an integer
        except ValueError:
            return None



# Tuples of (attribute_name, mutagen_getter_key_string, converter_function)
TAG_EXTRACTION_RULES = [
    ("length", "info.length", _conv_float),  # mutagen.File.info.length attribute
    ("bitrate", "info.bitrate", _conv_int),  # mutagen.File.info.bitrate attribute
    ("title", "title", _conv_string),
    ("artist", "artist", _conv_string),
    ("album", "album", _conv_string),
    ("genre", "genre", _conv_string),
    ("composer", "composer", _conv_string),
    ("comment", "comment", _extract_comment_value),
    ("albumartist", "albumartist", _conv_string),
    ("grouping", "grouping", _conv_string),
    ("date", "date", _conv_string),
    ("discnumber", "discnumber", _conv_track_or_disc),
    ("tracknumber", "tracknumber", _conv_track_or_disc),
]


class MusicFile:
    """
    Represents an audio file on the PC filesystem, encapsulating its path,
    size, modification time, and all parsed metadata tags as raw Python types.
    This class is designed to be fully picklable for multiprocessing.
    """

    def __init__(
        self,
        filepath: str,
        filesize: int,
        modtime_unix: int,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        genre: Optional[str] = None,
        composer: Optional[str] = None,
        comment: Optional[str] = None,
        albumartist: Optional[str] = None,
        grouping: Optional[str] = None,
        date: Optional[str] = None,
        discnumber: Optional[int] = None,
        tracknumber: Optional[int] = None,
        bitrate: Optional[int] = None,
        length: Optional[float] = None,
    ):
        self.filepath: str = filepath
        self.filesize: int = filesize
        self.modtime_unix: int = modtime_unix
        self.modtime_fat32: int = mtime_to_fat(modtime_unix)

        self.title: Optional[str] = title
        self.artist: Optional[str] = artist
        self.album: Optional[str] = album
        self.genre: Optional[str] = genre
        self.composer: Optional[str] = composer
        self.comment: Optional[str] = comment
        self.albumartist: Optional[str] = albumartist
        self.grouping: Optional[str] = grouping
        self.date: Optional[str] = date
        self.discnumber: Optional[int] = discnumber
        self.tracknumber: Optional[int] = tracknumber
        self.bitrate: Optional[int] = (
            int(bitrate / 1000) if bitrate is not None else None
        )
        self.length: Optional[int] = (
            int(length * 1000.0) if length is not None else None
        )

        # Get some useful derived properties
        self.filename: str = os.path.basename(filepath)
        self.file_extension: str = os.path.splitext(filepath)[1].lower()

        self.grouping = self.title if self.grouping is None else self.grouping
        self.canonicalartist = self.artist if self.artist else self.albumartist
        self.composer = self.composer if self.composer else "<Untagged>"

        self.year = None

        # Attempt to extract year from date if available
        if self.date:
            try:
                # Try to parse date as YYYY-MM-DD or similar formats
                parsed_date = datetime.strptime(self.date, "%Y-%m-%d")
                self.year = parsed_date.year
            except ValueError:
                # If parsing fails, just convert the str to an int
                self.year = int(self.date) if self.date.isdigit() else None

    @classmethod
    def from_filepath(cls, path: str) -> Optional["MusicFile"]:
        """
        Creates a MusicFile instance by reading file system info and audio tags.
        Metadata is extracted and stored as raw Python types.
        """
        try:
            stat_info = os.stat(path)
            filesize: int = stat_info.st_size
            modtime_unix: int = int(stat_info.st_mtime)

            mutagen_tags: Optional[mutagen.File] = mutagen.File(path, easy=True)
            mutagen_tags_all: Optional[mutagen.File] = mutagen.File(path).tags

            print(mutagen_tags)

            if mutagen_tags is None:
                print(f"Unsupported file format or no tags found for: {path}")
                return None

            extracted_tags: Dict[str, Any] = {}
            for attr_name, mutagen_key_str, converter_func in TAG_EXTRACTION_RULES:
                try:
                    # Handle attributes directly from mutagen_tags.info (e.g., 'info.length')
                    if "." in mutagen_key_str:
                        obj_name, attr_name_in_obj = mutagen_key_str.split(".")
                        raw_value = getattr(mutagen_tags, obj_name, None)
                        if raw_value is not None:
                            raw_value = getattr(raw_value, attr_name_in_obj, None)

                    else:
                        raw_value = mutagen_tags.get(mutagen_key_str)

                    extracted_tags[attr_name] = converter_func(raw_value)
                except (AttributeError, KeyError, ValueError, IndexError) as e:
                    extracted_tags[attr_name] = None

            if extracted_tags.get("comment") is None:
                # If no comment tag found, try to extract from COMM tags
                # 'XXX' is the default language for comments in mutagen
                for comment in mutagen_tags_all.getall("COMM") or []:
                    if (
                        comment.lang == "XXX"
                    ):  # 'XXX' is the default language for comments in mutagen
                        comment_str = str(comment.text[0])

                        # If the comment is empty, skip it
                        if comment_str:
                            # Cut it down to 255 characters if it's too long
                            if len(comment_str) > 255:
                                comment_str = comment_str[:255]
                            extracted_tags["comment"] = comment_str
                            break

            # Create MusicFile instance, passing extracted tags as keyword arguments
            return cls(
                filepath=path,
                filesize=filesize,
                modtime_unix=modtime_unix,
                **extracted_tags,
            )
        except FileNotFoundError:
            print(f"File not found: {path}")
            return None
        except Exception as e:
            print(f"Error processing file '{path}': {e}")
            return None

    def __repr__(self) -> str:
        """Provides a developer-friendly string representation."""
        title_val = self.title if self.title is not None else "(No Title)"
        artist_val = self.artist if self.artist is not None else "(No Artist)"
        return f"MusicFile(filepath='{self.filepath}', title='{title_val}', artist='{artist_val}')"

    def generate_unique_id(self) -> str:
        """
        Generates a unique ID for this music file based on its filepath and modification time.
        This is used for de-duplication and tracking in the database.
        """
        return f"{self.filepath}_{self.modtime_unix}"
