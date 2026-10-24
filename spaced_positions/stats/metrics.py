"""Training and collection metrics (spec 04 · Stats), computed from the tables only; the rules are chess-study-manager's
(training/metrics.py there), kept.

Card stages (from the schedule)
    new        never solved yet
    learning   in the short learning / relearning steps
    young      in review, interval < MATURE_DAYS
    mature     in review, interval ≥ MATURE_DAYS: held in long-term memory

Pattern library = mature cards. Each answer line is a card, so each counts as a pattern.

Retention = due reviews solved: counted attempts that found the card in review (state_before = review); young and
mature by the interval before the attempt.

Mastery of a tag (and of a family of tags) from its established cards and its retention:
    Learning (attempted) → Familiar (1) → Solid (5, 75 %) → Strong (15, 80 %) → Expert (40, 85 %) → Master (100, 90 %)
A mature card counts 1, a young card its share of the way (interval / MATURE_DAYS). Levels above Familiar need the
retention proven in at least REVIEWS_FOR_RETENTION due reviews.

Weakness = smoothed accuracy (solved + PRIOR·PRIOR_WEIGHT) / (attempts + PRIOR_WEIGHT), from WEAK_MIN_ATTEMPTS on.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

from django.db import IntegrityError, transaction
from django.utils import timezone

from spaced_positions.training import srs
from spaced_positions.training.models import Attempt, Card, Position, Session

MATURE_DAYS = 21
LIBRARY_MILESTONES = [25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000]
DAY_STREAK_MILESTONES = [7, 14, 30, 60, 100, 200, 365]
STORM_MILESTONES = [20, 30, 40, 50, 60, 75, 100]
STREAK_MILESTONES = [10, 25, 50, 100, 200]
RETENTION_MILESTONES = [85, 90, 95]
RETENTION_MIN_REVIEWS = 100
WEEK_GOAL_DAYS = 4
ON_TIME_GRACE = timedelta(days=1)
PRIOR, PRIOR_WEIGHT = 0.8, 4
WEAK_MIN_ATTEMPTS = 3
REVIEWS_FOR_RETENTION = 5
ROBUST_MIN, ROBUST_GAP = 10, 0.10
FAMILIES = [("motif", "Tactical motifs"), ("mate", "Mating patterns"), ("goal", "Objectives"), ("endgame", "Endgame types"),
            ("technique", "Endgame technique"), ("strategy", "Positional themes")]
LEVELS = [("Learning", 0, 0.0), ("Familiar", 1, 0.0), ("Solid", 5, 0.75), ("Strong", 15, 0.80), ("Expert", 40, 0.85), ("Master", 100, 0.90)]
MILESTONE_TEXT = {
    "library": "{v:,} patterns in your library", "daystreak": "{v} days in a row", "retention": "{v} % retention over 30 days",
    "storm": "{v} puzzles in one Storm", "streak": "A streak of {v}",
}
NOT_STARTED = {"level": -1, "name": "Not started", "next": "", "progress": 0}


def stage(card) -> str:
    if card.state == "new":
        return "new"
    if card.state in ("learning", "relearning"):
        return "learning"
    return "mature" if card.interval_days >= MATURE_DAYS else "young"


def rate(ok, n):
    return ok / n if n else None


def smoothed(ok, n):
    return (ok + PRIOR * PRIOR_WEIGHT) / (n + PRIOR_WEIGHT)


def local_day(dt) -> date:
    return timezone.localtime(dt).date()


def is_review(a) -> bool:
    return a.counted and a.state_before == "review"


# ── Data ──────────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass
class Data:
    now: datetime
    cards: list
    attempts: list
    sessions: list
    tags: dict = field(default_factory=dict)  # card id → [Tag]


def load(now=None) -> Data:
    """Cards in training with the tags of their position and of their first solver move."""
    now = now or timezone.now()
    cards = list(
        Card.objects.filter(in_solution=True, puzzle__active=True, puzzle__position__deleted_at=None)
        .select_related("puzzle__position", "puzzle__start_node")
        .prefetch_related("puzzle__position__tag_links__tag__field", "puzzle__start_node__kids__tag_links__tag__field")
    )
    attempts = list(Attempt.objects.order_by("at"))
    sessions = list(Session.objects.exclude(ended_at=None).order_by("started_at"))
    data = Data(now, cards, attempts, sessions)
    keys = {k for k, _ in FAMILIES}
    for c in cards:
        found = {}
        for link in c.puzzle.position.tag_links.all():
            if link.origin != "suggested" and link.tag.field.key in keys:
                found[link.tag_id] = link.tag
        start = c.puzzle.start_node
        if start is not None:
            for kid in start.kids.all():
                if kid.order == 0:
                    for link in kid.tag_links.all():
                        if link.origin != "suggested" and link.tag.field.key in keys:
                            found[link.tag_id] = link.tag
        data.tags[c.pk] = list(found.values())
    return data


# ── Pattern library ───────────────────────────────────────────────────────────────────────────────────────────


def first_mature_dates(attempts) -> dict:
    out = {}
    for a in attempts:
        if a.card_id not in out and a.success and a.counted and a.interval_after >= MATURE_DAYS:
            out[a.card_id] = a.at
    return out


def library(d: Data) -> dict:
    counts = defaultdict(int)
    for c in d.cards:
        counts[stage(c)] += 1
    size = counts["mature"]
    reached = sorted(first_mature_dates(d.attempts).values())
    prev = max([m for m in LIBRARY_MILESTONES if m <= size], default=0)
    nxt = next((m for m in LIBRARY_MILESTONES if m > size), None)
    pace = sum(1 for t in reached if t >= d.now - timedelta(days=28)) / 4  # per week, last 4 weeks
    forecast = maturity_forecast(d)
    on_course = forecast[nxt - size - 1] if nxt and len(forecast) >= nxt - size else None
    return {
        "size": size, "counts": dict(counts), "total": len(d.cards), "established": counts["mature"] + counts["young"],
        "prev": prev, "next": nxt, "progress": ((size - prev) / (nxt - prev)) if nxt else 1.0,
        "pace": pace, "weeks_to_next": ((nxt - size) / pace) if nxt and pace > 0 else None, "on_course": on_course,
        "maturing_soon": sum(1 for t in forecast if t <= d.now + timedelta(days=30)),
        "reached": [(m, reached[m - 1]) for m in LIBRARY_MILESTONES if len(reached) >= m],
        "history": library_history(reached, d.now),
    }


def library_history(reached: list, now, days: int = 90) -> list[tuple[date, int]]:
    """Mature cards at the end of each day (first maturity dates; a card that lapsed later still counts once)."""
    today = local_day(now)
    days_list = [today - timedelta(days=days - 1 - i) for i in range(days)]
    out, i, n = [], 0, 0
    reached_days = sorted(local_day(t) for t in reached)
    for day in days_list:
        while i < len(reached_days) and reached_days[i] <= day:
            n += 1
            i += 1
        out.append((day, n))
    return out


def maturity_forecast(d: Data, horizon_days: int = 365) -> list:
    """When each card not yet mature would become mature if solved every time it is due (sorted)."""
    out = []
    end = d.now + timedelta(days=horizon_days)
    for c in d.cards:
        if c.state == "new" or stage(c) == "mature":
            continue
        sim = SimpleNamespace(pk=c.pk, state=c.state, due=c.due, interval_days=c.interval_days, ease=c.ease, step=c.step,
                              reps=c.reps, lapses=c.lapses, success_streak=c.success_streak)
        t = max(c.due, d.now)
        for _ in range(30):
            srs.review(sim, True, t)
            if stage(sim) == "mature":
                out.append(t)
                break
            t = sim.due
            if t > end:
                break
    return sorted(out)


def stage_history(d: Data, days: int = 60) -> list[dict]:
    """Cards per stage at the end of each day: the scheduler replayed over each card's attempts."""
    by_card = defaultdict(list)
    for a in d.attempts:
        by_card[a.card_id].append(a)
    timeline = {}
    for c in d.cards:
        sim = SimpleNamespace(pk=c.pk, state="new", due=c.created_at, interval_days=0.0, ease=2.5, step=0, reps=0, lapses=0, success_streak=0)
        steps = []
        for a in by_card[c.pk]:
            srs.review(sim, a.success, a.at)
            steps.append((local_day(a.at), stage(sim)))
        timeline[c.pk] = (local_day(c.created_at), steps)
    start = local_day(d.now) - timedelta(days=days - 1)
    out = []
    for i in range(days):
        day = start + timedelta(days=i)
        row = {"day": day, "new": 0, "learning": 0, "young": 0, "mature": 0}
        for made, steps in timeline.values():
            if made > day:
                continue
            current = "new"
            for when, st in steps:
                if when > day:
                    break
                current = st
            row[current] += 1
        out.append(row)
    first = next((i for i, r in enumerate(out) if r["learning"] + r["young"] + r["mature"]), len(out))
    return out[max(0, first - 1):]


