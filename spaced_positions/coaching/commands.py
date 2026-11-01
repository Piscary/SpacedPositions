"""Lesson commands (spec 17 §2): `:lesson-add Forks` adds the selection (or the open analysis) to a lesson, made when
no lesson has that title; removing an item and its note. Each returns its inverse, so `u` undoes it."""

from __future__ import annotations

import json

from django.db.models import Max
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from spaced_positions.core.server_commands import CommandError, command
from spaced_positions.library.details import subject

from .models import Lesson, LessonItem


def _lesson(name: str) -> Lesson:
    name = name.strip()
    if not name:
        raise CommandError(_("which lesson? :lesson-add Forks"))
    return Lesson.objects.filter(title__iexact=name).first() or Lesson.objects.create(title=name[:120])


@command("lesson.addto")
def add_to(args, context, body):
    """args: the lesson's title, then the refs (p529, g12, an analysis's uuid)."""
    if len(args) < 2:
        raise CommandError(_("nothing selected to add"))
    lesson = _lesson(args[0])
    order = (lesson.items.aggregate(m=Max("order"))["m"] or 0) + 1
    made = []
    for ref in args[1:]:
        collection, obj = subject(ref)
        if obj is None or collection not in ("positions", "games"):
            continue
        field = "position" if collection == "positions" else "game"
        if lesson.items.filter(**{field: obj}).exists():
            continue
        made.append(LessonItem.objects.create(lesson=lesson, order=order, **{field: obj}).pk)
        order += 1
    if not made:
        raise CommandError(_("already in the lesson {title} (or nothing to add)").format(title=lesson.title))
    lesson.save()  # most recent first in the list
    return {
        "message": ngettext("{n} added to the lesson {title}", "{n} added to the lesson {title}", len(made)).format(n=len(made), title=lesson.title),
        "effects": {"lessons": lesson.pk},
        "undo": {"command": "lesson.remove", "args": [json.dumps(made)]},
        "redo": {"command": "lesson.addto", "args": list(args)},
    }


@command("lesson.remove")
def remove(args, context, body):
    """args: a JSON list of item ids (the undo of an add), or one item id."""
    ids = json.loads(args[0]) if args and str(args[0]).startswith("[") else [int(a) for a in args if str(a).isdigit()]
    items = list(LessonItem.objects.filter(pk__in=ids).select_related("lesson", "position", "game"))
    if not items:
        raise CommandError(_("no such item"))
    lesson = items[0].lesson
    refs = [f"p{i.position_id}" if i.position_id else f"g{i.game_id}" for i in items]
    LessonItem.objects.filter(pk__in=ids).delete()
    return {"message": _("Taken out of the lesson {title}").format(title=lesson.title), "effects": {"lessons": lesson.pk},
            "undo": {"command": "lesson.addto", "args": [lesson.title, *refs]}, "redo": {"command": "lesson.remove", "args": [json.dumps(ids)]}}


@command("lesson.note")
def note(args, context, body):
    """args: the item id, then the note (what to ask, what to show)."""
    if not args or not str(args[0]).isdigit():
        raise CommandError(_("which item?"))
    item = LessonItem.objects.filter(pk=int(args[0])).first()
    if item is None:
        raise CommandError(_("no such item"))
    before, item.note = item.note, " ".join(args[1:]).strip()
    item.save(update_fields=["note"])
    return {"message": _("Note saved"), "effects": {"lessons": item.lesson_id},
            "undo": {"command": "lesson.note", "args": [str(item.pk), before]}, "redo": {"command": "lesson.note", "args": list(args)}}
