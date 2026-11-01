"""Coaching (spec 17): the Lessons and Lesson panes, the homework file, the student's results file, results coming
back, and the homework table."""

from __future__ import annotations

import json
from datetime import date

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from spaced_positions.library.packs import PackError

from . import homework as hw
from .models import Assignment, Homework, Lesson


def _lesson(pk) -> Lesson:
    lesson = Lesson.objects.filter(pk=pk).first()
    if lesson is None:
        raise Http404("no such lesson")
    return lesson


def _file(data: bytes, name: str, content_type: str) -> HttpResponse:
    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    return response


@require_GET
def lessons(request):
    rows = [{"lesson": lesson, "items": lesson.items.count(), "puzzles": len(hw.homework_positions(lesson)),
             "sent": lesson.assignments.count(), "results": sum(hw.HomeworkResult.objects.filter(assignment=str(a.uuid)).count()
                                                                for a in lesson.assignments.all())}
            for lesson in Lesson.objects.all()[:200]]
    return render(request, "coaching/lessons.html", {"rows": rows})


@require_GET
def lesson(request, pk):
    lesson = _lesson(pk)
    items = lesson.items.select_related("position", "game", "position__source")
    latest = lesson.assignments.first()
    return render(request, "coaching/lesson.html", {"lesson": lesson, "items": items,
                                                    "table": hw.table(latest) if latest else None})


@require_GET
def complete(request):
    q = request.GET.get("q", "").strip()
    rows = Lesson.objects.filter(title__icontains=q) if q else Lesson.objects.all()
    return JsonResponse({"items": [{"value": lesson.title, "label": lesson.title} for lesson in rows[:20]]})


@require_GET
def homework_file(request, pk):
    lesson = _lesson(pk)
    due = request.GET.get("due", "")
    try:
        data, name = hw.export(lesson, request.GET.get("text", "").strip(), date.fromisoformat(due) if due else None)
    except (PackError, ValueError) as e:
        return JsonResponse({"ok": False, "message": str(e)}, status=422)
    return _file(data, name, "application/zip")


@require_GET
def homework_cards(request, assignment):
    homework = Homework.objects.filter(assignment=assignment).first()
    if homework is None:
        raise Http404("no such homework")
    return JsonResponse({"cards": hw.cards_of(homework), "title": homework.title, "instructions": homework.instructions})


@require_GET
def results_file(request, assignment):
    """The student's results file (they look at it before they send it, as with the usage report)."""
    homework = Homework.objects.filter(assignment=assignment).first()
    if homework is None:
        raise Http404("no such homework")
    student = (request.GET.get("student") or hw.author() or _("a student")).strip()
    homework.sent_at = timezone.now()
    homework.save(update_fields=["sent_at"])
    data = json.dumps(hw.results(homework, student), ensure_ascii=False, indent=1).encode("utf-8")
    return _file(data, f"results-{homework.title[:40]}-{student[:30]}.spresult", "application/json")


@require_POST
def results_in(request):
    """Results files dropped on the coach's app (the body is the file)."""
    try:
        result = hw.store_results(request.body)
    except ValueError as e:
        return JsonResponse({"ok": False, "message": str(e)}, status=422)
    assignment = Assignment.objects.filter(uuid=result.assignment).first()
    return JsonResponse({"ok": True, "lesson": assignment.lesson_id if assignment else None,
                         "message": _("Results of {student} for {title}").format(student=result.student, title=result.data.get("title", ""))})