# ── Retention ─────────────────────────────────────────────────────────────────────────────────────────────────


def retention(d: Data) -> dict:
    reviews = [a for a in d.attempts if is_review(a)]

    def window(days):
        rs = [a for a in reviews if days is None or a.at >= d.now - timedelta(days=days)]
        ok = sum(a.success for a in rs)
        return {"n": len(rs), "ok": ok, "rate": rate(ok, len(rs))}

    young = [a for a in reviews if (a.interval_before or 0) < MATURE_DAYS]
    mature = [a for a in reviews if (a.interval_before or 0) >= MATURE_DAYS]
    recent = [a for a in d.attempts if a.at >= d.now - timedelta(days=30)]
    return {
        "d7": window(7), "d30": window(30), "all": window(None),
        "young": {"n": len(young), "rate": rate(sum(a.success for a in young), len(young))},
        "mature": {"n": len(mature), "rate": rate(sum(a.success for a in mature), len(mature))},
        "accuracy30": rate(sum(a.success for a in recent), len(recent)),
    }


# ── Tags, mastery, weak spots ─────────────────────────────────────────────────────────────────────────────────


def mastery(established, ret, proven=True) -> dict:
    """{level, name, what the next level needs, progress}. Without proven retention: at most Familiar."""
    level = 0
    for i, (_name, need, need_ret) in enumerate(LEVELS):
        if established >= need and (ret or 0) >= need_ret and (proven or i <= 1):
            level = i
    if level + 1 < len(LEVELS):
        name, need, need_ret = LEVELS[level + 1]
        missing = []
        if established < need:
            more = max(1, math.ceil(need - established - 1e-9))
            missing.append(f"{more} more established card{'s' if more != 1 else ''}")
        if need_ret and not proven:
            missing.append(f"{REVIEWS_FOR_RETENTION} due reviews to prove retention")
        elif need_ret and (ret or 0) < need_ret:
            missing.append(f"retention {need_ret:.0%}")
        nxt = f"{name}: " + " and ".join(missing)
        progress = min(0.99, min(1.0, established / need) if need else 1.0)
    else:
        nxt, progress = "", 1.0
    return {"level": level, "name": LEVELS[level][0], "next": nxt, "progress": progress}


