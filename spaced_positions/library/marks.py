"""Two marks on positions (GitHub #5, #6): a diagram (an illustration: shown, never trained, may be illegal) and the
`flagged` mark of a puzzle that is broken (`!` in training). `p D` and `!` switch them on and off for the Library's
selection, the open analysis or the puzzle just trained; the Details pane shows both. Each returns its undo."""

from __future__ import annotations

import json

from django.db import transaction
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from spaced_positions import chesslogic
from spaced_positions.core.server_commands import CommandError, command
from spaced_positions.training.models import Position, Puzzle

from .views import objects

MODES = ("toggle", "on", "off")


def _found(body):
    """The selection's objects (never "everything the query finds": a mark is set on what is selected)."""
    collection, ids = body.get("c", "positions"), body.get("ids", [])
    if collection not in ("positions", "puzzles"):
        raise CommandError(_("only positions and puzzles have this mark"))
    if not ids:
        raise CommandError(_("nothing selected"))
    return collection, objects(collection, ids)


def _mode(args) -> str:
    mode = str(args[0]) if args else "toggle"
    if mode not in MODES and mode != "restore":
        raise CommandError(_("on, off or toggle"))
    return mode


def set_diagram(position, on: bool) -> bool:
    """A diagram or not; False when it can't stop being one (an illegal position stays a diagram)."""
    if position.diagram == on:
        return True
    if not on and not chesslogic.check_fen(position.fen)["ok"]:
        return False
    position.diagram = on
    position.save(update_fields=["diagram"])
    if not on:  # a position again: its moves and tags count (detection skips diagrams)
        from spaced_positions.analysis import tree

        from .detect import run as run_detection

        tree.root(position)
        run_detection(position)
    return True


@command("library.diagram")
def diagram(args, context, body):
    """args: toggle (default), on, off; or `restore` with {pk: bool} (the undo)."""
    mode = _mode(args)
    if mode == "restore":
        wanted = {int(pk): on for pk, on in json.loads(args[1]).items()}
    else:
        collection, found = _found(body)
        pks = found.values_list("position_id" if collection == "puzzles" else "pk", flat=True)
        positions = list(Position.objects.filter(pk__in=list(pks)))
        on = mode == "on" or (mode == "toggle" and not all(p.diagram for p in positions))
        wanted = {p.pk: on for p in positions}
    before, refused = {}, 0
    with transaction.atomic():
        for position in Position.objects.filter(pk__in=wanted):
            was = position.diagram
            if set_diagram(position, wanted[position.pk]):
                before[position.pk] = was
            else:
                refused += 1
    if not before:
        raise CommandError(_("not legal: a diagram until the board editor (S) fixes it") if refused else _("nothing selected"))
    on = next(iter(wanted.values()))
    n = len(before)
    if mode == "restore":
        message = _("Diagram mark put back")
    elif on:
        message = ngettext("{n} diagram: shown, not trained", "{n} diagrams: shown, not trained", n).format(n=n)
    else:
        message = ngettext("{n} no longer a diagram: it trains again", "{n} no longer diagrams: they train again", n).format(n=n)
    if refused:
        message += " · " + ngettext("{n} not legal stays a diagram", "{n} not legal stay diagrams", refused).format(n=refused)
    return {
        "message": message,
        "effects": {"library": "changed"},
        "undo": {"command": "library.diagram", "args": ["restore", json.dumps(before)]},
        "redo": {"command": "library.diagram", "args": ["restore", json.dumps({pk: wanted[pk] for pk in before})]},
    }


@command("library.flag")
def flag(args, context, body):
    """args: toggle (default), on, off; or `restore` with {puzzle pk: bool} (the undo). A position's puzzles all."""
    mode = _mode(args)
    if mode == "restore":
        wanted = {int(pk): on for pk, on in json.loads(args[1]).items()}
        puzzles = list(Puzzle.objects.filter(pk__in=wanted))
    else:
        collection, found = _found(body)
        puzzles = list(found if collection == "puzzles" else Puzzle.objects.filter(position__in=found))
        if not puzzles:
            raise CommandError(_("no puzzle here to flag"))
        on = mode == "on" or (mode == "toggle" and not all(p.flagged for p in puzzles))
        wanted = {p.pk: on for p in puzzles}
    before = {p.pk: p.flagged for p in puzzles}
    with transaction.atomic():
        for value in (True, False):
            Puzzle.objects.filter(pk__in=[pk for pk, on in wanted.items() if on is value]).update(flagged=value)
    on = next(iter(wanted.values()))
    if mode == "restore":
        message = _("Flag put back")
    elif on:
        message = _("Flagged as broken: is:flagged in the Library lists it · ! again takes the flag off")
    else:
        message = _("Flag taken off: the puzzle is fine again")
    return {
        "message": message,
        "effects": {"library": "changed"},
        "undo": {"command": "library.flag", "args": ["restore", json.dumps(before)]},
        "redo": {"command": "library.flag", "args": ["restore", json.dumps(wanted)]},
    }
