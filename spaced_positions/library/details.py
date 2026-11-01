"""The Details pane (spec 16): the fields of one game, position, player or source as rows, edited with `:edit`
(library/edit.py), so every change has its undo. The pane follows its link group's subject: the Library row under
the cursor or the open analysis."""

from __future__ import annotations

import re

from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET

from spaced_positions.training.models import Position

from .edit import FIELDS
from .models import Game, Player, Source

UUID = re.compile(r"^[0-9a-f-]{36}$")


def subject(ref: str):
    """(collection, object) for `g12`, `p529`, `@tal`, `s3` or an analysis's uuid; (None, None) for anything else."""
    ref = (ref or "").strip()
    if ref.startswith("@"):
        return "players", Player.objects.filter(key=ref[1:]).first()
    if ref[:1] in "gps" and ref[1:].isdigit():
        collection, model = {"g": ("games", Game), "p": ("positions", Position), "s": ("sources", Source)}[ref[0]]
        return collection, model.objects.filter(pk=int(ref[1:])).first()
    if UUID.match(ref):
        game = Game.objects.filter(uuid=ref).first()
        return ("games", game) if game else ("positions", Position.objects.filter(uuid=ref).first())
    return None, None


def ref_of(collection: str, obj) -> str:
    return f"@{obj.key}" if collection == "players" else {"games": "g", "positions": "p", "sources": "s"}[collection] + str(obj.pk)


LABELS = {
    "white": _("White"), "black": _("Black"), "white-elo": _("White Elo"), "black-elo": _("Black Elo"), "result": _("Result"),
    "date": _("Date"), "event": _("Event"), "site": _("Site"), "round": _("Round"), "eco": "ECO", "annotator": _("Annotator"),
    "source": _("Source"), "notes": _("Notes"), "title": _("Title"), "page": _("Page"), "diagram": _("Diagram number"),
    "objective": _("Objective"), "difficulty": _("Difficulty (1–5)"), "name": _("Name"), "key": _("Key (@ in queries)"),
    "aliases": _("Other names and handles"), "role": _("Role"), "federation": _("Federation"), "fide": _("FIDE id"),
    "born": _("Born"), "short": _("Short citation"), "kind": _("Kind"), "authors": _("Authors"), "year": _("Year"),
    "publisher": _("Publisher"), "isbn": "ISBN", "url": _("Web address"),
}
NOUNS = {"games": _("Game"), "positions": _("Position"), "players": _("Player"), "sources": _("Source")}


def _shown(obj, attr: str, kind: str) -> str:
    value = getattr(obj, attr)
    if value is None:
        return ""
    if kind == "player":
        return f"{value.name} @{value.key}"
    if kind == "source":
        return str(value)
    if kind == "list":
        return ", ".join(value)
    if kind == "choice":
        return str(dict(type(obj)._meta.get_field(attr).choices).get(value, value))
    return str(value)


def _raw(obj, attr: str, kind: str) -> str:
    """The value as `:edit` takes it back (for the command line's start text)."""
    value = getattr(obj, attr)
    if value is None:
        return ""
    if kind == "player":
        return f"@{value.key}"
    if kind == "source":
        return f"s{value.pk}"
    return ", ".join(value) if kind == "list" else str(value)


@require_GET
def details(request):
    collection, obj = subject(request.GET.get("ref", ""))
    if obj is None:
        return render(request, "library/details.html", {"obj": None})
    rows = [{"field": name, "label": LABELS.get(name, name), "value": _shown(obj, attr, kind), "raw": _raw(obj, attr, kind),
             "kind": kind} for name, (attr, kind) in FIELDS[collection].items() if not (collection == "players" and name == "key")]
    if collection == "positions":  # the marks (GitHub #5, #6): switches, ↵ or a click turns them on and off
        rows.append({"field": "is-diagram", "label": _("Only a diagram (not trained)"), "on": obj.diagram, "kind": "toggle",
                     "cmd": "library.diagram"})
        if obj.puzzles.exists():
            rows.append({"field": "is-flagged", "label": _("Flagged as broken"), "on": obj.puzzles.filter(flagged=True).exists(),
                         "kind": "toggle", "cmd": "library.flag"})
    missing = collection == "games" and not (obj.white_id or obj.black_id)
    return render(request, "library/details.html", {
        "obj": obj, "ref": ref_of(collection, obj), "noun": NOUNS[collection], "title": getattr(obj, "title", "") or str(obj),
        "rows": rows, "missing": missing,
    })