def weight(card) -> float:
    st = stage(card)
    return 1.0 if st == "mature" else (min(1.0, card.interval_days / MATURE_DAYS) if st == "young" else 0.0)


def tag_rows(d: Data) -> list[dict]:
    rows = {}
    card_stage = {c.pk: stage(c) for c in d.cards}
    for c in d.cards:
        for t in d.tags.get(c.pk, []):
            r = rows.setdefault(t.pk, {"tag": t, "cards": 0, "new": 0, "learning": 0, "mature": 0, "young": 0, "established": 0.0,
                                       "n": 0, "ok": 0, "rn": 0, "rok": 0, "ms": []})
            r["cards"] += 1
            r[card_stage[c.pk]] += 1
            r["established"] += weight(c)
    for a in d.attempts:
        if a.card_id not in card_stage:
            continue
        for t in d.tags.get(a.card_id, []):
            r = rows.get(t.pk)
            if r is None:
                continue
            r["n"] += 1
            r["ok"] += a.success
            if is_review(a):
                r["rn"] += 1
                r["rok"] += a.success
            if a.success and a.ms:
                r["ms"].append(a.ms)
    out = []
    for r in rows.values():
        r["accuracy"] = rate(r["ok"], r["n"])
        r["smoothed"] = smoothed(r["ok"], r["n"])
        r["retention"] = rate(r["rok"], r["rn"]) if r["rn"] >= REVIEWS_FOR_RETENTION else None
        r["median_s"] = statistics.median(r["ms"]) / 1000 if r["ms"] else None
        r["mastery"] = mastery(r["established"], r["retention"], proven=r["retention"] is not None) if r["n"] else NOT_STARTED
        del r["ms"]
        out.append(r)
    out.sort(key=lambda r: (r["tag"].field.order, -r["cards"], r["tag"].name))
    return out


