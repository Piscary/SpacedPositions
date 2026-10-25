"""Puzzle packs in the app (spec 09 §12): `:pack-export` from the Library (the selection or the query), the
download, and the import: the file is uploaded once (`/packs/scan/`), previewed, then imported by its token."""

from __future__ import annotations

import json
import re
import shlex
import time
import uuid
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_GET, require_POST

from spaced_positions.core import settings as user_settings
from spaced_positions.core.server_commands import CommandError, command

from . import packs
from .models import Pack
from .views import objects


def _folder(name: str) -> Path:
    path = Path(settings.DATA_DIR) / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def author_name() -> str:
    from .models import Player

    return user_settings.get("packs.author") or (Player.objects.filter(role="me").values_list("name", flat=True).first() or "")


@command("pack.export")
def pack_export(args, context, body):
    """`:pack-export <title> [for=<student>] [licence="…"] [received]`: the selection (or the query) as a pack file."""
    try:
        words = shlex.split(" ".join(args))
    except ValueError as e:
        raise CommandError(_("unbalanced quotes: {error}").format(error=e)) from None
    options = dict(w.split("=", 1) for w in words if "=" in w)
    title = " ".join(w for w in words if "=" not in w and w != "received").strip()
    if not title:
        raise CommandError(_('a title: :pack-export "Back ranks" for=Ben'))
    collection = body.get("c", "positions")
    if collection not in ("positions", "puzzles", "games"):
        raise CommandError(_("packs hold positions and games: select positions, puzzles or games in the Library"))
    found = objects(collection, body.get("ids", []), body.get("q", ""))
    from spaced_positions.training.models import Position

    from .models import Game

    games = found if collection == "games" else Game.objects.none()
    ids = Position.objects.none().values("pk") if collection == "games" else found.values("pk") if collection == "positions" else found.values("position_id")
    pack, _made = Pack.objects.get_or_create(title=title[:120])
    if "licence" in options:
        pack.licence = options["licence"][:300]
    pack.query = body.get("q", "")[:500]
    pack.save()
    try:
        data, manifest = packs.build(Position.objects.filter(pk__in=ids), pack, author=author_name(), student=options.get("for", "")[:120],
                                     include_received="received" in words, games=games)
    except packs.PackError as e:
        raise CommandError(str(e)) from None
    name = f"{slugify(title) or 'pack'}-v{manifest['version']}" + (f"-for-{slugify(manifest['for'])}" if manifest.get("for") else "") + packs.SUFFIX
    (_folder("exports") / name).write_bytes(data)
    who = " " + _("for {name}").format(name=manifest["for"]) if manifest.get("for") else ""
    parts = [ngettext("{n} position", "{n} positions", manifest["positions"]).format(n=manifest["positions"]),
             ngettext("{n} puzzle", "{n} puzzles", manifest["puzzles"]).format(n=manifest["puzzles"])]
    if manifest.get("games"):
        parts.append(ngettext("{n} game", "{n} games", manifest["games"]).format(n=manifest["games"]))
    return {"message": _("Pack {title} v{version}{who}: {contents}, {size} kB (exports/{name})").format(
                title=title, version=manifest["version"], who=who, contents=", ".join(parts), size=f"{len(data) / 1024:.0f}", name=name),
            "effects": {"download": f"/packs/download/{name}", "storage": True}}


@require_GET
def download(request, name):
    path = _folder("exports") / name
    if not re.fullmatch(r"[a-z0-9-]+\.sppack", name) or not path.is_file():
        raise Http404("no such pack file")
    return FileResponse(open(path, "rb"), as_attachment=True, filename=name, content_type="application/zip")


@require_POST
def scan_view(request):
    """The pack file as the request body: kept under a token (an hour at most) and previewed."""
    data = request.body
    try:
        preview = packs.scan(data)
    except packs.PackError as e:
        return JsonResponse({"ok": False, "message": str(e)}, status=422)
    token = uuid.uuid4().hex
    folder = _folder("imports")
    for old in folder.glob("*.sppack"):  # earlier previews that weren't imported
        if old.stat().st_mtime < time.time() - 3600:
            old.unlink(missing_ok=True)
    (folder / f"{token}.sppack").write_bytes(data)
    return JsonResponse({"ok": True, "token": token, **preview})


@require_POST
def run_view(request):
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        body = {}
    token = str(body.get("token", ""))
    path = _folder("imports") / f"{token}.sppack"
    if not re.fullmatch(r"[0-9a-f]{32}", token) or not path.is_file():
        return JsonResponse({"ok": False, "message": _("the preview has expired: open the pack again")}, status=422)
    try:
        report = packs.run(path.read_bytes(), ready=bool(body.get("ready", True)))
    except packs.PackError as e:
        return JsonResponse({"ok": False, "message": str(e)}, status=422)
    finally:
        path.unlink(missing_ok=True)
    c = report.counts
    parts = [_("{n} new").format(n=c["new"]), _("{n} updated").format(n=c["updated"]) if c["updated"] else "",
             ngettext("{n} puzzle", "{n} puzzles", c["puzzles"]).format(n=c["puzzles"]) if c["puzzles"] else "",
             ngettext("{n} game", "{n} games", c["games"]).format(n=c["games"]) if c["games"] else "",
             _("{n} already here").format(n=c["duplicate"]) if c["duplicate"] else "",
             _("{n} could not be read").format(n=c["failed"]) if c["failed"] else ""]
    source = report.source
    return JsonResponse({"ok": True, "message": _("Pack {title}: {contents}").format(title=source.title, contents=", ".join(p for p in parts if p)),
                         "problems": report.problems,
                         "query": f'src:s{source.pk}', "effects": {"library": "changed"}})
