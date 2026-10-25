"""The Stats mode (spec 04 · Stats) and the parts of Home that show progress. Sections of charts and numbers built
from metrics.dashboard(); every number drills down somewhere (a Library query or a training session)."""

from __future__ import annotations

import json
from datetime import timedelta

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_GET, require_POST

from spaced_positions.analysis.models import Node
from spaced_positions.core.models import LOCAL_USER, UIState

from . import charts, metrics
from .charts import Chart, Point, Series
from .models import Achievement

PERIODS = {"7d": 7, "30d": 30, "90d": 90, "1y": 365, "all": None}
PERIOD_LABELS = {"7d": gettext_lazy("7 days"), "30d": gettext_lazy("30 days"), "90d": gettext_lazy("90 days"), "1y": gettext_lazy("1 year"),
                 "all": gettext_lazy("all")}


def period_of(request) -> str:
    period = request.GET.get("period")
    if period not in PERIODS:
        state = UIState.objects.filter(user=LOCAL_USER, mode="stats").first()
        period = (state.subject or {}).get("period", "90d") if state else "90d"
    return period if period in PERIODS else "90d"


def _pct(v) -> str:
    return "–" if v is None else f"{round(100 * v)}%"


def _day(d) -> str:
    return date_format(d, "j M")


def _weekday(d) -> str:
    return date_format(d, "D j M")


