"""Backups of the database (spec 09 §11): a daily one, kept 14 days, and one before every migration or import, the
newest 5 of each kind kept. A backup is SQLite's own consistent copy (also of a database in WAL mode, also while the app
runs), compressed with xz (about a fifth of the size). `spos restore <file>` puts one back."""

from __future__ import annotations

import lzma
import shutil
import sqlite3
import tempfile
from datetime import date, datetime
from pathlib import Path

KEEP = {"daily": 14}
KEEP_OTHER = 5
SUFFIX = ".sqlite3.xz"


def folder(data_dir: Path) -> Path:
    path = Path(data_dir) / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def make(db: Path, label: str, stamp: str | None = None) -> Path:
    """A compressed copy of `db` as backups/db-<label>-<stamp>.sqlite3.xz."""
    db = Path(db)
    stamp = stamp or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target = folder(db.parent) / f"db-{label}-{stamp}{SUFFIX}"
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        copy = Path(tmp) / "copy.sqlite3"
        source = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        dest = sqlite3.connect(copy)
        try:
            source.backup(dest)
        finally:
            dest.close()
            source.close()
        with open(copy, "rb") as raw, lzma.open(target.with_suffix(".tmp"), "wb", preset=1) as packed:
            shutil.copyfileobj(raw, packed, 1 << 20)
        target.with_suffix(".tmp").replace(target)  # complete or not at all
    prune(target.parent)
    return target


def daily(db: Path) -> Path | None:
    """Today's backup, unless there is one already."""
    db = Path(db)
    if not db.exists() or not db.stat().st_size:
        return None
    today = date.today().isoformat()
    if any(folder(db.parent).glob(f"db-daily-{today}*{SUFFIX}")):
        return None
    return make(db, "daily", today)


def kind(path: Path) -> str:
    """'daily', 'before-migrate', 'before-csm' …: the label between db- and the date."""
    name = path.name.removeprefix("db-")
    parts = name.split("-")
    out = []
    for p in parts:
        if p[:4].isdigit():
            break
        out.append(p)
    return "-".join(out)


def prune(directory: Path) -> None:
    """The newest backups of each kind stay (14 daily, 5 of the others); uncompressed old ones are left alone."""
    by_kind: dict[str, list[Path]] = {}
    for path in directory.glob(f"db-*{SUFFIX}"):
        by_kind.setdefault(kind(path), []).append(path)
    for k, paths in by_kind.items():
        for old in sorted(paths, key=lambda p: p.name, reverse=True)[KEEP.get(k, KEEP_OTHER):]:
            old.unlink(missing_ok=True)


def listing(data_dir: Path) -> list[dict]:
    out = []
    for path in sorted(folder(data_dir).glob("db-*"), key=lambda p: p.stat().st_mtime, reverse=True):
        out.append({"name": path.name, "kind": kind(path), "size": path.stat().st_size,
                    "when": datetime.fromtimestamp(path.stat().st_mtime)})
    return out


def restore(backup: Path, db: Path) -> Path:
    """Put a backup back (the app must not be running). The current database is backed up first."""
    backup, db = Path(backup), Path(db)
    if not backup.is_file():
        raise FileNotFoundError(f"{backup} doesn't exist")
    if db.exists():
        make(db, "before-restore")
    tmp = db.with_suffix(".restoring")
    if backup.name.endswith(".xz"):
        with lzma.open(backup, "rb") as packed, open(tmp, "wb") as raw:
            shutil.copyfileobj(packed, raw, 1 << 20)
    else:
        shutil.copyfile(backup, tmp)
    check = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
    try:
        check.execute("pragma quick_check").fetchone()  # a database, readable
    finally:
        check.close()
    for suffix in ("-wal", "-shm"):
        Path(f"{db}{suffix}").unlink(missing_ok=True)
    tmp.replace(db)
    return db


def compact(db: Path) -> None:
    """VACUUM: the space of deleted rows goes back to the disk (after migrations; nothing else may use the file)."""
    con = sqlite3.connect(db)
    try:
        con.execute("VACUUM")
    finally:
        con.close()
