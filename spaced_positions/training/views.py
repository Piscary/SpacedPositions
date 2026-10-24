"""Training endpoints (spec 09 §7). The solve → next loop never waits for these: the trainer gets puzzles in
batches and posts attempts in the background."""

import json
import statistics

from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from spaced_positions.library.models import SavedQuery

from . import pace, puzzles, selection, srs
from .models import Attempt, Card, Puzzle, Session

LOOKS = ("normal", "silhouette", "blind")
SIDES = ("move", "white", "black", "random")


def _json(request) -> dict:
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _session(sid) -> Session:
    try:
        return Session.objects.get(uuid=sid)
    except (Session.DoesNotExist, ValueError):
        raise Http404("no such session") from None


def _options(data: dict) -> tuple[str, dict]:
    mode = data.get("mode")
    if mode not in Session.Mode.values:
        raise ValueError("mode must be review, storm or streak")
    options = {
        "look": data.get("look") if data.get("look") in LOOKS else "normal",
        "side": data.get("side") if data.get("side") in SIDES else "move",
        "first_move": bool(data.get("first_move")),
    }
    if mode == Session.Mode.STORM:
        options["minutes"] = int(data.get("minutes") or 3) if int(data.get("minutes") or 3) in (3, 5, 10) else 3
        options["pace"] = data.get("pace") if data.get("pace") in pace.PACES else "medium"
    if mode == Session.Mode.STREAK:
        options["lives"] = int(data.get("lives") or 0) if int(data.get("lives") or 0) in (0, 1, 3, 5) else 0
    if str(data.get("filter") or "").strip():
        options["filter"] = str(data["filter"]).strip()[:500]
    if data.get("weakest"):  # a Streak on the weakest motifs (Stats · Weak spots)
        from spaced_positions.stats import metrics

        weak = metrics.weakest(metrics.tag_rows(metrics.load()), k=4)
        if not weak:
            raise ValueError("no weak spots yet: they show after 3 attempts on a motif")
        options["filter"] = "tag:" + ",".join(r["tag"].key for r in weak)
        options["weakest"] = [r["tag"].name for r in weak]
    cards = data.get("cards")
    if isinstance(cards, list) and cards:
        options["cards"] = [str(c) for c in cards][:200]
    return mode, options


@require_POST
def start(request):
    try:
        mode, options = _options(_json(request))
    except ValueError as e:
        return JsonResponse({"ok": False, "message": str(e)}, status=422)
    session = selection.start(mode, options)
    queue = session.options["queue"]
    if not queue:
        session.delete()
        message = "Nothing due right now." if mode == Session.Mode.REVIEW else "No puzzles yet: make one from a board with :puzzle"
        if options.get("filter"):
            message = f"No puzzles in training match “{options['filter']}”" + (" that are due" if mode == Session.Mode.REVIEW else "")
        return JsonResponse({"ok": False, "empty": True, "message": message}, status=200)
    return JsonResponse(
        {
            "ok": True,
            "session": str(session.uuid),
            "mode": mode,
            "label": session.label,
            "options": {k: v for k, v in session.options.items() if k not in ("queue", "mirror")},
            "total": len(queue),
            "puzzles": selection.batch(session, 0),
            "clock": pace.clock(options.get("pace", "medium")) if mode == Session.Mode.STORM else None,
            "records": selection.records(),
        }
    )


@require_GET
def batch(request, sid):
    session = _session(sid)
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except ValueError:
        offset = 0
    return JsonResponse({"puzzles": selection.batch(session, offset)})


@require_POST
def attempt(request, sid):
    session = _session(sid)
    data = _json(request)
    try:
        card = Card.objects.select_related("puzzle__position").get(uuid=data.get("card"))
    except (Card.DoesNotExist, ValueError):
        raise Http404("no such card") from None
    hinted, gave_up = bool(data.get("hinted")), bool(data.get("gave_up"))
    success = bool(data.get("success")) and not hinted and not gave_up
    ms = max(0, min(int(data.get("ms") or 0), 3_600_000))
    now = timezone.now()
    outcome = srs.record(card, success, ms, now)
    card.save()
    Attempt.objects.create(
        card=card,
        session=session,
        at=now,
        success=success,
        ms=ms,
        hinted=hinted,
        gave_up=gave_up,
        wrong_move=str(data.get("wrong_move") or "")[:8],
        mode=session.mode,
        look=session.options.get("look", ""),
        first_move_only=bool(session.options.get("first_move")),
        counted=outcome.counted,
        state_before=outcome.state_before,
        interval_before=outcome.interval_before,
        interval_after=outcome.interval,
        due_before=outcome.due_before,
        solved_as=str(data.get("solved_as") or "")[:1],
        mirrored=bool(data.get("mirrored")),
        flipped=bool(data.get("flipped")),
    )
    if success:
        session.solved += 1
    else:
        session.failed += 1
    session.save(update_fields=["solved", "failed"])
    return JsonResponse(
        {
            "ok": True,
            "counted": outcome.counted,
            "stage": card.stage,
            "due": srs.describe_due(card.due, now),
            "interval": round(card.interval_days, 1),
        }
    )


