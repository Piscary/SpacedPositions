"""Where Spaced Positions keeps its data.

The data folder is never inside the install folder, so reinstalling or updating never touches user data
(spec 09 §11). Development (`manage.py`) uses `<repo>/.data` instead, so working on the app never touches
the real library.
"""

import os
import secrets
import sys
from pathlib import Path

import platformdirs

APP_NAME = "Spaced Positions"


def default_data_dir() -> Path:
    if sys.platform.startswith("linux"):
        return Path(platformdirs.user_data_dir("spaced-positions", appauthor=False))
    return Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))


def data_dir() -> Path:
    """The data folder of this process: `SPOS_DATA_DIR`, else the platform's user-data folder."""
    path = Path(os.environ.get("SPOS_DATA_DIR") or default_data_dir()).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def secret_key() -> str:
    """A per-install secret, created on first start."""
    path = data_dir() / "secret_key"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(50), encoding="utf-8")
        path.chmod(0o600)
    return path.read_text(encoding="utf-8").strip()
