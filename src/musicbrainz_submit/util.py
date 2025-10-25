from pathlib import Path

import platformdirs

CONFIG_DIR: Path = Path(platformdirs.user_config_dir("mbmc"))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
