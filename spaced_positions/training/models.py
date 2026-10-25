"""Positions, puzzles and the training history (spec 04 · objects, Train).

Position   a FEN with what identifies and describes it, and its analysis (analysis.Node, the move tree). Phase 4
           adds tags, sources and the library.
Puzzle     a trainable problem: a start position and a solution tree (puzzles.py). Self-contained, so a puzzle
           doesn't depend on an analysis staying as it is.
Card       one answer line of a puzzle, the unit of spaced repetition (srs.py): a puzzle whose solution lets the
           opponent answer in three ways trains three cards.
Session    one training run (Review, Storm, Streak, custom); Attempt one puzzle in it.
"""

import uuid

from django.db import models
from django.utils import timezone


class AliveManager(models.Manager):
    """Without the trash (spec 11: deleting moves to the trash)."""

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at=None)


PIECE_ORDER = "KQRBNP"


def material_of(fen: str) -> tuple[str, int]:
    """('KQRvKR', 5): white's pieces, 'v', black's, strongest first; and the number of pieces."""
    placement = fen.split()[0] if fen else ""
    white = sorted((c for c in placement if c in PIECE_ORDER), key=PIECE_ORDER.index)
    black = sorted((c.upper() for c in placement if c in PIECE_ORDER.lower()), key=PIECE_ORDER.index)
    return f"{''.join(white)}v{''.join(black)}", len(white) + len(black)


SEARCHED = {"title", "description", "objective", "notes", "source_text", "source_page", "source_ref"}


def search_text(position) -> str:
    """What a word of the Library's search looks in (the source, tags and comments are searched where they are)."""
    from spaced_positions.library.text import fold

    return fold(" ".join(str(getattr(position, f) or "") for f in ("title", "objective", "description", "notes", "source_text")))


def first_number(text) -> int | None:
    """'Nr. 12' → 12, '41-42' → 41: page and diagram numbers sort as numbers."""
    import re

    m = re.search(r"\d+", str(text or ""))
    return int(m.group()[:9]) if m else None


class Position(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    fen = models.CharField(max_length=100)
    canonical = models.CharField(max_length=90, db_index=True, help_text="placement, side, castling, legal e.p.")
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True, help_text="The task as shown with the diagram (Markdown)")
    notes = models.TextField(blank=True, help_text="Private working notes (Markdown)")
    source = models.ForeignKey("library.Source", null=True, blank=True, on_delete=models.SET_NULL, related_name="positions")
    source_page = models.CharField(max_length=40, blank=True)
    source_ref = models.CharField(max_length=300, blank=True, help_text="Diagram number, puzzle id or URL path")
    source_text = models.CharField(max_length=300, blank=True, help_text="The citation as text (imports; unmatched)")
    objective = models.CharField(max_length=120, blank=True, help_text="Task line, e.g. 'Mate in 2'")
    difficulty = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True, help_text="1–5: the override, else the automatic value")
    difficulty_override = models.PositiveSmallIntegerField(null=True, blank=True)
    difficulty_auto = models.PositiveSmallIntegerField(null=True, blank=True)
    tags = models.ManyToManyField("library.Tag", through="library.PositionTag", related_name="positions", blank=True)
    diagram = models.BooleanField(default=False, help_text="An illustration: shown, never trained, may be illegal")
    game = models.ForeignKey("library.Game", null=True, blank=True, on_delete=models.SET_NULL, related_name="positions")
    game_node = models.ForeignKey("analysis.Node", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    side = models.CharField(max_length=1, default="w", editable=False)
    material = models.CharField(max_length=40, blank=True, db_index=True, editable=False)
    pieces = models.PositiveSmallIntegerField(default=0, editable=False)
    origin = models.CharField(max_length=40, blank=True, help_text="Where it came from: board, csm:<id> …")
    search = models.TextField(blank=True, editable=False, help_text="Folded title, description, task, notes and citation")
    page_number = models.PositiveIntegerField(null=True, blank=True, editable=False, help_text="The page as a number: sorts 9 before 10")
    ref_number = models.PositiveIntegerField(null=True, blank=True, editable=False, help_text="The diagram number as a number")
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    alive = AliveManager()

    class Meta:
        base_manager_name = "objects"

    def save(self, *args, **kwargs):
        parts = (self.fen or "").split()
        self.side = parts[1] if len(parts) > 1 and parts[1] in "wb" else "w"
        self.material, self.pieces = material_of(self.fen)
        self.difficulty = self.difficulty_override or self.difficulty_auto
        self.search = search_text(self)
        self.page_number, self.ref_number = first_number(self.source_page), first_number(self.source_ref)
        fields = kwargs.get("update_fields")
        if fields is not None:
            fields = set(fields)
            if "fen" in fields:
                fields |= {"side", "material", "pieces"}
            if fields & {"difficulty_override", "difficulty_auto"}:
                fields.add("difficulty")
            if fields & SEARCHED:
                fields.add("search")
            if fields & {"source_page", "source_ref"}:
                fields |= {"page_number", "ref_number"}
            kwargs["update_fields"] = fields | {"updated_at"}
        super().save(*args, **kwargs)

    @property
    def short_id(self) -> str:
        return f"p{self.pk}"

    @property
    def tag_names(self) -> list[str]:
        """Names of its tags in field order (prefetch `tag_links__tag__field` for lists)."""
        links = sorted(self.tag_links.all(), key=lambda link: (link.tag.field.order, link.tag.order, link.tag.id))
        return [link.tag.name for link in links if link.origin != "suggested"]

    @property
    def task(self) -> str:
        return self.task_for(self.side)

    def task_for(self, side: str) -> str:
        """The objective line: set by hand, else the task of its objective tag ('White to play and mate in 2'), for
        the side that solves (a mirrored puzzle is solved by the other colour)."""
        if self.objective:
            return self.objective
        for link in self.tag_links.all():
            if link.tag.field.key == "goal" and link.tag.task_en and link.origin != "suggested":
                return link.tag.task_en.replace("{side}", "White" if side == "w" else "Black")
        return ""

    @property
    def citation(self) -> str:
        if self.source_id and self.source.kind == "pack":  # the pack, who it's from and for, then the book it cites
            received = getattr(self.source, "pack", None)
            name = f"{self.source.label} ({received.credit})" if received and received.credit else self.source.label
            return " · ".join(x for x in [name, self.source_text] if x)
        if self.source_id:
            ref = " · ".join(x for x in [f"p. {self.source_page}" if self.source_page else "", self.source_ref] if x)
            return " · ".join(x for x in [self.source.label, ref] if x)
        return self.source_text

    def __str__(self):
        return self.title or self.fen


class Puzzle(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name="puzzles")
    start_fen = models.CharField(max_length=100, help_text="The position the solver sees (a game puzzle starts later)")
    solution = models.JSONField(help_text="The solution tree, see puzzles.py")
    active = models.BooleanField(default=True, help_text="In the training pool")
    flagged = models.BooleanField(default=False, help_text="Marked as broken in training (`!`)")
    origin = models.CharField(max_length=40, blank=True)
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
    origin = models.CharField(max_length=40, blank=True, db_index=True, help_text="Where it came from: csm-…:<id> (phase 7)")

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
            return ("Streak" + (f" ♥{lives}" if lives else "") + (" · blind" if o.get("look") == "blind" else "")
                    + (" · weakest motifs" if o.get("weakest") else ""))
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
    origin = models.CharField(max_length=40, blank=True, help_text="Where it came from: csm-…:<id> (phase 7)")

    class Meta:
        ordering = ["-at"]