def families(rows: list[dict]) -> list[dict]:
    out = []
    for key, label in FAMILIES:
        members = [r for r in rows if r["tag"].field.key == key]
        if not members:
            continue
        n, ok = sum(r["n"] for r in members), sum(r["ok"] for r in members)
        rn, rok = sum(r["rn"] for r in members), sum(r["rok"] for r in members)
        est = sum(r["established"] for r in members)
        out.append({
            "key": key, "label": label, "tags": members, "n": n, "accuracy": rate(ok, n), "retention": rate(rok, rn) if rn else None,
            "established": est, "mastery": mastery(est, rate(rok, rn), proven=rn >= REVIEWS_FOR_RETENTION) if n else NOT_STARTED,
            "weakest": min((r for r in members if r["n"] >= WEAK_MIN_ATTEMPTS), key=lambda r: r["smoothed"], default=None),
        })
    return out


def weakest(rows: list[dict], k: int = 6) -> list[dict]:
    return sorted((r for r in rows if r["n"] >= WEAK_MIN_ATTEMPTS), key=lambda r: (r["smoothed"], -r["n"]))[:k]


# ── Storm, Streak ─────────────────────────────────────────────────────────────────────────────────────────────


def per_minute(s) -> float:
    minutes = s.options.get("minutes") or 3
    return s.solved / (s.duration_s / 60 if s.duration_s else minutes)


def storm(d: Data) -> dict:
    sessions = [s for s in d.sessions if s.mode == "storm"]
    best = {m: max([s.solved for s in sessions if s.options.get("minutes") == m], default=0) for m in (3, 5, 10)}
    recent = sessions[-10:]
    solved, failed = sum(s.solved for s in recent), sum(s.failed for s in recent)
    times = [a.ms for a in d.attempts if a.mode == "storm" and a.success and a.ms]
    return {
        "count": len(sessions), "best": best, "ppm": statistics.mean([per_minute(s) for s in recent]) if recent else None,
        "best_combo": max([s.best_combo for s in sessions], default=0), "accuracy": rate(solved, solved + failed),
        "median_s": statistics.median(times[-300:]) / 1000 if times else None,
        "history": [{"at": s.started_at, "minutes": s.options.get("minutes"), "solved": s.solved, "failed": s.failed,
                     "pace": s.options.get("pace", "medium")} for s in sessions[-30:]],
    }


def streak(d: Data) -> dict:
    sessions = [s for s in d.sessions if s.mode == "streak"]
    plain = [s.streak for s in sessions if not s.options.get("lives")]
    with_lives = {}
    for s in sessions:
        lives = s.options.get("lives") or 0
        if lives:
            with_lives[lives] = max(with_lives.get(lives, 0), s.streak)
    return {"count": len(sessions), "longest": max(plain, default=0), "average": statistics.mean(plain[-20:]) if plain else None,
            "with_lives": sorted(with_lives.items()),
            "history": [{"at": s.started_at, "streak": s.streak, "lives": s.options.get("lives") or 0} for s in sessions[-30:]]}


# ── Consistency, calendar ─────────────────────────────────────────────────────────────────────────────────────


