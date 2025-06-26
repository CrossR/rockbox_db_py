# rockbox_db_file_type.py
from enum import Enum

from rockbox_db_py.utils.defs import TAG_MAGIC

class RockboxDBFileType(Enum):
    """
    Enum for different Rockbox database file types, with associated properties.
    """
    # Main index file
    INDEX = {
        "filename": "database_idx.tcd",
        "tag_index": None,
        "magic": TAG_MAGIC
    }

    ARTIST = {
        "filename": "database_0.tcd",
        "tag_index": 0,
        "magic": TAG_MAGIC
    }
    ALBUM = {
        "filename": "database_1.tcd",
        "tag_index": 1,
        "magic": TAG_MAGIC
    }
    GENRE = {
        "filename": "database_2.tcd",
        "tag_index": 2,
        "magic": TAG_MAGIC
    }
    TITLE = {
        "filename": "database_3.tcd",
        "tag_index": 3,
        "magic": TAG_MAGIC
    }
    FILENAME = {
        "filename": "database_4.tcd",
        "tag_index": 4,
        "magic": TAG_MAGIC,
    }
    COMPOSER = {
        "filename": "database_5.tcd",
        "tag_index": 5,
        "magic": TAG_MAGIC
    }
    COMMENT = {
        "filename": "database_6.tcd",
        "tag_index": 6,
        "magic": TAG_MAGIC
    }
    ALBUMARTIST = {
        "filename": "database_7.tcd",
        "tag_index": 7,
        "magic": TAG_MAGIC
    }
    GROUPING = {
        "filename": "database_8.tcd",
        "tag_index": 8,
        "magic": TAG_MAGIC
    }
    CANONICALARTIST = {
        "filename": "database_12.tcd",
        "tag_index": 12,
        "magic": TAG_MAGIC
    }

    # Set up the enum member instances, before __init__.
    def __new__(cls, props_dict):
        obj = object.__new__(cls)
        obj._value_ = props_dict
        object.__setattr__(obj, 'props', props_dict)

        return obj

    def __getattr__(self, name):
        try:
            return self.props[name]
        except KeyError as e:
            raise AttributeError(f"'{self.name}' (RockboxDBFileType member) has no attribute '{name}'") from e

    @property
    def is_filename_db(self):
        """Returns True if this file type is the filename database."""
        return self == RockboxDBFileType.FILENAME

    @classmethod
    def from_filename(cls, filename):
        """Returns the RockboxDBFileType enum member for a given database filename."""
        for file_type in cls:
            if file_type.filename == filename:
                return file_type
        raise ValueError(f"Unknown Rockbox database file: {filename}")

    @classmethod
    def from_tag_index(cls, tag_index):
        """Returns the RockboxDBFileType enum member for a given tag index."""
        for file_type in cls:
            if file_type.tag_index == tag_index:
                return file_type
        raise ValueError(f"No Rockbox database file associated with tag index: {tag_index}")