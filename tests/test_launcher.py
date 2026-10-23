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
