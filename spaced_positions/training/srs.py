"""Spaced repetition from solved / missed only: no self-rating.

    new, learning   steps of LEARNING_STEPS (10 minutes, 1 day); solving the last step graduates the card to review
                    with an interval of GRADUATE_DAYS
    review, solved  interval × ease (at least one day more than before); after EASE_STREAK solves in a row the ease
                    grows by EASE_BONUS (up to EASE_MAX): cards that are always solved drift further apart
    review, missed  a lapse: ease − EASE_PENALTY (not below EASE_MIN), interval × LAPSE_FACTOR, relearn in RELEARN_STEP
    relearning      solved → back to review with the shrunk interval; missed → again in RELEARN_STEP
    not yet due     a solve before the due date (Storm, Streak) is logged but doesn't push the card further out; a miss
                    always counts
    hinted          counts as missed (spec 10 · decision 11)

Intervals get a small, stable per-card fuzz (±5 %) so cards learned together don't stay together.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

LEARNING_STEPS = (timedelta(minutes=10), timedelta(days=1))
RELEARN_STEP = timedelta(minutes=10)
GRADUATE_DAYS = 3.0
EASE_START, EASE_MIN, EASE_MAX = 2.5, 1.3, 3.0
EASE_BONUS, EASE_PENALTY, EASE_STREAK = 0.05, 0.2, 3
LAPSE_FACTOR = 0.3
MAX_INTERVAL = 365.0
NEW_PER_DAY = 20


@dataclass
class Outcome:
    counted: bool
    state_before: str
    interval_before: float
    due_before: datetime
    interval: float
    due: datetime


def _fuzz(card, days: float) -> float:
    if days < 2:
        return days
    return days * (1 + (((card.pk or 0) * 37) % 11 - 5) / 100)


def review(card, success: bool, now=None) -> Outcome:
    """Apply one attempt to `card` (in place, not saved) and say what happened."""
    now = now or timezone.now()
    before, interval_before, due_before = card.state, card.interval_days, card.due
    due_now = card.due <= now or card.state == "new"
    if success and not due_now:
        return Outcome(False, before, interval_before, due_before, card.interval_days, card.due)

    if success:
        card.success_streak += 1
        if card.state in ("new", "learning"):
            card.step = card.step + 1 if card.state == "learning" else 1
            if card.step >= len(LEARNING_STEPS):
                card.state, card.step = "review", 0
                card.interval_days = _fuzz(card, GRADUATE_DAYS)
                card.due = now + timedelta(days=card.interval_days)
            else:
                card.state = "learning"
                card.due = now + LEARNING_STEPS[card.step]
        elif card.state == "relearning":
            card.state = "review"
            card.interval_days = max(1.0, card.interval_days)
            card.due = now + timedelta(days=card.interval_days)
        else:
            if card.success_streak >= EASE_STREAK:
                card.ease = min(EASE_MAX, card.ease + EASE_BONUS)
            card.interval_days = min(MAX_INTERVAL, max(card.interval_days + 1, _fuzz(card, card.interval_days * card.ease)))
            card.due = now + timedelta(days=card.interval_days)
        card.reps += 1
    else:
        card.success_streak = 0
        if card.state == "review":
            card.lapses += 1
            card.ease = max(EASE_MIN, card.ease - EASE_PENALTY)
            card.interval_days = max(1.0, card.interval_days * LAPSE_FACTOR)
            card.state = "relearning"
            card.due = now + RELEARN_STEP
        elif card.state == "relearning":
            card.due = now + RELEARN_STEP
        else:
            card.state, card.step = "learning", 0
            card.due = now + LEARNING_STEPS[0]
    return Outcome(True, before, interval_before, due_before, card.interval_days, card.due)


def record(card, success: bool, ms: int = 0, now=None) -> Outcome:
    """Statistics of an attempt (always) and the schedule (when it counts). The card is not saved."""
    now = now or timezone.now()
    if card.introduced_at is None:
        card.introduced_at = now
    outcome = review(card, success, now)
    card.attempts += 1
    card.successes += 1 if success else 0
    card.total_ms += max(0, int(ms))
    if success and ms and (card.best_ms is None or ms < card.best_ms):
        card.best_ms = int(ms)
    card.last_result = success
    card.last_seen = now
    return outcome


def describe_due(due, now=None) -> str:
    """'in 10 minutes', 'tomorrow', 'in 9 days'."""
    from django.utils.translation import gettext, ngettext

    now = now or timezone.now()
    seconds = (due - now).total_seconds()
    if seconds < 90:
        return gettext("now")
    if seconds < 3600:
        n = round(seconds / 60)
        return ngettext("in {n} minute", "in {n} minutes", n).format(n=n)
    if seconds < 86400:
        n = round(seconds / 3600)
        return ngettext("in {n} hour", "in {n} hours", n).format(n=n)
    days = round(seconds / 86400)
    return gettext("tomorrow") if days == 1 else ngettext("in {n} day", "in {n} days", days).format(n=days)
