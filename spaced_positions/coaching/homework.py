"""Homework (spec 17 §3–§5): a lesson's puzzles as a pack with a `homework` block in its manifest; the student's
app keeps it as Homework, trains it as a session of its cards, and writes a results file (counts and first tries per
puzzle, nothing else) that the coach imports into the homework's table."""

from __future__ import annotations

import json
from datetime import date

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from spaced_positions.core import settings as user_settings
from spaced_positions.library import packs
from spaced_positions.library.models import Pack
from spaced_positions.training.models import Attempt, Card, Position

from .models import Assignment, Homework, HomeworkResult, Lesson

RESULTS_FORMAT = 1


def author() -> str:
    from spaced_positions.library.models import Player

    me = Player.objects.filter(role="me").first()
    return user_settings.get("packs.author") or (me.name if me else "")


def homework_positions(lesson: Lesson):
    """The lesson's positions that have a puzzle, in the lesson's order."""
    ids = [i.position_id for i in lesson.items.exclude(position=None)]
    found = {p.pk: p for p in Position.objects.filter(pk__in=ids, puzzles__isnull=False, deleted_at=None).distinct()}
    return [found[i] for i in ids if i in found]


def export(lesson: Lesson, instructions: str = "", due: date | None = None) -> tuple[bytes, str]:
    """The homework file of a lesson; each export is a new assignment the results refer to."""
    positions = homework_positions(lesson)
    if not positions:
        raise packs.PackError(_("this lesson has no puzzles: add positions with a puzzle (L in the Library)"))
    if lesson.pack is None:
        lesson.pack = Pack.objects.create(title=lesson.title[:120])
        lesson.save(update_fields=["pack"])
    assignment = Assignment.objects.create(lesson=lesson, title=lesson.title, instructions=instructions, due=due,
                                           positions=[str(p.uuid) for p in positions])
    block = {"homework": {"id": str(assignment.uuid), "title": lesson.title, "instructions": instructions,
                          "due": due.isoformat() if due else "", "positions": assignment.positions}}
    data, _manifest = packs.build(Position.objects.filter(pk__in=[p.pk for p in positions]), lesson.pack, author=author(),
                                  include_received=True, extra=block)
    return data, f"homework-{lesson.title[:40]}-{timezone.localdate().isoformat()}.sppack"


def receive_homework(manifest: dict, report) -> Homework:
    """A pack with a homework block was imported (packs.run): keep the homework for Home."""
    h = manifest["homework"]
    due = h.get("due") or ""
    homework, _created = Homework.objects.update_or_create(assignment=str(h.get("id", ""))[:36], defaults={
        "title": str(h.get("title", ""))[:120], "coach": str(manifest.get("author", ""))[:120],
        "instructions": str(h.get("instructions", "")), "due": date.fromisoformat(due) if due else None,
        "positions": [str(p) for p in h.get("positions", [])][:200],
    })
    return homework


def cards_of(homework: Homework) -> list[str]:
    """The cards of the homework's puzzles, in the coach's order (a puzzle with several answer lines: all its cards)."""
    order = {u: i for i, u in enumerate(homework.positions)}
    cards = Card.objects.filter(puzzle__position__uuid__in=homework.positions, in_solution=True).select_related("puzzle__position")
    return [str(c.uuid) for c in sorted(cards, key=lambda c: (order.get(str(c.puzzle.position.uuid), 0), c.pk))]


def progress(homework: Homework) -> tuple[int, int]:
    """(puzzles tried since it came, puzzles in it)."""
    tried = Attempt.objects.filter(card__puzzle__position__uuid__in=homework.positions, at__gte=homework.received_at,
                                   origin="").values("card__puzzle__position").distinct().count()
    return tried, len(homework.positions)


def results(homework: Homework, student: str) -> dict:
    """What the student sends back: per puzzle the first try (solved or not, time, hint, the wrong move) and how many
    tries; no other training, no other material."""
    items = []
    titles = dict(Position.objects.filter(uuid__in=homework.positions).values_list("uuid", "title"))
    for uid in homework.positions:
        tries = list(Attempt.objects.filter(card__puzzle__position__uuid=uid, at__gte=homework.received_at, origin="").order_by("at"))
        first = tries[0] if tries else None
        items.append({"position": uid, "title": titles.get(uid) or titles.get(_uuid(uid)) or "", "done": bool(first),
                      "first": bool(first and first.success), "tries": len(tries), "solved": any(t.success for t in tries),
                      "ms": first.ms if first else None, "hint": bool(first and first.hinted), "wrong": first.wrong_move if first else ""})
    return {"kind": "results", "format": RESULTS_FORMAT, "homework": homework.assignment, "title": homework.title,
            "student": student, "written": timezone.now().isoformat(), "items": items}


def _uuid(text):
    import uuid

    try:
        return uuid.UUID(text)
    except ValueError:
        return None


@transaction.atomic
def store_results(raw: bytes) -> HomeworkResult:
    """A results file on the coach's side; one per student and homework (a newer file replaces it)."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError(_("not a results file")) from None
    if data.get("kind") != "results" or not data.get("homework") or not str(data.get("student", "")).strip():
        raise ValueError(_("not a results file (no homework or no student)"))
    if data.get("format", 0) > RESULTS_FORMAT:
        raise ValueError(_("these results were written by a newer version of Spaced Positions: update the app"))
    result, _created = HomeworkResult.objects.update_or_create(
        assignment=str(data["homework"])[:36], student=str(data["student"]).strip()[:120],
        defaults={"data": data, "received_at": timezone.now()})
    return result


def table(assignment: Assignment) -> dict:
    """The coach's view of one homework: students × puzzles, a cell per first try; columns sorted by misses."""
    rows = list(HomeworkResult.objects.filter(assignment=str(assignment.uuid)).order_by("student"))
    titles = dict(Position.objects.filter(uuid__in=assignment.positions).values_list("uuid", "title"))
    columns = []
    for i, uid in enumerate(assignment.positions):
        cells = [next((it for it in r.data.get("items", []) if it.get("position") == uid), {}) for r in rows]
        missed = sum(1 for c in cells if c.get("done") and not c.get("first"))
        columns.append({"n": i + 1, "position": uid, "title": titles.get(_uuid(uid)) or titles.get(uid) or "", "missed": missed, "cells": cells})
    columns.sort(key=lambda c: -c["missed"])
    students = [{"name": r.student, "cells": [c["cells"][k] for c in columns]} for k, r in enumerate(rows)]
    return {"assignment": assignment, "columns": columns, "students": students}
