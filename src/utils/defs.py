# defs.py
# Based on tagcache.h and tagcache.c from Rockbox source code (Commit #5344606)

# MAGIC DB version number
TAG_MAGIC = 0x54434810

# From tagcache.h: enum tag_type, up to TAG_COUNT
TAG_TYPES = [
    'artist',
    'album',
    'genre',
    'title',
    'filename',
    'composer',
    'comment',
    'albumartist',
    'grouping',
    'year',           # Embedded numeric tag
    'discnumber',     # Embedded numeric tag
    'tracknumber',    # Embedded numeric tag
    'canonicalartist',# Byte offset for tag file
    'bitrate',        # Embedded numeric tag
    'length',         # Embedded numeric tag (in milliseconds)
    'playcount',      # Embedded numeric tag
    'rating',         # Embedded numeric tag
    'playtime',       # Embedded numeric tag
    'lastplayed',     # Embedded numeric tag
    'commitid',       # Embedded numeric tag
    'mtime',          # Embedded numeric tag
    'lastelapsed',    # Embedded numeric tag
    'lastoffset'      # Embedded numeric tag
]
TAG_COUNT = len(TAG_TYPES)

# Indices for tags stored as byte offsets in separate .tcd files (first 9 + canonicalartist)
TAG_FILES = {
    "artist": 0,
    "album": 1,
    "genre": 2,
    "title": 3,
    "filename": 4,
    "composer": 5,
    "comment": 6,
    "albumartist": 7,
    "grouping": 8,
    "canonicalartist": 12
}
FILE_TAG_INDICES = [value for value in TAG_FILES.values()]
FILE_TAG_NAMES = [name for name in TAG_FILES.keys()]
INDEX_FILE = 'database_idx.tcd'

# Indices for tags embedded directly in database_idx.tcd
EMBEDDED_TAG_INDICES = [
    idx for idx in range(TAG_COUNT) if idx not in FILE_TAG_INDICES
]

# Flag definitions from tagcache.c
FLAG_DELETED = 0x0001
FLAG_DIRCACHE = 0x0002
FLAG_DIRTYNUM = 0x0004
FLAG_TRKNUMGEN = 0x0008
FLAG_RESURRECTED = 0x0010

# Tags are encoded in UTF-8
ENCODING = 'utf-8'

# Tag data padding requirement
TAGFILE_ENTRY_CHUNK_LENGTH = 8