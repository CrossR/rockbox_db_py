# General purpose utility functions for Rockbox database management.

import time


def mtime_to_fat(mtime: int) -> int:
    """
    Converts a Unix timestamp (mtime from os.stat) to Rockbox's FAT32 mtime format.
    The FAT32 mtime schema is detailed in the fat32 documentation.
    """
    # Deconstruct Unix timestamp into local time components
    year, month, day, hour, minute, second = time.localtime(mtime)[:-3]

    # Adjust year for FAT32 (relative to 1980)
    year = year - 1980

    # Assemble FAT32 date word (16 bits)
    # Bits 15-9: Year (0-127, relative to 1980)
    # Bits 8-5: Month (1-12)
    # Bits 4-0: Day (1-31)
    date_word: int = 0
    date_word |= year << 9
    date_word |= month << 5
    date_word |= day

    # Assemble FAT32 time word (16 bits)
    # Bits 15-11: Hour (0-23)
    # Bits 10-5: Minute (0-59)
    # Bits 4-0: Second / 2 (0-29, so 2-second increments)
    time_word: int = 0
    time_word |= hour << 11
    time_word |= minute << 5
    time_word |= second // 2  # FAT32 seconds are 2-second increments

    # Combine date and time words into a 32-bit FAT timestamp
    fat_timestamp: int = (date_word << 16) | time_word
    return fat_timestamp


def fat_to_mtime(fat: int) -> int:
    """
    Converts a Rockbox's FAT32 mtime format to a Unix timestamp (seconds since epoch).
    """
    # Extract FAT32 date and time components
    date_word: int = fat >> 16
    time_word: int = fat & 0x0000FFFF

    # Deconstruct FAT32 date word
    year: int = ((date_word >> 9) & 0x7F) + 1980  # Year is 0-127, relative to 1980
    month: int = (date_word >> 5) & 0x0F
    day: int = date_word & 0x1F

    # Deconstruct FAT32 time word
    hour: int = (time_word >> 11) & 0x1F
    minute: int = (time_word >> 5) & 0x3F
    second: int = (time_word & 0x1F) * 2  # Seconds are 2-second increments

    # Assemble into a tuple suitable for time.mktime
    # -1 for DST not applied, -1 for no zoneinfo
    # mktime expects a 9-tuple: (year, month, day, hour, minute, second, weekday, yearday, isdst)
    unix_timestamp: int = int(
        time.mktime((year, month, day, hour, minute, second, 0, 0, -1))
    )
    return unix_timestamp
