"""Positions, puzzles and the training history (spec 04 · objects, Train).

Position   a FEN with what identifies and describes it. Minimal in phase 2: phase 4 adds tags, sources and the
           library; phase 3 adds the analysis (move tree).
Puzzle     a trainable problem: a start position and a solution tree (puzzles.py). Self-contained, so a puzzle
           doesn't depend on an analysis staying as it is.
Card       one answer line of a puzzle, the unit of spaced repetition (srs.py): a puzzle whose solution lets the
           opponent answer in three ways trains three cards.
Session    one training run (Review, Storm, Streak, custom); Attempt one puzzle in it.
"""

import uuid

from django.db import models
from django.utils import timezone


class Position(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    fen = models.CharField(max_length=100)
    canonical = models.CharField(max_length=90, db_index=True, help_text="placement, side, castling, legal e.p.")
    title = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=300, blank=True, help_text="Citation as text (phase 4: a Source)")
    objective = models.CharField(max_length=120, blank=True, help_text="Task line, e.g. 'Mate in 2'")
    difficulty = models.PositiveSmallIntegerField(null=True, blank=True, help_text="1–5")
    tag_names = models.JSONField(default=list, blank=True, help_text="Shown in feedback until phase 4 brings tags")
    origin = models.CharField(max_length=40, blank=True, db_index=True, help_text="Where it came from: board, csm:<id> …")
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.title or self.fen


class Puzzle(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name="puzzles")
    start_fen = models.CharField(max_length=100, help_text="The position the solver sees (a game puzzle starts later)")
    solution = models.JSONField(help_text="The solution tree, see puzzles.py")
    active = models.BooleanField(default=True, help_text="In the training pool")
    flagged = models.BooleanField(default=False, help_text="Marked as broken in training (`!`)")
    origin = models.CharField(max_length=40, blank=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    start_node = models.ForeignKey(
        "analysis.Node", null=True, blank=True, on_delete=models.SET_NULL, related_name="puzzles",
        help_text="Set up in the analysis: the solution is rebuilt from the tree (analysis/puzzles.py)",
    )
    marks = models.JSONField(
        default=dict, blank=True,
        help_text='{"ends": [node ids], "also": [ids], "replies": [ids]}: where lines stop, further correct moves, further answers',
    )

    def __str__(self):
        return f"Puzzle {self.pk} · {self.position}"


class Card(models.Model):
    class State(models.TextChoices):
        NEW = "new", "New"
        LEARNING = "learning", "Learning"
        REVIEW = "review", "Review"
        RELEARNING = "relearning", "Relearning"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE, related_name="cards")
    line_key = models.CharField(max_length=400, help_text="The line's moves in UCI, space-separated")
    line = models.JSONField(help_text="[uci, …]: solver move, answer, solver move …")
    in_solution = models.BooleanField(default=True, help_text="Off when the solution no longer has this line")
    created_at = models.DateTimeField(default=timezone.now)

    state = models.CharField(max_length=10, choices=State.choices, default=State.NEW, db_index=True)
    due = models.DateTimeField(default=timezone.now, db_index=True)
    interval_days = models.FloatField(default=0)
    ease = models.FloatField(default=2.5)
    step = models.PositiveSmallIntegerField(default=0)
    reps = models.PositiveIntegerField(default=0)
    lapses = models.PositiveIntegerField(default=0)
    success_streak = models.PositiveIntegerField(default=0)

    attempts = models.PositiveIntegerField(default=0)
    successes = models.PositiveIntegerField(default=0)
    total_ms = models.BigIntegerField(default=0)
    best_ms = models.PositiveIntegerField(null=True, blank=True)
    last_result = models.BooleanField(null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    introduced_at = models.DateTimeField(null=True, blank=True, help_text="First attempt (the daily limit of new cards)")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["puzzle", "line_key"], name="card_per_puzzle_line")]

    @property
    def stage(self) -> str:
        """new · learning · young · mature (spec · Progress)."""
        if self.state == self.State.NEW:
            return "new"
        if self.state in (self.State.LEARNING, self.State.RELEARNING):
            return "learning"
        return "mature" if self.interval_days >= 21 else "young"


class Session(models.Model):
    class Mode(models.TextChoices):
        REVIEW = "review", "Review"
        STORM = "storm", "Storm"
        STREAK = "streak", "Streak"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    mode = models.CharField(max_length=8, choices=Mode.choices)
    options = models.JSONField(default=dict, blank=True, help_text="minutes, lives, look, side, first_move, pace")
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    solved = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    best_combo = models.PositiveIntegerField(default=0)
    streak = models.PositiveIntegerField(default=0)
    duration_s = models.PositiveIntegerField(null=True, blank=True, help_text="Time actually played")

    class Meta:
        ordering = ["-started_at"]

    @property
    def score(self) -> int:
        return self.streak if self.mode == self.Mode.STREAK else self.solved

    @property
    def label(self) -> str:
        o = self.options
        if self.mode == self.Mode.STORM:
            return f"Storm {o.get('minutes', 3)}′"
        if self.mode == self.Mode.STREAK:
            lives = o.get("lives", 0)
            return "Streak" + (f" ♥{lives}" if lives else "") + (" · blind" if o.get("look") == "blind" else "")
        return "Review"


class Attempt(models.Model):
    card = models.ForeignKey(Card, on_delete=models.PROTECT, related_name="attempt_log", help_text="PROTECT: trained cards can't be deleted by a cascade")
    session = models.ForeignKey(Session, null=True, blank=True, on_delete=models.SET_NULL, related_name="attempts")
    at = models.DateTimeField(default=timezone.now, db_index=True)
    success = models.BooleanField()
    ms = models.PositiveIntegerField(default=0)
    hinted = models.BooleanField(default=False)
    gave_up = models.BooleanField(default=False)
    wrong_move = models.CharField(max_length=8, blank=True)
    mode = models.CharField(max_length=8, blank=True)
    look = models.CharField(max_length=12, blank=True)
    first_move_only = models.BooleanField(default=False)
    counted = models.BooleanField(default=True, help_text="Changed the schedule (a solve before the due date doesn't)")
    state_before = models.CharField(max_length=10, blank=True)
    interval_before = models.FloatField(null=True, blank=True)
    interval_after = models.FloatField(default=0)
    due_before = models.DateTimeField(null=True, blank=True)
    solved_as = models.CharField(max_length=1, blank=True, help_text="w / b")
    mirrored = models.BooleanField(default=False)
    flipped = models.BooleanField(default=False, help_text="The solver's side was at the top")

    class Meta:
        ordering = ["-at"]
