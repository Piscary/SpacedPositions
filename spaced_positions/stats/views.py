"""The Stats mode (spec 04 · Stats) and the parts of Home that show progress. Sections of charts and numbers built
from metrics.dashboard(); every number drills down somewhere (a Library query or a training session)."""

from __future__ import annotations

import json
from datetime import timedelta

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from spaced_positions.analysis.models import Node
from spaced_positions.core.models import LOCAL_USER, UIState

from . import charts, metrics
from .charts import Chart, Point, Series
from .models import Achievement

PERIODS = {"7d": 7, "30d": 30, "90d": 90, "1y": 365, "all": None}


def period_of(request) -> str:
    period = request.GET.get("period")
    if period not in PERIODS:
        state = UIState.objects.filter(user=LOCAL_USER, mode="stats").first()
        period = (state.subject or {}).get("period", "90d") if state else "90d"
    return period if period in PERIODS else "90d"


def _pct(v) -> str:
    return "–" if v is None else f"{round(100 * v)}%"


def sections(period: str = "90d", now=None) -> dict:
    now = now or timezone.now()
    days = PERIODS[period]
    data = metrics.dashboard(now)
    lib, ret, cons, coll = data["library"], data["retention"], data["consistency"], data["collection"]
    span = days or 365

    # Pattern library over time
    history = lib["history"] if days is None else lib["history"][-min(days, len(lib["history"])):]
    library_chart = charts.line(Chart(
        "library", f"Pattern library: mature cards, last {span if days else 90} days",
        [Point(f"{d:%d %b}", [n], f"{d:%a %d %b} · {n} mature") for d, n in history], [Series("Mature cards", "chart-1")],
    ))

    # Card stages per day
    stage_rows = metrics.stage_history(data["_data"], days=min(span, 120))
    stages_chart = charts.bars(Chart(
        "stages", f"Cards by stage, last {min(span, 120)} days",
        [Point(f"{r['day']:%d %b}", [r["mature"], r["young"], r["learning"], r["new"]],
               f"{r['day']:%a %d %b} · mature {r['mature']} · young {r['young']} · learning {r['learning']} · new {r['new']}")
         for r in stage_rows],
        [Series("Mature", "chart-3"), Series("Young", "chart-2"), Series("Learning", "chart-5"), Series("New", "chart-6")],
    ))

    # Activity per week
    weeks = data["activity"] if days is None else data["activity"][-max(2, span // 7):]
    activity_chart = charts.bars(Chart(
        "activity", "Activity per week: collected, analysed, solved",
        [Point(f"{w['week']:%d %b}", [w["collect"], w["analyse"], w["train"]],
               f"week of {w['week']:%d %b} · collected {w['collect']} · analysed {w['analyse']} · solved {w['train']}") for w in weeks],
        [Series("Collected", "chart-2"), Series("Analysed", "chart-4"), Series("Solved", "chart-3")],
    ))
    calendar_chart = charts.heatmap(Chart("calendar", f"Training days: {data['calendar']['days']} in the last 53 weeks", []),
                                    data["calendar"]["weeks"])

    # Records
    storm = data["storm"]
    storm_chart = charts.bars(Chart(
        "storm", "Storm: the last sessions (solved and missed)",
        [Point(f"{h['at']:%d %b}", [h["solved"], h["failed"]], f"{h['at']:%d %b} · Storm {h['minutes']}′ · {h['solved']} solved, {h['failed']} missed")
         for h in storm["history"]],
        [Series("Solved", "good"), Series("Missed", "bad")], empty="No Storm yet: ␣ t, then 1.",
    ))

    # Mastery ladder and weak spots
    ladder_rows = sorted((r for r in data["tags"] if r["n"]), key=lambda r: (-r["mastery"]["level"], -r["established"]))[:24]
    ladder = Chart("mastery", "Mastery per tag", [
        Point(r["tag"].name, [r["mastery"]["level"]], f"{r['tag'].name} · {r['mastery']['name']}" +
              (f" · next: {r['mastery']['next']}" if r["mastery"]["next"] else "") + f" · accuracy {_pct(r['accuracy'])}",
              drill=f"#{r['tag'].key}") for r in ladder_rows
    ], empty="Mastery grows with the cards you train: solve some puzzles first.")
    weak = Chart("weak", "Weak spots: smoothed accuracy, at least 3 attempts", [
        Point(r["tag"].name, [round(100 * r["smoothed"])], f"{r['tag'].name} · {_pct(r['accuracy'])} of {r['n']} · ↵ Streak on it",
              drill=f"train:#{r['tag'].key}") for r in data["weakest"]
    ], [Series("Smoothed accuracy %", "bad")], empty="No weak spots yet (or not enough attempts).")

    # Collection
    funnel = Chart("funnel", "From collected to mature", [
        Point(label, [n], f"{label}: {n}", drill={"Collected": "", "Analysed": "has:analysis", "Puzzle": "has:puzzle",
                                                    "In training": "has:solution", "Mature": "has:solution"}.get(label, ""))
        for label, n in coll["funnel"]
    ], [Series("Positions", "chart-1")])
    by_source = Chart("sources", "Positions by source", [
        Point(s["source__short"] or s["source__title"], [s["n"]], f"{s['source__short'] or s['source__title']}: {s['n']}",
              drill=f'src:"{s["source__short"] or s["source__title"]}"') for s in coll["by_source"]
    ], [Series("Positions", "chart-2")], empty="No sources yet.")
    by_difficulty = charts.bars(Chart("difficulty", "Positions by difficulty", [
        Point("★" * d, [n], f"{'★' * d}: {n}", drill=f"diff:{d}") for d, n in coll["by_difficulty"]
    ], [Series("Positions", "chart-5")]))
    fields = [charts.hbars(Chart(f"field-{f['key']}", f["label"], [
        Point(t["tag__name"], [t["n"]], f"{t['tag__name']}: {t['n']}", drill=f"#{t['tag__key']}") for t in f["tags"]
    ], [Series("Positions", "chart-1")])) for f in coll["by_field"]]

    tiles = [
        ("Positions", coll["total"], ""), ("In training", coll["in_training"], "has:solution"), ("Games", coll["games"], "games:"),
        ("Moves of analysis", Node.objects.filter(parent__isnull=False, position__deleted_at=None).count(), "has:analysis"),
        ("Cards", lib["total"], "puzzles:"), ("Pattern library", lib["size"], "puzzles:state:mature"),
        ("Days in a row", cons["current"], ""),
    ]
    return {
        "period": period, "periods": list(PERIODS), "data": data, "tiles": tiles,
        "library_chart": library_chart, "stages_chart": stages_chart, "activity_chart": activity_chart,
        "calendar_chart": calendar_chart, "storm_chart": storm_chart, "ladder": ladder, "ladder_rows": ladder_rows,
        "levels": [name for name, _, _ in metrics.LEVELS],
        "ladder_points": json.dumps([{"label": p.label, "text": p.text, "drill": p.drill} for p in ladder.points]), "weak_chart": charts.hbars(weak), "funnel_chart": charts.hbars(funnel),
        "source_chart": charts.hbars(by_source), "difficulty_chart": by_difficulty, "field_charts": fields,
        "achievements": Achievement.objects.all()[:30], "retention_rows": [
            ("Last 7 days", ret["d7"]), ("Last 30 days", ret["d30"]), ("All", ret["all"]),
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
    return JsonResponse({"achievements": [{"label": a.label, "kind": a.kind} for a in rows]})
