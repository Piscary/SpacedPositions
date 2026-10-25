"""Smoke test of the built app (release workflow): it starts on a fresh data folder, creates its database, answers,
shows the home page and stops."""

import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = {"darwin": ROOT / "dist/Spaced Positions.app/Contents/MacOS/Spaced Positions",
       "win32": ROOT / "dist/Spaced Positions/Spaced Positions.exe"}.get(sys.platform, ROOT / "dist/Spaced Positions/Spaced Positions")


def main():
    browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))  # the token becomes a cookie
    with tempfile.TemporaryDirectory() as data:
        server = subprocess.Popen([str(APP), "start", "--no-browser", "--data-dir", data])
        try:
            runtime = Path(data) / "runtime.json"
            for _ in range(600):
                if server.poll() is not None:
                    sys.exit(f"the app exited with {server.returncode}")
                if runtime.exists():
                    try:
                        info = json.loads(runtime.read_text())
                        with browser.open(info["url"], timeout=5) as response:
                            html = response.read().decode()
                        break
                    except (OSError, ValueError):
                        pass
                time.sleep(0.2)
            else:
                sys.exit("the app didn't answer within two minutes")
            assert "Spaced Positions" in html, html[:500]
            with browser.open(f"http://127.0.0.1:{info['port']}/static/design/commands.json", timeout=5) as response:
                assert response.status == 200
            print(f"ok: {info['url'].split('?')[0]}, database {(Path(data) / 'db.sqlite3').stat().st_size // 1024} kB")
        finally:
            subprocess.run([str(APP), "stop", "--data-dir", data], timeout=60)
            server.wait(timeout=30)


if __name__ == "__main__":
    main()
