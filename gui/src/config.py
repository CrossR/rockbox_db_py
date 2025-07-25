# General configuration for the GUI
import os
import json

from dataclasses import dataclass, field

# Which file extensions to track for syncing
FILES_TO_TRACK = [
    ".mp3",
    ".flac",
    ".png",
    ".jpg",
    ".jpeg",
]

# Define the user config object
@dataclass
class UserConfig:
    """Configuration for the user interface"""
    input_folder: str = ""
    output_folder: str = ""
    db_file: str = ""
    extensions_to_track: list[str] = field(default_factory=lambda: FILES_TO_TRACK)
    sync_db_path: str = ".sync/sync_helper.db"

def get_config_path() -> str:
    """
        Get the most appropriate config path, depending on the platform.

        Returns:
            str: The path to the config file.
    """

    platform = os.name


    if platform == "nt":  # Windows
        target_dir = os.getenv("APPDATA", os.path.expanduser("~\\AppData\\Roaming"))
    elif platform == "posix" and not os.getenv("XDG_CONFIG_HOME"):
        target_dir = os.path.join(os.path.expanduser("~"), ".config")
    elif platform == "posix" and os.getenv("XDG_CONFIG_HOME"):
        target_dir = os.getenv("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    else:
        raise RuntimeError(f"Unsupported platform: {platform}")

    return os.path.join(target_dir, "rockbox_db_py", "config.json")

def get_user_config() -> UserConfig:
    """
        Load the user configuration from the config file.

        Returns:
            UserConfig: The loaded user configuration.
    """
    config_path = get_config_path()

    if not os.path.exists(config_path):
        return UserConfig()

    with open(config_path, "r") as f:
        data = json.load(f)

    return UserConfig(**data)


def save_user_config(config: UserConfig) -> None:
    """
        Save the user configuration to the config file.

        Args:
            config (UserConfig): The configuration to save.
    """
    config_path = get_config_path()
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    with open(config_path, "w") as f:
        json.dump(config.__dict__, f, indent=4)


