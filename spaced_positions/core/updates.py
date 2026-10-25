"""The opt-in update check (spec 09 §11): with `app.updates` on, the newest release on GitHub is looked up at most once
a day; a newer version shows in the app bar with a link. The request carries nothing but the app's name and version."""

from __future__ import annotations

import json
import time
import urllib.request

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from spaced_positions import SOURCE_URL, __version__

from . import settings as user_settings

LATEST = SOURCE_URL.replace("https://github.com/", "https://api.github.com/repos/") + "/releases/latest"
DAY = 24 * 3600


def version_tuple(text: str) -> tuple:
    return tuple(int(p) for p in "".join(c for c in str(text) if c.isdigit() or c == ".").split(".") if p.isdigit())


def latest(now: float | None = None) -> dict:
    """{version, url} of the newest release (cached a day in the data folder), or {} when it can't be known."""
    now = now or time.time()
    cache = settings.DATA_DIR / "update.json"
    try:
        known = json.loads(cache.read_text())
        if now - known.get("checked", 0) < DAY:
            return known.get("release", {})
    except (OSError, ValueError):
        pass
    try:
        request = urllib.request.Request(LATEST, headers={"Accept": "application/vnd.github+json", "User-Agent": f"SpacedPositions/{__version__}"})
        with urllib.request.urlopen(request, timeout=4) as r:  # noqa: S310 (a fixed https URL)
            data = json.loads(r.read())
        release = {"version": str(data.get("tag_name", "")).lstrip("v"), "url": data.get("html_url", SOURCE_URL)}
    except (OSError, ValueError):
        release = {}
    try:
        cache.write_text(json.dumps({"checked": now, "release": release}))
    except OSError:
        pass
    return release


@require_GET
def check(request):
    """For the app bar: {"available": "0.2.0", "url": …} when a newer version is out (and the check is on)."""
    if not user_settings.get("app.updates"):
        return JsonResponse({"available": None})
    release = latest()
    newer = release.get("version") and version_tuple(release["version"]) > version_tuple(__version__)
    return JsonResponse({"available": release["version"] if newer else None, "url": release.get("url")})