def streaks(days: set, today: date) -> tuple[int, int]:
    """(current run, longest run) of consecutive days; the current run stays alive while today or yesterday counts."""
    longest = run = 0
    prev = None
    for day in sorted(days):
        run = run + 1 if prev and day - prev == timedelta(days=1) else 1
        longest = max(longest, run)
        prev = day
    current = 0
    probe = today if today in days else today - timedelta(days=1)
    while probe in days:
        current += 1
        probe -= timedelta(days=1)
    return current, longest


def consistency(d: Data) -> dict:
    days = {local_day(a.at) for a in d.attempts}
    today = local_day(d.now)
    cur, longest = streaks(days, today)
    per_week = defaultdict(int)
    for day in days:
        per_week[day - timedelta(days=day.weekday())] += 1
    this_week = today - timedelta(days=today.weekday())
    weeks, probe = 0, this_week if per_week.get(this_week, 0) >= WEEK_GOAL_DAYS else this_week - timedelta(days=7)
    while per_week.get(probe, 0) >= WEEK_GOAL_DAYS:
        weeks += 1
        probe -= timedelta(days=7)
    due_attempts = [a for a in d.attempts if a.counted and a.state_before not in ("new", "") and a.due_before]
    recent = [a for a in due_attempts if a.at >= d.now - timedelta(days=30)]
    on_time = sum(1 for a in recent if a.at - a.due_before <= ON_TIME_GRACE)
    today_attempts = [a for a in d.attempts if local_day(a.at) == today]
    return {
        "current": cur, "longest": longest, "trained_today": today in days, "weeks": weeks, "week_goal": WEEK_GOAL_DAYS,
        "this_week_days": per_week.get(this_week, 0), "active30": sum(1 for day in days if day > today - timedelta(days=30)),
        "on_time": rate(on_time, len(recent)), "overdue": sum(1 for c in d.cards if c.state != "new" and d.now - c.due > ON_TIME_GRACE),
        "today": len(today_attempts), "today_solved": sum(a.success for a in today_attempts),
    }


def calendar(d: Data, weeks: int = 53) -> dict:
    """Weeks × days (Monday first) with the attempts of each day (the activity heatmap)."""
    today = local_day(d.now)
    start = today - timedelta(days=today.weekday() + 7 * (weeks - 1))
    count, solved = defaultdict(int), defaultdict(int)
    for a in d.attempts:
        day = local_day(a.at)
        if day >= start:
            count[day] += 1
            solved[day] += a.success
    peak = max(count.values(), default=0)
    out = []
    for w in range(weeks):
        week = []
        for i in range(7):
            day = start + timedelta(days=7 * w + i)
            n = count.get(day, 0)
            week.append({"day": day, "n": n, "ok": solved.get(day, 0), "level": 0 if not n else min(4, 1 + int(4 * n / (peak + 1))),
                         "future": day > today})
        out.append(week)
    return {"weeks": out, "peak": peak, "days": sum(1 for v in count.values() if v)}


def robustness(d: Data) -> list[dict]:
    def group(pred):
        rs = [a for a in d.attempts if pred(a)]
        return {"n": len(rs), "rate": rate(sum(a.success for a in rs), len(rs))}

    pairs = [
        ("Colour", "as White", group(lambda a: a.solved_as == "w"), "as Black", group(lambda a: a.solved_as == "b")),
        ("Mirroring", "original", group(lambda a: not a.mirrored), "mirrored", group(lambda a: a.mirrored)),
        ("Board", "side below", group(lambda a: not a.flipped), "side on top", group(lambda a: a.flipped)),
    ]
    out = []
    for label, a_label, a, b_label, b in pairs:
        gap = (a["rate"] - b["rate"]) if a["rate"] is not None and b["rate"] is not None else None
        flag = gap is not None and min(a["n"], b["n"]) >= ROBUST_MIN and abs(gap) >= ROBUST_GAP
        out.append({"label": label, "a_label": a_label, "a": a, "b_label": b_label, "b": b, "gap": gap, "flag": flag,
                    "weaker": (b_label if gap > 0 else a_label) if flag else ""})
    return out


# ── Activity and the collection ───────────────────────────────────────────────────────────────────────────────


