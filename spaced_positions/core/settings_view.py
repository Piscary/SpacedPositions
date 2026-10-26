"""The Settings mode (spec 04 · Settings, 07 §5): one list of sections; every row has its label, its current value,
a short explanation and its `:set` name. Tokens (colours, type, board …) and settings (training, keys, engine …)
side by side; `h l` step a value, `↵` edits it on the command line, `⌫` resets it."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.http import HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _t
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_POST

from . import keymap, registry, settings, themes, user_pieces
from .i18n_names import token_label
from .models import LOCAL_USER, KeymapOverride, Preferences

# The order is how often people change things: the language first (the first thing someone looks for), then what
# changes while working (board, engine, training), then the look, and last what is set once and forgotten. "theme"
# is the theme list (templates/settings/rows.html); Data, Advanced and Licences follow these.
SECTIONS = [
    (_("Language"), "n", ["ui.language", "tags.language"]),
    (_("Board"), "b", ["piece-set", "board-coords", "board.letters", "board-border"]),
    (_("Engine"), "e", ["engine.source", "engine.path", "engine.lines", "engine.depth", "engine.arrows", "engine.threads", "engine.hash"]),
    (_("Training"), "r", ["training.new-per-day", "training.storm-pace"]),
    (_("Theme"), "t", "theme"),
    (_("Sound and motion"), "m", ["sound.on", "display.ticker", "motion", "board-motion"]),
    (_("Keys"), "k", ["keys.keycaps", "keys.teach", "keys.whichkey"]),
    (_("Typography"), "y", ["font-ui", "font-mono", "font-moves", "font-size", "type-ratio", "figurines"]),
    (_("Density and shape"), "d", ["density", "radius", "rule"]),
    (_("Colours"), "c", ["bg", "bg-alt", "surface", "line", "text", "text-sub", "main", "main-text", "good", "bad", "warn", "info", "special"]),
    (_("Board colours"), "o", ["sq-light", "sq-dark", "sq-lastmove", "sq-selected", "sq-check", "sq-hint", "arrow-green", "arrow-red",
                               "arrow-blue", "arrow-yellow", "arrow-engine"]),
    (_("Packs"), "a", ["packs.author"]),
    (_("App"), "p", ["app.updates", "app.autostop"]),
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

    @property
    def options(self) -> list[tuple[str, str]]:
        """(value, label) of an enum's values."""
        return [(str(v), settings.value_label(v)) for v in self.values]


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
        if names == "theme":
            out.append({"title": title, "key": key, "theme": True, "rows": []})
            continue
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
                row = Row(name, _t(token_label(name)), _t(spec["description"]) if spec.get("description") else "", spec["type"], current.get(name),
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
            return f"{ratio:.1f}:1 ✓" if ratio >= minimum else _t("{ratio}:1, needs {minimum}:1").format(ratio=f"{ratio:.1f}", minimum=minimum)
    return ""


@require_GET
def settings_rows(request):
    prefs = Preferences.current()
    known = themes.all_themes()
    theme_rows = [{"name": "auto", "label": _t("Follow the system (Paper / Ink)"), "dark": None, "user": False}] + [
        {"name": n, "label": t["label"], "dark": t["dark"], "user": t.get("user", False)} for n, t in known.items()
    ]
    return render(request, "settings/rows.html", {
        "sections": rows(), "themes": theme_rows, "theme": prefs.theme or "auto",
        "overrides": KeymapOverride.objects.filter(user=LOCAL_USER).count(),
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
        "rows": [{"id": cid, "title": _t(spec["title"]), "group": _t(spec["group"]) if spec.get("group") else "", "keys": keys_of.get(cid, [])}
                 for cid, spec in commands],
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


def storage() -> dict:
    """Settings → App: where the data is and how much of it there is."""
    from pathlib import Path

    from django.db import connection

    from spaced_positions import backups

    db = Path(connection.settings_dict["NAME"])
    found = backups.listing(db.parent)
    size = sum(db.parent.joinpath(f"{db.name}{s}").stat().st_size for s in ("", "-wal") if db.parent.joinpath(f"{db.name}{s}").exists())
    latest = found[0] | {"kind": str(BACKUP_KINDS.get(found[0]["kind"], found[0]["kind"]))} if found else None
    return {"folder": str(db.parent), "db_size": size, "backups": len(found), "backups_size": sum(b["size"] for b in found),
            "latest": latest}


BACKUP_KINDS = {"daily": _("daily"), "before-migrate": _("before an update"), "before-restore": _("before a restore"), "now": _("by hand")}


def packs_made() -> list:
    """Settings → Packs: the packs you made, each with its export log (spec 09 §12)."""
    from spaced_positions.library.models import Pack

    return list(Pack.objects.prefetch_related("exports"))


def packs_received() -> list:
    from spaced_positions.library.models import ReceivedPack

    return list(ReceivedPack.objects.select_related("source").order_by("-imported_at"))


# Python packages the app runs on (and theirs): name → why it's there. Their licences come from their metadata.
PACKAGES = {"django": _("the web framework"), "asgiref": _("part of Django"), "sqlparse": _("part of Django"), "waitress": _("the server"),
            "whitenoise": _("static files"), "platformdirs": _("the data folder"), "chess": _("python-chess: rules, PGN, engines")}


def licences() -> dict:
    """Settings → Licences (spec 09 §13): the app's own licence and source, and every bundled component."""
    import json
    from importlib import metadata
    from pathlib import Path

    from spaced_positions import SOURCE_URL, __version__

    built = Path(__file__).resolve().parents[1] / "static" / "design" / "licences.json"  # from design/licences.toml (design build)
    data = json.loads(built.read_text()) if built.exists() else {}
    files = [{"name": name, "licence": v.get("licence", ""), "source": v.get("source", "")}
             for table in ("vendor", "data") for name, v in data.get(table, {}).items()]
    pieces = [{"name": v.get("label", name), "licence": v.get("licence", ""), "source": v.get("author", "")} for name, v in data.get("pieces", {}).items()]
    packages = []
    for name, role in PACKAGES.items():
        try:
            m = metadata.metadata(name)
        except metadata.PackageNotFoundError:
            continue
        classifiers = [c.rsplit(" :: ", 1)[-1] for c in m.get_all("Classifier") or [] if c.startswith("License ::")]
        packages.append({"name": f"{m.get('Name')} {m.get('Version')}", "licence": m.get("License-Expression") or m.get("License") or ", ".join(classifiers),
                         "source": str(role)})
    return {"version": __version__, "source": SOURCE_URL, "files": files, "pieces": pieces, "packages": packages}


def _python_licence() -> str:
    """The Python runtime's licence: next to the standard library, or bundled with the double-click app."""
    import sys
    from pathlib import Path

    for path in (Path(sys.base_prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "LICENSE.txt",
                 Path(sys.base_prefix) / "LICENSE.txt", Path(__file__).resolve().parents[1] / "static" / "licences" / "LICENSE.txt"):  # the app (packaging/spos.spec)
        if path.is_file():
            return path.read_text(errors="replace")
    return "Python Software Foundation License Version 2: https://docs.python.org/3/license.html"


def notices_text() -> str:
    """Every licence text the app has to pass on (GPL §4–6, the BSD/MIT/ZPL notices): the app's own licence and where
    its source is, the vendored files, the piece sets, the Python packages and Python itself."""
    import json
    import re
    import sys
    from importlib import metadata
    from pathlib import Path

    from spaced_positions import SOURCE_URL, __version__

    static = Path(__file__).resolve().parents[1] / "static"
    rule = "\n" + "=" * 100 + "\n"
    out = [
        f"Spaced Positions {__version__}\n\nFree software under the GNU General Public License, version 3 or later (the full text "
        f"follows at the end). The source of this version: {SOURCE_URL}/tree/v{__version__} (all versions: {SOURCE_URL}).\n"
        "The double-click apps are built from it with PyInstaller (packaging/ in the source).\n\n"
        "Bundled with it: the components below, each under its own licence. The GPL components' sources are where their "
        "entries say (chessground and stockfish.js at the versions named; python-chess on PyPI; the piece sets are SVG, "
        "their own source).",
    ]
    gpl = (static / "licences" / "GPL-3.0.txt").read_text()

    def licence_text(text: str) -> str:
        """A licence file, unless it is the GPL version 3 again (once, at the end)."""
        if " ".join(text.split())[:300] == " ".join(gpl.split())[:300]:
            return "(the GNU General Public License, version 3: the full text is at the end)"
        return text

    data = json.loads((static / "design" / "licences.json").read_text()) if (static / "design" / "licences.json").exists() else {}
    for name, v in data.get("vendor", {}).items():
        text = f"{name}\nLicence: {v.get('licence', '')}\nSource: {v.get('source', '')}"
        for file in re.findall(r"licences/(\S+)", v.get("source", "")):
            if (static / "vendor" / "licences" / file).is_file():
                text += "\n\n" + licence_text((static / "vendor" / "licences" / file).read_text(errors="replace"))
        out.append(text)
    for name, v in data.get("pieces", {}).items():
        out.append(f"Piece set {v.get('label', name)} by {v.get('author', '')}\nLicence: {v.get('licence', '')}\nSource: {v.get('source', '')}")
    for name in PACKAGES:
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        text = f"{dist.metadata['Name']} {dist.version}\nLicence: {dist.metadata.get('License-Expression') or dist.metadata.get('License') or ''}"
        for f in dist.files or []:
            if "dist-info" in str(f) and any(word in str(f).upper() for word in ("LICEN", "COPYING", "NOTICE", "AUTHORS")):
                try:
                    text += f"\n\n--- {Path(str(f)).name} ---\n" + licence_text(Path(dist.locate_file(f)).read_text(errors="replace"))
                except OSError:
                    continue
        out.append(text)
    out.append(f"Python {sys.version.split()[0]}\n\n" + _python_licence())
    out.append("GNU General Public License, version 3\n\n" + gpl)
    return rule.join(out) + "\n"


@require_GET
def notices(request):
    return HttpResponse(notices_text(), content_type="text/plain; charset=utf-8")