def sections(period: str = "90d", now=None) -> dict:
    now = now or timezone.now()
    days = PERIODS[period]
    data = metrics.dashboard(now)
    lib, ret, cons, coll = data["library"], data["retention"], data["consistency"], data["collection"]
    span = days or 365

    # Pattern library over time
    history = lib["history"] if days is None else lib["history"][-min(days, len(lib["history"])):]
    library_chart = charts.line(Chart(
        "library", _("Pattern library: mature cards, last {n} days").format(n=span if days else 90),
        [Point(_day(d), [n], _("{day} · {n} mature").format(day=_weekday(d), n=n)) for d, n in history], [Series(_("Mature cards"), "chart-1")],
    ))

    # Card stages per day
    stage_rows = metrics.stage_history(data["_data"], days=min(span, 120))
    stages_chart = charts.bars(Chart(
        "stages", _("Cards by stage, last {n} days").format(n=min(span, 120)),
        [Point(_day(r["day"]), [r["mature"], r["young"], r["learning"], r["new"]],
               _("{day} · mature {mature} · young {young} · learning {learning} · new {new}").format(
                   day=_weekday(r["day"]), mature=r["mature"], young=r["young"], learning=r["learning"], new=r["new"]))
         for r in stage_rows],
        [Series(_("Mature"), "chart-3"), Series(_("Young"), "chart-2"), Series(_("Learning"), "chart-5"), Series(_("New"), "chart-6")],
    ))

    # Activity per week
    weeks = data["activity"] if days is None else data["activity"][-max(2, span // 7):]
    activity_chart = charts.bars(Chart(
        "activity", _("Activity per week: collected, analysed, solved"),
        [Point(_day(w["week"]), [w["collect"], w["analyse"], w["train"]],
               _("week of {day} · collected {collect} · analysed {analyse} · solved {train}").format(
                   day=_day(w["week"]), collect=w["collect"], analyse=w["analyse"], train=w["train"])) for w in weeks],
        [Series(_("Collected"), "chart-2"), Series(_("Analysed"), "chart-4"), Series(_("Solved"), "chart-3")],
    ))
    calendar_chart = charts.heatmap(Chart("calendar", _("Training days: {n} in the last 53 weeks").format(n=data["calendar"]["days"]), []),
                                    data["calendar"]["weeks"])

    # Records
    storm = data["storm"]
    storm_chart = charts.bars(Chart(
        "storm", _("Storm: the last sessions (solved and missed)"),
        [Point(_day(h["at"]), [h["solved"], h["failed"]],
               _("{day} · Storm {minutes}′ · {solved} solved, {failed} missed").format(
                   day=_day(h["at"]), minutes=h["minutes"], solved=h["solved"], failed=h["failed"]))
         for h in storm["history"]],
        [Series(_("Solved"), "good"), Series(_("Missed"), "bad")], empty=_("No Storm yet: ␣ t, then 1."),
    ))

    # Mastery ladder and weak spots
    ladder_rows = sorted((r for r in data["tags"] if r["n"]), key=lambda r: (-r["mastery"]["level"], -r["established"]))[:24]
    ladder = Chart("mastery", _("Mastery per tag"), [
        Point(r["tag"].label, [r["mastery"]["level"]], f"{r['tag'].label} · {r['mastery']['name']}" +
              (" · " + _("next: {what}").format(what=r["mastery"]["next"]) if r["mastery"]["next"] else "")
              + " · " + _("accuracy {rate}").format(rate=_pct(r["accuracy"])),
              drill=f"#{r['tag'].key}") for r in ladder_rows
    ], empty=_("Mastery grows with the cards you train: solve some puzzles first."))
    weak = Chart("weak", _("Weak spots: smoothed accuracy, at least 3 attempts"), [
        Point(r["tag"].label, [round(100 * r["smoothed"])],
              _("{tag} · {rate} of {n} · ↵ Streak on it").format(tag=r["tag"].label, rate=_pct(r["accuracy"]), n=r["n"]),
              drill=f"train:#{r['tag'].key}") for r in data["weakest"]
    ], [Series(_("Smoothed accuracy %"), "bad")], empty=_("No weak spots yet (or not enough attempts)."))

    # Collection
    drills = {"collected": "", "analysed": "has:analysis", "puzzle": "has:puzzle", "training": "has:solution", "mature": "has:solution"}
    funnel = Chart("funnel", _("From collected to mature"), [
        Point(label, [n], f"{label}: {n}", drill=drills.get(key, "")) for key, label, n in coll["funnel"]
    ], [Series(_("Positions"), "chart-1")])
    by_source = Chart("sources", _("Positions by source"), [
        Point(s["source__short"] or s["source__title"], [s["n"]], f"{s['source__short'] or s['source__title']}: {s['n']}",
              drill=f'src:"{s["source__short"] or s["source__title"]}"') for s in coll["by_source"]
    ], [Series(_("Positions"), "chart-2")], empty=_("No sources yet."))
    by_difficulty = charts.bars(Chart("difficulty", _("Positions by difficulty"), [
        Point("★" * d, [n], f"{'★' * d}: {n}", drill=f"diff:{d}") for d, n in coll["by_difficulty"]
    ], [Series(_("Positions"), "chart-5")]))
    fields = [charts.hbars(Chart(f"field-{f['key']}", f["label"], [
        Point(t["tag__name"], [t["n"]], f"{t['tag__name']}: {t['n']}", drill=f"#{t['tag__key']}") for t in f["tags"]
    ], [Series(_("Positions"), "chart-1")])) for f in coll["by_field"]]

    tiles = [
        (_("Positions"), coll["total"], ""), (_("In training"), coll["in_training"], "has:solution"), (_("Games"), coll["games"], "games:"),
        (_("Moves of analysis"), Node.objects.filter(parent__isnull=False, position__deleted_at=None).count(), "has:analysis"),
        (_("Cards"), lib["total"], "puzzles:"), (_("Pattern library"), lib["size"], "puzzles:state:mature"),
        (_("Days in a row"), cons["current"], ""),
    ]
    return {
        "period": period, "periods": list(PERIOD_LABELS.items()), "data": data, "tiles": tiles,
        "library_chart": library_chart, "stages_chart": stages_chart, "activity_chart": activity_chart,
        "calendar_chart": calendar_chart, "storm_chart": storm_chart, "ladder": ladder, "ladder_rows": ladder_rows,
        "levels": [metrics.level_name(i) for i in range(len(metrics.LEVELS))],
        "ladder_points": json.dumps([{"label": p.label, "text": p.text, "drill": p.drill} for p in ladder.points]), "weak_chart": charts.hbars(weak), "funnel_chart": charts.hbars(funnel),
        "source_chart": charts.hbars(by_source), "difficulty_chart": by_difficulty, "field_charts": fields,
        "achievements": Achievement.objects.all()[:30], "retention_rows": [
            (_("Last 7 days"), ret["d7"]), (_("Last 30 days"), ret["d30"]), (_("All"), ret["all"]),
        ],
        "milestone_eta": lib["on_course"],
        "now": now, "weeks_ago": now - timedelta(weeks=53),
    }


@require_GET
def stats_sections(request):
    period = period_of(request)
    return render(request, "stats/sections.html", sections(period))


@require_POST
def seen(request):
    """The achievements not yet announced (status line, Home banner), marked as announced."""
    metrics.sync_achievements()
    rows = list(Achievement.objects.filter(seen=False).order_by("reached_at")[:5])
    Achievement.objects.filter(pk__in=[a.pk for a in rows]).update(seen=True)
    return JsonResponse({"achievements": [{"label": a.text, "kind": a.kind} for a in rows]})
