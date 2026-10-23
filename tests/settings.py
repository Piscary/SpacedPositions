"""Test settings: a throw-away data folder, so tests never touch the development or the real database."""

import os
import tempfile

os.environ.setdefault("SPOS_DATA_DIR", tempfile.mkdtemp(prefix="spos-test-"))

from spaced_positions.settings import *  # noqa: E402,F403
