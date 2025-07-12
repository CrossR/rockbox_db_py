# music_file.py
#
# Represents an audio file on the PC filesystem, encapsulating its path,
# size, modification time, and all parsed metadata tags as raw Python types.
# This class is designed to be fully picklable for multiprocessing.

from dataclasses import dataclass
import os
from typing import Optional, List, Dict, Any

from rockbox_db_py.utils.utils import mtime_to_fat

from mediafile import MediaFile, TYPES


# Define supported formats for mutagen.File.
# These are passed to mutagen.File to help it identify file types.
SUPPORTED_MUTAGEN_FORMATS = [format for format in TYPES.values()]

# Commonly used extensions for the above formats.
SUPPORTED_MUSIC_EXTENSIONS: List[str] = [f".{ext}" for ext in TYPES.keys()]


@dataclass
class TagType:
    rockbox_name: str
    mediafile_names: List[str]
    type: str


# Define the mapping of Rockbox tags to MediaFile attributes.
# If there is multiple options for a tag, use a list.
ROCKBOX_TO_MEDIAFILE = [
    TagType("artist", ["artist", "performer"], "str"),
    TagType("album", ["album"], "str"),
    TagType("genre", ["genre"], "str"),
    TagType("title", ["title"], "str"),
    TagType("composer", ["composer"], "str"),
    TagType("comment", ["comments"], "str"),
    TagType("albumartist", ["albumartist"], "str"),
    TagType("grouping", ["grouping", "title"], "str"),
    TagType("date", ["date", "year"], "str"),
    TagType("year", ["year"], "int"),
    TagType("discnumber", ["disc"], "int"),
    TagType("tracknumber", ["track"], "int"),
    TagType("bitrate", ["bitrate"], "int"),
    TagType("length", ["length"], "float"),
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
        year: Optional[int] = None,
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
        self.year: Optional[int] = year
        self.discnumber: Optional[int] = discnumber
        self.tracknumber: Optional[int] = tracknumber
        self.bitrate: Optional[int] = (
            int(bitrate / 1000) if bitrate is not None else None
        )
        self.length: Optional[int] = (
            int(length * 1000.0) if length is not None else None
        )

        # Get some useful derived properties
        self.file_extension: str = os.path.splitext(filepath)[1].lower()

        self.grouping = self.title if self.grouping is None else self.grouping
        self.canonicalartist = self.artist if self.artist else self.albumartist
        self.composer = self.composer if self.composer else "<Untagged>"

    @property
    def filename(self) -> str:
        """
        Rockbox expects a "filename" property that is really the full path.
        This is used, rather than a self.filename property, to ensure that
        the file path is always available and consistent.

        Returns:
            str: The file path associated with this music file.
        """
        return self.filepath

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

            media_file: MediaFile = MediaFile(path)

            if media_file is None:
                print(f"Unsupported file format or no tags found for: {path}")
                return None

            extracted_tags: Dict[str, Any] = {}
            for tag_props in ROCKBOX_TO_MEDIAFILE:
                rockbox_name = tag_props.rockbox_name
                mediafile_tags = tag_props.mediafile_names
                tag_type = tag_props.type

                # Use getattr to get the tag value, defaulting to None if not present
                for mediafile_tag in mediafile_tags:
                    tag_value = getattr(media_file, mediafile_tag, None)
                    if tag_value is not None:
                        break

                # Convert the tag value to the appropriate type
                if tag_type == "str":
                    extracted_tags[rockbox_name] = str(tag_value) if tag_value else None
                elif tag_type == "int":
                    extracted_tags[rockbox_name] = int(tag_value) if tag_value else None
                elif tag_type == "float":
                    extracted_tags[rockbox_name] = (
                        float(tag_value) if tag_value else None
                    )
                else:
                    extracted_tags[rockbox_name] = tag_value

            # If the comment tag is not found, set a default value.
            # TODO: How on earth does RockBox generate this? It seems to be vary, but no idea.
            if extracted_tags.get("comment") is None:
                extracted_tags["comment"] = (
                    " 0000167A 0000167A 00003832 00003832 00000000 00000000 00008608 00008608 00000000 00000000"
                )

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

    def info(self) -> str:
        """
        Returns a string with basic information about the music file.
        This is useful for debugging and logging.
        """
        return "\n".join(
            [
                "MusicFile Info:",
                f"  Filepath: {self.filepath}",
                f"  Filesize: {self.filesize} bytes",
                f"  Modification Time (Unix): {self.modtime_unix}",
                f"  Modification Time (FAT32): {self.modtime_fat32}",
                f"  Title: {self.title if self.title else '(No Title)'}",
                f"  Artist: {self.artist if self.artist else '(No Artist)'}",
                f"  Album: {self.album if self.album else '(No Album)'}",
                f"  Genre: {self.genre if self.genre else '(No Genre)'}",
                f"  Composer: {self.composer if self.composer else '(No Composer)'}",
                f"  Comment: {self.comment if self.comment else '(No Comment)'}",
                f"  Album Artist: {self.albumartist if self.albumartist else '(No Album Artist)'}",
                f"  Grouping: {self.grouping if self.grouping else '(No Grouping)'}",
                f"  Date: {self.date if self.date else '(No Date)'}",
                f"  Year: {self.year if self.year is not None else '(No Year)'}",
                f"  Disc Number: {self.discnumber if self.discnumber is not None else '(No Disc Number)'}",
                f"  Track Number: {self.tracknumber if self.tracknumber is not None else '(No Track Number)'}",
                f"  Bitrate: {self.bitrate if self.bitrate is not None else '(No Bitrate)'} kbps",
                f"  Length: {self.length if self.length is not None else '(No Length)'} ms",
            ]
        )

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