def activity(d: Data, weeks: int = 26) -> list[dict]:
    """Points per week by kind: collect (positions made), analyse (changes of an analysis), train (puzzles solved)."""
    from spaced_positions.analysis.models import JournalEntry

    from .models import ActivityLog

    today = local_day(d.now)
    start = today - timedelta(days=today.weekday() + 7 * (weeks - 1))
    out = {start + timedelta(days=7 * w): {"collect": 0, "analyse": 0, "train": 0} for w in range(weeks)}

    def week_of(dt):
        day = local_day(dt)
        return day - timedelta(days=day.weekday())

    since = timezone.make_aware(datetime.combine(start, time.min))
    for created in Position.objects.filter(created_at__gte=since).values_list("created_at", flat=True):
        if week_of(created) in out:  # migrated positions keep the day they were collected in the old app
            out[week_of(created)]["collect"] += 1
    for when in JournalEntry.objects.filter(created_at__gte=since, undone=False).values_list("created_at", flat=True):
        if week_of(when) in out:
            out[week_of(when)]["analyse"] += 1
    for kind, points, when in ActivityLog.objects.filter(at__gte=since).values_list("kind", "points", "at"):
        if week_of(when) in out:  # the old app's analysis work and board moves (phase 7)
            out[week_of(when)][kind] += points
    for a in d.attempts:
        if a.at >= since and a.success and week_of(a.at) in out:
            out[week_of(a.at)]["train"] += 1
    return [{"week": week, **counts} for week, counts in out.items()]


def collection() -> dict:
    """The material: positions by field and tag, by source and difficulty, analysis coverage, and the funnel
    collected → analysed → puzzle → in training → mature."""
    from django.db.models import Count, Exists, OuterRef

    from spaced_positions.analysis.models import Node
    from spaced_positions.library.models import Game, PositionTag, TagField
    from spaced_positions.training.models import Puzzle

    alive = Position.alive.all()
    total = alive.count()
    analysed = alive.filter(Exists(Node.objects.filter(position=OuterRef("pk"), parent__isnull=False))).count()
    with_puzzle = alive.filter(Exists(Puzzle.objects.filter(position=OuterRef("pk")))).count()
    in_training = alive.filter(Exists(Puzzle.objects.filter(position=OuterRef("pk"), active=True))).count()
    mature = alive.filter(Exists(Card.objects.filter(puzzle__position=OuterRef("pk"), in_solution=True, state="review",
                                                     interval_days__gte=MATURE_DAYS))).count()
    by_field = []
    links = PositionTag.objects.filter(position__deleted_at=None).exclude(origin="suggested")
    for f in TagField.objects.filter(on_positions=True):
        tags = list(links.filter(tag__field=f).values("tag__key", "tag__name").annotate(n=Count("id")).order_by("-n")[:8])
        if tags:
            by_field.append({"key": f.key, "label": f.name, "tags": tags})
    by_source = list(alive.exclude(source=None).values("source__title", "source__short").annotate(n=Count("id")).order_by("-n")[:8])
    by_difficulty = {d: n for d, n in alive.order_by().values_list("difficulty").annotate(n=Count("id")) if d}
    return {
        "total": total, "analysed": analysed, "with_puzzle": with_puzzle, "in_training": in_training, "mature": mature,
        "games": Game.objects.filter(deleted_at=None).count(),
        "by_field": by_field, "by_source": by_source, "by_difficulty": [(d, by_difficulty.get(d, 0)) for d in range(1, 6)],
        "funnel": [("Collected", total), ("Analysed", analysed), ("Puzzle", with_puzzle), ("In training", in_training), ("Mature", mature)],
    }


# ── Achievements ──────────────────────────────────────────────────────────────────────────────────────────────


