# RockBox DB Py

An implementation of the Rockbox database, in Python.

# Features

 - Multi-threaded indexing of your music collection
   - Should be much faster, especially on large collections, usually less than a
   second per 1000 files.
 - Uses the `mediafile` library to read metadata from files, so it supports
   a wide range of audio formats.
    - Battle tested and used in `beets` and more.
 - Once your media files are indexed, you can make in-memory edits to their tags.
    - I.e. you can change the title, artist, album, etc. of a file, just for
        the Rockbox database, without messing with the actual file.
    - This is REALLY useful for things like the genre, where you can "canonicalize"
        a list of genres to a single genre, significantly reducing the entries
        in the database.

# Current Caveats

There is a few caveats to be aware of, as this is a work in progress:

 - This is a brand new database every time. You aren't keeping around any of
   your stats, ratings, playtimes etc. from the old database.
   - This is mostly a design choice for now...I use last.fm etc to track those
   things, so didn't see the point in trying to keep them around. Some partial
   support may be possible, but I haven't really looked into it yet.

 - The main "build_db.py" script currently assumes a 1:1 mapping between
   the music files on your device and the files in your music collection.
   - I.e. it assumes that if you have a file at "F:/Music/Artist/Album/Song.mp3",
     then that is the same file as "/Music/Artist/Album/Song.mp3" on your device.
   - If you have a more complex setup, you can potentially make changes to the
     `build_db.py` script to handle that, but you will need to have some
     programmatic way to keep the two in sync.

 - There isn't really any extensive testing done yet. I've used it, it works for
   my and my music, but other setups may not work. If you find something that
   doesn't work, please report it as an issue on GitHub, and I will try to fix it.

 - I'm not 100% sure my comment parsing code is working properly. The DB works on
   my iPod Classic 5, but the comments values in some places (even in regular
   Rockbox) are non-sensical. I don't care about comments, so I haven't looked
   into it in a lot of detail, and the DB works fine, so it isn't a priority.

# Installation

Right now....this is a work in progress / proof of concept, so this is really for
developers. I do plan to produce a full, pre-made release with a GUI and all that
but it makes sense to verify the core functionality first.

Before starting, you'll need a Python environment on you machine, and `uv` installed.
Instructions for both of those can be found pretty easily online.

Once you have that, you can setup the project like this:

```bash
git clone https://github.com/CrossR/rockbox_db_py.git
cd rockbox_db_py

# Setup the virtual environment and install the dependencies
uv sync

# Install the current project in editable mode
uv pip install -e .
```

# Usage

Once you have the project setup, the steps are as follows:

1. Backup your existing database, if you have one. Ideally back it up twice!
  - If you don't do this, and the scripts here mess it up, you will lose
    your existing database. That will mean waiting around for Rockbox to
    re-index your music collection, which can take a long time.

2. From the root of the project, run the first debugging script over the
   folder you just backed up your database to:
    ```bash
    uv run python tools/print_db.py "D:\Path\To\Rockbox\db\backup"
    ```
    This won't edit your database, but should print out the first 30 entries.
    If this fails or goes weird...report it as an issue on GitHub, and stop here
    most likely. There is some feature of your current DB that we can't handle,
    so making a new DB will probably also fail. If it did work, you can also
    mess with the other flags (check `print_db.py --help` for details) to print
    other bits of info.

3. If that did work....we can parse your DB! So, let's try something else.
   ```bash
   uv run python tools/copy_db.py "D:\Path\To\Rockbox\db\backup" "D:\Path\To\Rockbox\db\copy"
   ```
   This will fully parse your existing DB to memory, then write it out using the
   python-based Rockbox DB format. Again, if this fails, report it as an issue
   and stop here. You should also be able to run `print_db.py` on the new copy
   to verify that it looks correct.

4. Okay, the final step. My code can somehow parse your existing DB, so
   let's try to make a new one.
   ```bash
   uv run python tools/build_db.py "D:\Media\Music" "/Music/" "D:\Path\To\Rockbox\db\new_db"
   ```
   This command takes 3 arguments:
    - The path to your music collection, which will be indexed.
    - The path to the music collection as it should appear in the Rockbox DB.
      I.e. if when you plugin over USB, your music collection is at "F:/Music",
      then this should be "/Music/". This is used to make the paths in the DB.
    - The folder where to write the new database to. This should be a folder
      that does not already exist, as it will be created.
    You should see a progress bar as your music files are read, and then a brief
    print out of the first music file we parse. After that, the script will
    write out the new database with a second progress bar (though this is
    usually very quick). After that point, you can run `print_db.py` on the new
    database to verify that it looks correct, before actually trying it on your
    device.  I find a reboot of the device after copying is best, just to ensure
    everything is reloaded correctly.
