"""The opt-in update check (spec 09 §11): with `app.updates` on, the newest release on GitHub is looked up at most once
a day; a newer version shows in the app bar with a link. The request carries nothing but the app's name and version."""

from __future__ import annotations

import json
import time
import urllib.request

from django.conf import settings
from django.http import JsonResponse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET

from spaced_positions import SOURCE_URL, __version__

from . import settings as user_settings

# The release list, not /releases/latest: that one skips pre-releases, and test versions are pre-releases (v0.2.0-beta).
RELEASES = SOURCE_URL.replace("https://github.com/", "https://api.github.com/repos/") + "/releases?per_page=10"
DAY = 24 * 3600


def version_tuple(text: str) -> tuple:
    return tuple(int(p) for p in "".join(c for c in str(text) if c.isdigit() or c == ".").split(".") if p.isdigit())


def latest(now: float | None = None) -> dict:
    """{version, url} of the newest release (cached a day in the data folder), or {} when it can't be known."""
    now = now or time.time()
    cache = settings.DATA_DIR / "update.json"
    try:
        known = json.loads(cache.read_text(encoding="utf-8"))
        if now - known.get("checked", 0) < DAY:
            return known.get("release", {})
    except (OSError, ValueError):
        pass
    try:
        request = urllib.request.Request(RELEASES, headers={"Accept": "application/vnd.github+json", "User-Agent": f"SpacedPositions/{__version__}"})
        with urllib.request.urlopen(request, timeout=4) as r:  # noqa: S310 (a fixed https URL)
            data = json.loads(r.read())
        # versions only (v1.2.3, v1.2.3-beta): not drafts, not the rolling "nightly" build of main
        versions = [d for d in data if not d.get("draft") and str(d.get("tag_name", "")).startswith("v")]
        newest = max(versions, key=lambda d: version_tuple(d["tag_name"]), default=None)
        release = {"version": newest["tag_name"].lstrip("v"), "url": newest.get("html_url", SOURCE_URL)} if newest else {}
    except (OSError, ValueError):
        release = {}
    try:
        cache.write_text(json.dumps({"checked": now, "release": release}), encoding="utf-8")
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
    return JsonResponse({"available": release["version"] if newer else None, "url": release.get("url"), "how": how_to_update()})


def how_to_update() -> str:
    """How this copy is updated, for the app bar's notice (install.py knows how it was installed)."""
    from spaced_positions import install

    how = install.kind()
    if how == "app":
        return _("Download the new version from the release page and replace the app: your data stays where it is.")
    if how == "source":
        return _("A development copy: git pull, then start it again.")
    if install.update_command():
        return _("In a terminal: spos update. It stops the app, updates it and starts it again; your data stays.")
    return _("Install the new version the way you installed this one; your data stays where it is.")
