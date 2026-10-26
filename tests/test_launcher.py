"""`spos` end to end: start on a fresh data folder, open with the token, refuse without it, start twice, stop."""

import http.cookiejar
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from spaced_positions import launcher


def test_free_port_skips_busy_ports():
    import socket

    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        port = busy.getsockname()[1]
        with pytest.raises(SystemExit):
            launcher._free_port("127.0.0.1", port)
    assert isinstance(launcher._free_port("127.0.0.1", None), int)


def test_stale_runtime_file_is_ignored(tmp_path):
    (tmp_path / "runtime.json").write_text(json.dumps({"pid": 999999, "port": 1, "url": "x"}), encoding="utf-8")
    assert launcher._running_instance(tmp_path) is None
    assert not (tmp_path / "runtime.json").exists()


def test_a_runtime_file_of_another_program_is_stale(tmp_path):
    """After a crash or a restart the recorded process number may belong to another program (here: the tests): it
    doesn't answer, so the file is stale and the app starts instead of refusing to."""
    (tmp_path / "runtime.json").write_text(json.dumps({"pid": os.getpid(), "port": launcher._free_port("127.0.0.1", None), "url": "x"}),
                                           encoding="utf-8")
    assert launcher._alive(os.getpid())
    assert launcher._running_instance(tmp_path) is None
    assert not (tmp_path / "runtime.json").exists()


def _spos(data, *args, **kwargs):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SPOS_", "DJANGO_"))}
    return subprocess.run(
        [sys.executable, "-m", "spaced_positions", "--data-dir", str(data), *args],
        env=env, capture_output=True, text=True, timeout=30, **kwargs,
    )


