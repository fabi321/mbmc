from pathlib import Path
import atexit
import json

import platformdirs

CONFIG_DIR: Path = Path(platformdirs.user_config_dir("mbmc"))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR: Path = Path(platformdirs.user_cache_dir("mbmc"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

BANNED_ALBUMS_FILE: Path = CONFIG_DIR / "banned_albums.json"
BANNED_ALBUMS_FILE.touch(exist_ok=True)
BANNED_ALBUMS: dict[str, list[str]]

with BANNED_ALBUMS_FILE.open("r") as f:
    try:
        BANNED_ALBUMS = json.load(f)
    except json.JSONDecodeError:
        BANNED_ALBUMS = {}


def exit_handler():
    """Automatically save banned albums on exit."""
    with BANNED_ALBUMS_FILE.open("w") as f:
        json.dump(BANNED_ALBUMS, f, indent=4)


atexit.register(exit_handler)
