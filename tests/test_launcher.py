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
    (tmp_path / "runtime.json").write_text(json.dumps({"pid": 999999, "port": 1, "url": "x"}))
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
        info = json.loads(runtime.read_text())
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
        info = json.loads((tmp_path / "runtime.json").read_text())
        second = subprocess.run([sys.executable, app], env=env, capture_output=True, text=True, timeout=30)
        assert json.loads((tmp_path / "runtime.json").read_text())["pid"] == info["pid"]  # the same server
        assert second.returncode == 0 and info["url"] in first.stdout + second.stdout
        assert "is running" in (tmp_path / "app.log").read_text()
        assert not list((tmp_path / "backups").glob("db-before-migrate-*"))
    finally:
        _spos(tmp_path, "stop")