def test_start_open_refuse_list_stop(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SPOS_", "DJANGO_"))}
    server = subprocess.Popen(
        [sys.executable, "-m", "spaced_positions", "--no-browser", "--data-dir", str(tmp_path)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        runtime = tmp_path / "runtime.json"
        for _ in range(100):
            if runtime.exists():
                break
            time.sleep(0.1)
        info = json.loads(runtime.read_text(encoding="utf-8"))
        base = f"http://127.0.0.1:{info['port']}"

        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(f"{base}/home/")
        assert refused.value.code == 403

        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        with opener.open(info["url"]) as response:  # ?token= → cookie → redirect to /home/
            assert response.status == 200 and b'id="boot"' in response.read()
        assert (tmp_path / "db.sqlite3").exists()

        again = _spos(tmp_path, "--no-browser")
        assert "Already running" in again.stdout
        assert info["url"] in _spos(tmp_path, "list").stdout

        assert "Stopped" in _spos(tmp_path, "stop").stdout
        server.wait(timeout=10)
        assert not runtime.exists()
    finally:
        if server.poll() is None:
            server.kill()


def test_backups_are_compressed_rotated_and_restore(tmp_path):
    """spec 09 §11: a daily backup (14 kept), one before migrations and imports (5 kept), xz-compressed; restore."""
    import sqlite3

    from spaced_positions import backups

    db = tmp_path / "db.sqlite3"
    con = sqlite3.connect(db)
    con.execute("create table t (x text)")
    con.executemany("insert into t values (?)", [("a fairly repetitive row of text",)] * 5000)
    con.commit()
    con.close()
    first = backups.daily(db)
    assert first.name.endswith(".sqlite3.xz") and first.stat().st_size < db.stat().st_size / 5
    assert backups.daily(db) is None  # one a day
    for i in range(7):
        backups.make(db, "before-migrate", f"2026-01-0{i + 1}_10-00-00")
    names = sorted(p.name for p in (tmp_path / "backups").glob("db-before-migrate-*"))
    assert len(names) == 5 and names[0].startswith("db-before-migrate-2026-01-03")  # the newest five
    con = sqlite3.connect(db)
    con.execute("delete from t")
    con.commit()
    con.close()
    backups.restore(first, db)
    assert sqlite3.connect(db).execute("select count(*) from t").fetchone()[0] == 5000
    assert list((tmp_path / "backups").glob("db-before-restore-*.sqlite3.xz"))  # what was there before is kept


def test_double_click_starts_in_the_background_and_reopens(tmp_path):
    """The installed app's entry (packaging/app.py): the first double click starts the server and returns, the second
    only opens the browser at it; no backup of the empty database on the first start."""
    app = os.path.join(os.path.dirname(__file__), "..", "packaging", "app.py")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SPOS_", "DJANGO_"))} | {
        "SPOS_DATA_DIR": str(tmp_path), "BROWSER": f"{sys.executable} -c \"print('OPEN', '%s')\""}
    try:
        first = subprocess.run([sys.executable, app], env=env, capture_output=True, text=True, timeout=60)
        assert first.returncode == 0, first.stderr
        info = json.loads((tmp_path / "runtime.json").read_text(encoding="utf-8"))
        second = subprocess.run([sys.executable, app], env=env, capture_output=True, text=True, timeout=30)
        assert json.loads((tmp_path / "runtime.json").read_text(encoding="utf-8"))["pid"] == info["pid"]  # the same server
        assert second.returncode == 0 and info["url"] in first.stdout + second.stdout
        assert "is running" in (tmp_path / "app.log").read_text(encoding="utf-8")
        assert not list((tmp_path / "backups").glob("db-before-migrate-*"))
    finally:
        _spos(tmp_path, "stop")


def test_the_package_ships_every_file_it_reads():
    """An installed copy (pipx, the release apps) has the translations and the tag vocabulary: every file in the
    package that isn't Python is matched by pyproject.toml's package-data (a missing locale/ kept the app English)."""
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    package = root / "spaced_positions"
    patterns = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]["package-data"]["spaced_positions"]
    shipped = {p for pattern in patterns for p in package.glob(pattern) if p.is_file()}
    needed = {p for p in package.rglob("*") if p.is_file() and p.suffix not in (".py", ".pyc") and p.name != ".DS_Store"
              and "__pycache__" not in p.parts}
    assert not needed - shipped, sorted(str(p.relative_to(package)) for p in needed - shipped)[:10]
    assert package / "locale" / "de" / "LC_MESSAGES" / "django.mo" in shipped


def test_spos_update_knows_how_this_copy_was_installed(monkeypatch):
    """`spos update` (and the app bar's update notice) follow the way the app was installed."""
    from spaced_positions import install

    def origin(value):
        monkeypatch.setattr(install, "_direct_url", lambda: value)

    origin({"dir_info": {"editable": True}, "url": "file:///src/spaced-positions"})
    assert install.kind() == "source" and install.update_command() is None and "git pull" in install.instructions()
    origin({"dir_info": {}, "url": "file:///Users/me/spaced-positions"})
    monkeypatch.setattr(sys, "prefix", "/usr/local/venv")
    assert install.kind() == "pip"
    assert install.update_command()[-3:] == ["--force-reinstall", "--no-deps", "/Users/me/spaced-positions"]
    origin({"url": "https://github.com/Piscary/SpacedPositions", "vcs_info": {"vcs": "git", "commit_id": "abc"}})
    assert install.update_command()[-2:] == ["--upgrade", "git+https://github.com/Piscary/SpacedPositions"]
    origin({})
    assert install.update_command()[-1] == "spaced-positions"  # from PyPI
    monkeypatch.setattr(sys, "prefix", "/Users/me/.local/pipx/venvs/spaced-positions")
    monkeypatch.setattr(install.shutil, "which", lambda name: "/usr/local/bin/pipx")
    assert install.kind() == "pipx" and install.update_command() == ["/usr/local/bin/pipx", "upgrade", "spaced-positions"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert install.kind() == "app" and install.update_command() is None and "release" in install.instructions().lower()


def test_text_files_are_read_and_written_as_utf8():
    """Windows reads a text file as cp1252 unless told otherwise: the tags, the translations and the catalogues would
    come out garbled there (or a migration fail). Every text read and write in the app names its encoding."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    bad = []
    for path in [*(root / "spaced_positions").rglob("*.py"), *(root / "packaging").glob("*.py")]:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\.read_text\(\)|\.write_text\((?!.*encoding=)", line) or (
                    re.search(r"(?<![\w.])open\((?![^)]*(encoding=|\"[rwa]b\"|'[rwa]b'))", line) and "urlopen" not in line):
                bad.append(f"{path.relative_to(root)}:{n}: {line.strip()}")
    assert not bad, "\n".join(bad)
