"""Home (spec 04 · Home): what to do now. Today: due cards, one-key sessions, today's numbers, the pattern library and
the newest achievement as a banner. Continue: the open analysis, the next diagram of Collect, a paste box, and the
positions and games worked on last."""

from __future__ import annotations

from django.db.models import Max

from spaced_positions.analysis.models import JournalEntry
from spaced_positions.core.models import LOCAL_USER, UIState
from spaced_positions.library.models import Game
from spaced_positions.training import selection, srs
from spaced_positions.training.models import Position

from . import metrics
from .models import Achievement


def today() -> dict:
    counts = selection.counts()
    d = metrics.load()
    lib = metrics.library(d)
    cons = metrics.consistency(d)
    rows = metrics.tag_rows(d)
    weak = metrics.weakest(rows, k=3)
    return {
        "counts": counts, "due": counts["learning"] + counts["review"],
        "next_due": srs.describe_due(counts["next_due"]) if counts["next_due"] else "",
        "library": lib, "consistency": cons, "weakest": weak, "records": selection.records(),
        "accuracy": round(100 * cons["today_solved"] / cons["today"]) if cons["today"] else None,
        "banner": Achievement.objects.filter(seen=False).order_by("-reached_at").first(),
        "first_run": first_run(),
        "again": selection.last_options(),
    }


def _subject(mode: str) -> dict:
    state = UIState.objects.filter(user=LOCAL_USER, mode=mode).first()
    return (state.subject or {}) if state else {}


def continue_() -> dict:
    analysis = None
    saved = (_subject("analyse").get("analysis") or {}).get("A")
    if saved and saved.get("position"):
        owner = Position.alive.filter(uuid=saved["position"]).first() or Game.objects.filter(uuid=saved["position"], deleted_at=None).first()
        if owner is not None:
            node = owner.nodes.filter(id=saved.get("node")).first() if saved.get("node") else None
            analysis = {"id": str(owner.uuid), "title": owner.title or getattr(owner, "fen", ""), "short": owner.short_id,
                        "move": node.san if node and node.parent_id else "", "node": saved.get("node")}
    entry = _subject("collect").get("entry") or {}
    worked = (JournalEntry.objects.filter(user=LOCAL_USER, undone=False, position__deleted_at=None).exclude(position=None)
              .values("position").annotate(last=Max("created_at")).order_by("-last")[:6])
    ids = [w["position"] for w in worked]
    tagged = Position.alive.prefetch_related("tag_links__tag__field")  # each row shows its tags
    recent_positions = sorted(tagged.filter(pk__in=ids), key=lambda p: ids.index(p.pk))
    recent_positions += list(tagged.exclude(pk__in=ids).order_by("-created_at")[: max(0, 6 - len(recent_positions))])
    return {
        "analysis": analysis,
        "collect": {"source": (entry.get("source") or {}).get("label"), "ref": entry.get("ref"), "page": entry.get("page")} if entry else None,
        "recent_positions": recent_positions, "recent_games": Game.objects.filter(deleted_at=None).order_by("-updated_at")[:4],
    }


def first_run() -> dict | None:
    """An empty library: Home starts with the ways in (spec 10 · decision 16). None once there is anything."""
    from spaced_positions.core.settings_view import csm_guess

    if Position.objects.exists():
        return None
    return {"csm": csm_guess()}

