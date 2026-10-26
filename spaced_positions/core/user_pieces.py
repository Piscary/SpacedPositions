"""Piece sets of the user's own (spec 07 §6): `<data folder>/pieces/<name>/` with the 12 pieces (`wK.svg` … `bP.svg`)
and, if wanted, an `about.toml` (`label`, `author`, `licence`). They stay in the data folder, are never part of the
app, and are checked like the bundled sets: all 12 pieces, no scripts, no external references."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from django.utils.translation import gettext as _

from spaced_positions import paths
from spaced_positions.design import lib

NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
UNSAFE = re.compile(r"<script|javascript:|\bon[a-z]+\s*=|<foreignObject|href=\"(?!#)|<!ENTITY", re.I)
MAX_BYTES = 300_000  # a piece


def folder() -> Path:
    return paths.data_dir() / "pieces"


def problems_of(set_dir: Path) -> list[str]:
    out = []
    missing = [code for code in lib.PIECE_CODES if not (set_dir / f"{code}.svg").is_file()]
    if missing:
        out.append(_("missing {value}").format(value=', '.join(missing)))
    for code in lib.PIECE_CODES:
        svg = set_dir / f"{code}.svg"
        if svg.is_file() and (svg.stat().st_size > MAX_BYTES or UNSAFE.search(svg.read_text(errors="replace"))):
            out.append(_("{code}.svg: too large, or scripts or external references").format(code=code))
    return out


def available() -> dict[str, dict]:
    """The usable sets of the data folder: {name: {label, author, licence, user}}; bundled names win."""
    from . import registry

    bundled = registry.themes().get("pieces", {})
    out = {}
    base = folder()
    for set_dir in sorted(base.iterdir()) if base.is_dir() else []:
        if not set_dir.is_dir() or not NAME.fullmatch(set_dir.name) or set_dir.name in bundled or problems_of(set_dir):
            continue
        about = {}
        if (set_dir / "about.toml").is_file():
            try:
                about = tomllib.loads((set_dir / "about.toml").read_text(encoding="utf-8"))
            except (tomllib.TOMLDecodeError, UnicodeDecodeError):
                about = {}
        out[set_dir.name] = {"label": str(about.get("label") or set_dir.name.replace("-", " ").title())[:40],
                             "author": str(about.get("author") or _("yours"))[:60],
                             "licence": str(about.get("licence") or _("your own"))[:40], "user": True}
    return out


def all_sets() -> dict[str, dict]:
    from . import registry

    return registry.themes().get("pieces", {}) | available()


def css() -> str:
    """The chessground rules for the user's sets, like the generated pieces.css."""
    lines = ["@layer base {"]
    for name in available():
        for code in lib.PIECE_CODES:
            color = "white" if code[0] == "w" else "black"
            lines.append(f'  :root[data-pieces="{name}"] .cg-wrap piece.{lib.ROLES[code[1]]}.{color} {{ background-image: url("/pieces/{name}/{code}.svg"); }}')
    lines.append("}")
    return "\n".join(lines) + "\n"


def validate_token(schema: dict, name: str, value):
    """lib.validate_token, with the user's sets allowed for `piece-set`."""
    if name == "piece-set" and str(value) in available():
        return str(value), None
    return lib.validate_token(schema, name, value)
