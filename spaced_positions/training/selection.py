"""Which cards a session trains, in which order (spec 04 · Train).

Review   due learning and relearning cards (by due date), then due reviews, then new cards up to the daily limit
Storm    one card per puzzle, a random sample, easiest first and getting harder
Streak   like Storm, as one long run

The queue is fixed when the session starts (stored with it) and sent to the trainer in batches.
"""

import random
from django.db.models import Q
from django.utils import timezone

from . import puzzles, srs
from .models import Card, Session

QUEUE_SIZE = 150


def pool():
    return Card.objects.filter(in_solution=True, puzzle__active=True).select_related("puzzle__position")


def new_left_today(now=None) -> int:
    now = now or timezone.now()
    start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    introduced = Card.objects.filter(introduced_at__gte=start).count()
    return max(0, srs.NEW_PER_DAY - introduced)


def counts(now=None) -> dict:
    now = now or timezone.now()
    cards = pool()
    return {
        "learning": cards.filter(state__in=["learning", "relearning"], due__lte=now).count(),
        "review": cards.filter(state="review", due__lte=now).count(),
        "new": min(cards.filter(state="new").count(), new_left_today(now)),
        "new_total": cards.filter(state="new").count(),
        "cards": cards.count(),
        "puzzles": cards.values("puzzle").distinct().count(),
        "next_due": cards.exclude(state="new").filter(due__gt=now).order_by("due").values_list("due", flat=True).first(),
    }


def review_queue(now=None) -> list[Card]:
    now = now or timezone.now()
    cards = pool()
    learning = list(cards.filter(state__in=["learning", "relearning"], due__lte=now).order_by("due"))
    reviews = list(cards.filter(state="review", due__lte=now).order_by("due"))
    new = list(cards.filter(state="new").order_by("created_at", "id")[: new_left_today(now)])
    return (learning + reviews + new)[:QUEUE_SIZE]


def run_queue(rng: random.Random) -> list[Card]:
    """One random card per puzzle, easy to hard (Storm, Streak)."""
    by_puzzle = {}
    for card in pool().order_by("?")[: QUEUE_SIZE * 3]:
        by_puzzle.setdefault(card.puzzle_id, card)
    cards = list(by_puzzle.values())[:QUEUE_SIZE]
    rng.shuffle(cards)
    return sorted(cards, key=puzzles.difficulty)


def mirror_for(card: Card, side: str, rng: random.Random) -> bool:
    """Whether to mirror so the solver plays the wanted colour ("move": as it is)."""
    solver = card.puzzle.start_fen.split()[1]
    if side == "white":
        return solver == "b"
    if side == "black":
        return solver == "w"
    if side == "random":
        return rng.random() < 0.5
    return False


def start(mode: str, options: dict) -> Session:
    rng = random.Random()
    if options.get("cards"):  # given cards, in the given order ("review the missed ones")
        found = {str(c.uuid): c for c in pool().filter(uuid__in=options["cards"])}
        queue = [found[i] for i in options.pop("cards") if i in found]
    elif mode == Session.Mode.REVIEW:
        queue = review_queue()
    else:
        queue = run_queue(rng)
    side = options.get("side", "move")
    options = options | {
        "queue": [str(c.uuid) for c in queue],
        "mirror": [str(c.uuid) for c in queue if mirror_for(c, side, rng)],
    }
    return Session.objects.create(mode=mode, options=options)


def batch(session: Session, offset: int, size: int = 10) -> list[dict]:
    ids = session.options.get("queue", [])[offset : offset + size]
    mirrored = set(session.options.get("mirror", []))
    cards = {str(c.uuid): c for c in pool().filter(uuid__in=ids)}
    first_only = bool(session.options.get("first_move"))
    return [puzzles.payload(cards[i], mirrored=i in mirrored, first_only=first_only) for i in ids if i in cards]


def last_options() -> dict | None:
    last = Session.objects.exclude(Q(ended_at=None) & Q(solved=0) & Q(failed=0)).first()
    if not last:
        return None
    keep = ("minutes", "lives", "look", "side", "first_move", "pace")
    return {"mode": last.mode, **{k: v for k, v in last.options.items() if k in keep}}


def records() -> dict:
    """Best Storm score per length, best Streak per number of lives."""
    out = {"storm": {}, "streak": {}}
    for s in Session.objects.filter(mode=Session.Mode.STORM).exclude(ended_at=None):
        m = s.options.get("minutes", 3)
        out["storm"][m] = max(out["storm"].get(m, 0), s.solved)
    for s in Session.objects.filter(mode=Session.Mode.STREAK).exclude(ended_at=None):
        lives = s.options.get("lives", 0)
        out["streak"][lives] = max(out["streak"].get(lives, 0), s.streak)
    return out

