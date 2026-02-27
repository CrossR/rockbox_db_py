# Rockbox Sync Helper

This is a pretty simple sync GUI, that is useful for keeping two directories in sync.
Rather than using `rsync` (which is a pain on Windows), this simply uses
built-in Python libraries to copy files from one directory to another.

To help keep things in sync, we also write a `.sync` database file in the remote directory.
That lets us keep track of when files were last copied, to update them only when necessary.

Once the files are copied over, we also update the Rockbox database, such that your
new music files are instantly available on your Rockbox device, without needing to wait for the
Rockbox database to re-index your music collection.

# TODO

 - Tidy up the UI and code, check the name etcetc.
