"""Test settings: a throw-away data folder, so tests never touch the development or the real database."""

import os
import tempfile

os.environ.setdefault("SPOS_DATA_DIR", tempfile.mkdtemp(prefix="spos-test-"))

from spaced_positions.settings import *  # noqa: E402,F403

# A file database (not :memory:), so the live server's request threads each get their own SQLite connection, as in
# the real app. An in-memory test database is shared between threads, and concurrent requests (many MiniBoards at
# once) then corrupt each other.
DATABASES["default"]["TEST"] = {"NAME": str(DATA_DIR / "test.sqlite3")}  # noqa: F405

if os.environ.get("SPOS_TEST_JITTER"):
    MIDDLEWARE = ["tests.jitter.jitter", *MIDDLEWARE]  # noqa: F405
