"""The Settings mode (spec 04 · Settings, 07 §5): one list of sections; every row has its label, its current value,
a short explanation and its `:set` name. Tokens (colours, type, board …) and settings (training, keys, engine …)
side by side; `h l` step a value, `↵` edits it on the command line, `⌫` resets it."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from . import keymap, registry, settings, themes, user_pieces
from .models import LOCAL_USER, KeymapOverride, Preferences

SECTIONS = [
    ("Colours", "c", ["bg", "bg-alt", "surface", "line", "text", "text-sub", "main", "main-text", "good", "bad", "warn", "info", "special"]),
    ("Typography", "y", ["font-ui", "font-mono", "font-moves", "font-size", "type-ratio", "figurines"]),
    ("Density and shape", "d", ["density", "radius", "rule"]),
    ("Board", "b", ["sq-light", "sq-dark", "sq-lastmove", "sq-selected", "sq-check", "sq-hint", "arrow-green", "arrow-red",
                    "arrow-blue", "arrow-yellow", "arrow-engine", "board-border", "board-coords", "piece-set", "board.letters"]),
    ("Sound and motion", "m", ["motion", "board-motion", "sound.on", "display.ticker"]),
    ("Keys", "k", ["keys.keycaps", "keys.teach", "keys.whichkey"]),
    ("Training", "r", ["training.new-per-day", "training.storm-pace"]),
    ("Engine", "e", ["engine.source", "engine.path", "engine.lines", "engine.depth", "engine.arrows", "engine.threads", "engine.hash"]),
    ("Packs", "a", ["packs.author"]),
    ("App", "p", ["app.updates", "app.autostop"]),
]


@dataclass
class Row:
    name: str
    label: str
    help: str
    type: str
    value: object
    default: object
    values: list = field(default_factory=list)
    low: float | None = None
    high: float | None = None
    changed: bool = False
    note: str = ""

    @property
    def shown(self) -> str:
        if isinstance(self.value, bool):
            return "on" if self.value else "off"
        return str(self.value)


def rows() -> list[dict]:
    prefs = Preferences.current()
    schema = registry.themes()["schema"]
    known = themes.all_themes()
    theme_name = prefs.theme if prefs.theme in known else "paper"
    theme_values = known[theme_name]["values"]
    current = theme_values | prefs.tokens
    stored = settings.values(prefs.settings)
    out = []
    for title, key, names in SECTIONS:
        section = []
        for name in names:
            if name in settings.BY_NAME:
                s = settings.BY_NAME[name]
                section.append(Row(name, s.label, s.help, s.type, stored[name], s.default, list(s.values),
                                   s.low if s.type == "int" else None, s.high if s.type == "int" else None,
                                   changed=name in prefs.settings))
            elif name in schema:
                spec = schema[name]
                values = list(spec.get("values") or []) + (list(user_pieces.available()) if name == "piece-set" else [])
                row = Row(name, name.replace("-", " ").capitalize(), spec.get("description", ""), spec["type"], current.get(name),
                          theme_values.get(name), values, spec.get("min"), spec.get("max"), changed=name in prefs.tokens)
                if spec["type"] == "color" and name in ("text", "text-sub", "main", "good", "bad", "warn"):
                    row.note = _contrast_note(name, current)
                section.append(row)
        out.append({"title": title, "key": key, "rows": section})
    return out


def _contrast_note(name: str, values: dict) -> str:
    from spaced_positions.design.check import CONTRAST_RULES, contrast

    for fg, bgs, minimum, _high in CONTRAST_RULES:
        if fg == name:
            try:
                ratio = min(contrast(values[fg], values[bg]) for bg in bgs)
            except (KeyError, ValueError):
                return ""
            return f"{ratio:.1f}:1 {'✓' if ratio >= minimum else f'needs {minimum}:1'}"
    return ""


@require_GET
def settings_rows(request):
    prefs = Preferences.current()
    known = themes.all_themes()
    theme_rows = [{"name": "auto", "label": "Follow the system (Paper / Ink)", "dark": None, "user": False}] + [
        {"name": n, "label": t["label"], "dark": t["dark"], "user": t.get("user", False)} for n, t in known.items()
    ]
    return render(request, "settings/rows.html", {
        "sections": rows(), "themes": theme_rows, "theme": prefs.theme or "auto",
        "overrides": KeymapOverride.objects.filter(user=LOCAL_USER).count(), "csm_path": csm_guess(),
        "custom_css": prefs.settings.get("custom.css", ""),
        "storage": storage(),
        "packs_made": packs_made(), "packs_received": packs_received(), "licences": licences(),
    })


@require_GET
def keymap_rows(request):
    """The keymap editor: every command with its keys (the user's overrides marked)."""
    data = keymap.effective()
    overrides = {(o.context, o.keys): o for o in KeymapOverride.objects.filter(user=LOCAL_USER)}
    keys_of: dict[str, list] = {}
    for context, bindings in data["keymap"].items():
        for seq, b in bindings.items():
            label = seq + (f" ({' '.join(b['args'])})" if b["args"] else "")
            keys_of.setdefault(b["command"], []).append({"seq": seq, "label": label, "context": context, "mine": (context, seq) in overrides})
    unmapped = [o for o in overrides.values() if not o.command]
    commands = sorted(((cid, spec) for cid, spec in data["commands"].items() if not spec.get("hidden")),
                      key=lambda x: (x[1].get("group", ""), x[1]["title"]))
    return render(request, "settings/keymap.html", {
        "rows": [{"id": cid, "title": spec["title"], "group": spec.get("group", ""), "keys": keys_of.get(cid, [])} for cid, spec in commands],
        "unmapped": unmapped,
    })


@require_GET
def export_settings(request):
    from .settings_io import export_toml

    response = HttpResponse(export_toml(), content_type="application/toml; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="spaced-positions-settings.toml"'
    return response


@require_POST
def import_settings(request):
    import json

    from django.http import JsonResponse

    from .settings_io import import_toml

    try:
        text = json.loads(request.body or b"{}").get("text", "")
    except ValueError:
        text = ""
    result = import_toml(str(text))
    return JsonResponse(result, status=200 if result["ok"] else 422)


# ── The user's piece sets (spec 07 §6) ──────────────────────────────────────────────────────────────────────────


@require_GET
def user_pieces_css(request):
    from . import user_pieces

    response = HttpResponse(user_pieces.css(), content_type="text/css; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    return response


@require_GET
def user_piece(request, name, code):
    from django.http import Http404

    from spaced_positions.design import lib

    from . import user_pieces

    if code not in lib.PIECE_CODES or name not in user_pieces.available():
        raise Http404("no such piece")
    response = HttpResponse((user_pieces.folder() / name / f"{code}.svg").read_bytes(), content_type="image/svg+xml")
    response["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"  # an image, nothing more
    response["Cache-Control"] = "no-cache"
    return response


# ── The migration from chess-study-manager (spaced_positions/csm.py) ──────────────────────────────────────────


def csm_guess() -> str:
    """Where an old database probably is: a chess-study-manager folder next to the app or in the home folder."""
    from pathlib import Path

    here = Path(__file__).resolve().parents[2]  # the folder the app is in (the repository, in development)
    for folder in (here.parent, Path.home(), Path.cwd(), Path.cwd().parent):
        candidate = folder / "chess-study-manager" / "db.sqlite3"
        if candidate.is_file():
            return str(candidate)
    return ""


@require_POST
def import_csm(request):
    """{path, dry_run}: run the migration (a real run backs up first) and say what it added."""
    import json

    from django.http import JsonResponse

    from spaced_positions import csm

    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        data = {}
    path, dry_run = str(data.get("path", "")).strip(), bool(data.get("dry_run"))
    if not path:
        return JsonResponse({"ok": False, "message": "the path of the old db.sqlite3"}, status=422)
    try:
        report = csm.run(path, dry_run=dry_run)
    except (FileNotFoundError, ValueError) as e:
        return JsonResponse({"ok": False, "message": str(e)}, status=422)
    what = ", ".join(report.lines()) or "nothing new"
    message = (f"Would add: {what}" if dry_run else f"Added: {what} · backup in {report.backup}")
    return JsonResponse({"ok": True, "dry_run": dry_run, "message": message, "problems": report.problems,
                         "new": sum(report.counts.values()), "effects": {} if dry_run else {"library": "changed"}})


def storage() -> dict:
    """Settings → App: where the data is and how much of it there is."""
    from pathlib import Path

    from django.db import connection

    from spaced_positions import backups

    db = Path(connection.settings_dict["NAME"])
    found = backups.listing(db.parent)
    size = sum(db.parent.joinpath(f"{db.name}{s}").stat().st_size for s in ("", "-wal") if db.parent.joinpath(f"{db.name}{s}").exists())
    return {"folder": str(db.parent), "db_size": size, "backups": len(found), "backups_size": sum(b["size"] for b in found),
            "latest": found[0] if found else None}


def packs_made() -> list:
    """Settings → Packs: the packs you made, each with its export log (spec 09 §12)."""
    from spaced_positions.library.models import Pack

    return list(Pack.objects.prefetch_related("exports"))


def packs_received() -> list:
    from spaced_positions.library.models import ReceivedPack

    return list(ReceivedPack.objects.select_related("source").order_by("-imported_at"))


# Python packages the app runs on (and theirs): name → why it's there. Their licences come from their metadata.
PACKAGES = {"django": "the web framework", "asgiref": "Django's", "sqlparse": "Django's", "waitress": "the server",
            "whitenoise": "static files", "platformdirs": "the data folder", "chess": "python-chess: rules, PGN, engines"}


def licences() -> dict:
    """Settings → Licences (spec 09 §13): the app's own licence and source, and every bundled component."""
    import json
    from importlib import metadata
    from pathlib import Path

    from spaced_positions import SOURCE_URL, __version__

    built = Path(__file__).resolve().parents[1] / "static" / "design" / "licences.json"  # from design/licences.toml (design build)
    data = json.loads(built.read_text()) if built.exists() else {}
    files = [{"name": name, "licence": v.get("licence", ""), "source": v.get("source", "")} for name, v in data.get("vendor", {}).items()]
    pieces = [{"name": v.get("label", name), "licence": v.get("licence", ""), "source": v.get("author", "")} for name, v in data.get("pieces", {}).items()]
    packages = []
    for name, role in PACKAGES.items():
        try:
            m = metadata.metadata(name)
        except metadata.PackageNotFoundError:
            continue
        classifiers = [c.rsplit(" :: ", 1)[-1] for c in m.get_all("Classifier") or [] if c.startswith("License ::")]
        packages.append({"name": f"{m.get('Name')} {m.get('Version')}", "licence": m.get("License-Expression") or m.get("License") or ", ".join(classifiers),
                         "source": role})
    return {"version": __version__, "source": SOURCE_URL, "files": files, "pieces": pieces, "packages": packages}