@require_POST
def end(request, sid):
    session = _session(sid)
    data = _json(request)
    if session.ended_at is None:
        session.ended_at = timezone.now()
        session.best_combo = max(0, int(data.get("best_combo") or 0))
        session.streak = max(0, int(data.get("streak") or 0))
        session.duration_s = max(0, int(data.get("duration_s") or 0)) or None
        session.save()
        from spaced_positions.stats.metrics import sync_achievements

        sync_achievements(session=session)  # records, milestones and level-ups reached in it: on the result screen
    return JsonResponse({"ok": True})


def _bars(attempts) -> dict:
    """Bars of the result chart (spec 04 · Result): time per puzzle, solved or missed, scaled to the slowest."""
    if not attempts:
        return {"bars": [], "max_s": 0}
    longest = max(a.ms for a in attempts) or 1
    return {
        "bars": [{"h": max(4, round(100 * a.ms / longest)), "ok": a.success, "s": round(a.ms / 1000, 1), "n": i + 1} for i, a in enumerate(attempts)],
        "max_s": round(longest / 1000, 1),
    }


@require_GET
def result(request, sid):
    session = _session(sid)
    attempts = list(session.attempts.select_related("card__puzzle__position").order_by("at"))
    for a in attempts:
        a.seconds = round(a.ms / 1000, 1)
    played = len(attempts)
    previous = Session.objects.filter(mode=session.mode).exclude(pk=session.pk).exclude(ended_at=None)
    if session.mode == Session.Mode.STORM:
        previous = [s.solved for s in previous if s.options.get("minutes") == session.options.get("minutes")]
    elif session.mode == Session.Mode.STREAK:
        previous = [s.streak for s in previous if s.options.get("lives", 0) == session.options.get("lives", 0)]
    else:
        previous = []
    best_before = max(previous, default=0)
    minutes = (session.duration_s or sum(a.ms for a in attempts) / 1000) / 60
    context = {
        "session": session,
        "attempts": attempts,
        "played": played,
        "accuracy": round(100 * session.solved / played) if played else 0,
        "per_minute": round(session.solved / minutes, 1) if minutes else 0,
        "median_s": round(statistics.median(a.ms for a in attempts) / 1000, 1) if attempts else 0,
        "record": session.mode != Session.Mode.REVIEW and session.score > best_before and session.score > 0,
        "best_before": best_before,
        "chart": _bars(attempts),
        "missed": sum(not a.success for a in attempts),
    }
    return render(request, "training/result.html", context)


@require_GET
def launcher(request):
    return render(request, "training/launcher.html", launcher_context())


def launcher_context() -> dict:
    from spaced_positions.core import settings as user_settings
    from spaced_positions.stats import metrics

    counts = selection.counts()
    weak = metrics.weakest(metrics.tag_rows(metrics.load()), k=3)
    records = selection.records()
    return {
        "counts": counts,
        "due": counts["learning"] + counts["review"],
        "next_due": srs.describe_due(counts["next_due"]) if counts["next_due"] else "",
        "records": records,
        "storm_best": {m: records["storm"].get(m, 0) for m in (3, 5, 10)},
        "storm_pace": user_settings.get("training.storm-pace"),
        "storm_paces": user_settings.BY_NAME["training.storm-pace"].values,
        "streak_best": records["streak"].get(0, 0),
        "again": selection.last_options(),
        "weakest": [f"{r['tag'].name} {round(100 * r['smoothed'])}%" for r in weak],
        "saved_queries": SavedQuery.objects.filter(collection__in=["positions", "puzzles"])[:9],
        "custom_modes": [("review", "Review", "b"), ("storm", "Storm 3′", "n"), ("streak", "Streak", "m")],
        "custom_looks": [("normal", "Normal", "q"), ("silhouette", "Silhouette", "w"), ("blind", "Blind", "e")],
        "custom_sides": [("move", "To move", "a"), ("white", "White", "s"), ("black", "Black", "d"), ("random", "Random", "f")],
        "custom_lives": [("0", "0", "z"), ("1", "1", "x"), ("3", "3", "c"), ("5", "5", "v")],
    }


@require_POST
def from_line(request):
    data = _json(request)
    moves = data.get("moves") or []
    if not isinstance(moves, list) or not all(isinstance(m, str) for m in moves):
        return HttpResponseBadRequest("moves must be a list of UCI moves")
    try:
        puzzle = puzzles.create_from_line(str(data.get("start") or ""), moves, title=str(data.get("title") or "")[:200])
    except ValueError as e:
        return JsonResponse({"ok": False, "message": str(e)}, status=422)
    cards = puzzle.cards.filter(in_solution=True).count()
    return JsonResponse({"ok": True, "puzzle": str(puzzle.uuid), "cards": cards, "message": f"Puzzle saved: {cards} card{'s' if cards != 1 else ''} in training"})


@require_POST
def flag(request):
    data = _json(request)
    updated = Puzzle.objects.filter(uuid=data.get("puzzle")).update(flagged=True) if data.get("puzzle") else 0
    return JsonResponse({"ok": bool(updated)})