def milestone_candidates(d: Data, lib: dict, ret: dict) -> dict:
    """(kind, value) → when it was first reached: dated from the history where possible."""
    out = [("library", m, when) for m, when in lib["reached"]]
    days = sorted({local_day(a.at) for a in d.attempts})
    run, prev = 0, None
    for day in days:
        run = run + 1 if prev and day - prev == timedelta(days=1) else 1
        prev = day
        for m in DAY_STREAK_MILESTONES:
            if run == m:
                out.append(("daystreak", m, timezone.make_aware(datetime.combine(day, time(20)))))
    for s in d.sessions:
        for m in STORM_MILESTONES:
            if s.mode == "storm" and s.solved >= m:
                out.append(("storm", m, s.ended_at))
        for m in STREAK_MILESTONES:
            if s.mode == "streak" and not s.options.get("lives") and s.streak >= m:
                out.append(("streak", m, s.ended_at))
    if ret["d30"]["n"] >= RETENTION_MIN_REVIEWS and ret["d30"]["rate"] is not None:
        for m in RETENTION_MILESTONES:
            if ret["d30"]["rate"] * 100 >= m:
                out.append(("retention", m, d.now))
    first = {}
    for kind, value, when in out:
        if (kind, value) not in first or when < first[(kind, value)]:
            first[(kind, value)] = when
    return first


def records(d: Data) -> dict:
    """(key, value) → (session, when) of each new best: Storm per length, Streak per number of lives."""
    best, out = {}, {}
    for s in d.sessions:
        if s.mode == "storm":
            key, value = f"storm-{s.options.get('minutes') or 3}", s.solved
        elif s.mode == "streak":
            key, value = f"streak-{s.options.get('lives') or 0}", s.streak
        else:
            continue
        if value > best.get(key, 0):
            best[key] = value
            out[(key, value)] = (s, s.ended_at)
    return out


def record_label(key: str, value: int) -> str:
    kind, n = key.split("-")
    if kind == "storm":
        return f"▲ new best Storm {n}′: {value}"
    return f"▲ new best Streak{' ♥' + n if n != '0' else ''}: {value}"


def sync_achievements(d: Data | None = None, session: Session | None = None) -> list:
    """Log milestones, records and level-ups reached and not logged yet. On the very first run the history is logged
    as already seen, except the most recent one, which is announced. Returns the new achievements."""
    from .models import Achievement

    d = d or load()
    lib, ret = library(d), retention(d)
    found = []  # (kind, key, value, label, when, session)
    for (kind, value), when in milestone_candidates(d, lib, ret).items():
        found.append((kind, "", value, MILESTONE_TEXT[kind].format(v=value), when, None))
    for (key, value), (s, when) in records(d).items():
        found.append(("record", key, value, record_label(key, value), when, s))
    for r in tag_rows(d):
        level = r["mastery"]["level"]
        if level >= 2:  # Solid and above are worth announcing
            for lv in range(2, level + 1):
                found.append(("level", r["tag"].key, lv, f"{r['tag'].name}: {LEVELS[lv - 1][0]} → {LEVELS[lv][0]}", d.now, None))
    existing = set(Achievement.objects.values_list("kind", "key", "value"))
    first_run = not existing
    new = [f for f in found if (f[0], f[1], f[2]) not in existing]
    if not new:
        return []
    latest = max(new, key=lambda f: (f[4], f[2]))
    made = []
    for item in new:
        kind, key, value, label, when, s = item
        # reached in this session: the result screen shows it, which announces it
        here = session is not None and (when == session.ended_at or getattr(s, "pk", None) == session.pk or not first_run)
        try:
            with transaction.atomic():
                made.append(Achievement.objects.create(
                    kind=kind, key=key, value=value, label=label[:200], reached_at=when or d.now, session=session if here else s,
                    seen=here or (first_run and item != latest),
                ))
        except IntegrityError:
            continue  # logged meanwhile
    return made


# ── Everything for a page ─────────────────────────────────────────────────────────────────────────────────────


def dashboard(now=None) -> dict:
    d = load(now)
    rows = tag_rows(d)
    return {
        "library": library(d), "retention": retention(d), "consistency": consistency(d), "storm": storm(d), "streak": streak(d),
        "robustness": robustness(d), "families": families(rows), "tags": rows, "weakest": weakest(rows), "calendar": calendar(d),
        "stages": stage_history(d), "activity": activity(d), "collection": collection(), "_data": d,
    }
