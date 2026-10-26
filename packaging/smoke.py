"""Smoke test of the built app (release workflow): it starts on a fresh data folder, creates its database, answers,
shows the home page, serves its files under the build's static path, has its translations, the tag vocabulary and
the starter pack, shows the licence notices (every bundled package with its licence text), and stops."""

import json
import re
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
                        info = json.loads(runtime.read_text(encoding="utf-8"))
                        with browser.open(info["url"], timeout=5) as response:
                            html = response.read().decode()
                        break
                    except (OSError, ValueError):
                        pass
                time.sleep(0.2)
            else:
                sys.exit("the app didn't answer within two minutes")
            assert "Spaced Positions" in html, html[:500]
            base = f"http://127.0.0.1:{info['port']}"
            static = re.search(r'src="(/static/[^"]*?)js/app\.js"', html)  # the build's stamped path (settings.STATIC_URL)
            assert static, "no app.js in the page"
            for path in ("js/app.js", "design/commands.json", "vendor/chessground.min.js", "i18n/de.json"):
                with browser.open(f"{base}{static.group(1)}{path}", timeout=5) as response:
                    assert response.status == 200, path
            with browser.open(f"{base}/help/library/", timeout=5) as response:  # a guide: the templates are there
                assert "guide" in response.read().decode()
            with browser.open(urllib.request.Request(f"{base}/home/", headers={"Accept-Language": "de"}), timeout=5) as response:
                assert 'lang="de"' in response.read().decode(), "the German translation is missing"  # locale/ shipped
            with browser.open(f"{base}/lib/complete/?kind=tag&q=fork", timeout=5) as response:
                assert json.loads(response.read())["items"], "no tags: the tag vocabulary is missing"
            with browser.open(f"{base}/settings/", timeout=5) as response:
                csrf = re.search(r'name="csrf-token" content="([^"]+)"', response.read().decode()).group(1)
            starter = urllib.request.Request(f"{base}/packs/starter/", data=b"", method="POST", headers={"X-CSRFToken": csrf})
            with browser.open(starter, timeout=30) as response:
                assert json.loads(response.read())["puzzles"] > 0, "the starter pack is missing"
            with browser.open(f"http://127.0.0.1:{info['port']}/licences/notices.txt", timeout=5) as response:
                notices = response.read().decode()
            for name in ("Django", "waitress", "whitenoise", "platformdirs", "chess", "Python Software Foundation", "GNU GENERAL PUBLIC LICENSE"):
                assert name in notices, f"the notices lack {name}"
            print(f"ok: {info['url'].split('?')[0]}, database {(Path(data) / 'db.sqlite3').stat().st_size // 1024} kB")
        finally:
            subprocess.run([str(APP), "stop", "--data-dir", data], timeout=60)
            server.wait(timeout=30)


if __name__ == "__main__":
    main()
