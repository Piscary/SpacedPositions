"""The library's objects (spec 11 §1): sources, players, tags in fields, tag presets, saved queries and games.
Positions stay in training/ (they came first); their tags and sources point here."""

import uuid

from django.db import models
from django.utils import timezone

from .text import fold


class Source(models.Model):
    class Kind(models.TextChoices):
        BOOK = "book", "Book"
        WEBSITE = "website", "Website"
        OWN = "own", "Own analysis"
        PUBLIC = "public", "Public domain"
        COURSE = "course", "Course"

    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.BOOK)
    title = models.CharField(max_length=300)
    short = models.CharField(max_length=80, blank=True, help_text="Citation stem shown in lists: 'Polgár 5334'")
    authors = models.CharField(max_length=300, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    publisher = models.CharField(max_length=200, blank=True)
    isbn = models.CharField(max_length=20, blank=True)
    url = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    search = models.TextField(blank=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["title"]

    def save(self, *args, **kwargs):
        self.search = fold(" ".join([self.title, self.short, self.authors, self.publisher]))
        super().save(*args, **kwargs)

    @property
    def label(self) -> str:
        return self.short or self.title

    def __str__(self):
        return self.label


class Player(models.Model):
    class Role(models.TextChoices):
        NONE = "", "—"
        ME = "me", "Me"
        STUDENT = "student", "Student"
        MODEL = "model", "Role model"
        OPPONENT = "opponent", "Opponent"

    key = models.SlugField(max_length=60, unique=True, help_text="@key in queries")
    name = models.CharField(max_length=150, help_text="'Tal, Mikhail'")
    aliases = models.JSONField(default=list, blank=True, help_text="Other spellings and online handles")
    role = models.CharField(max_length=10, choices=Role.choices, blank=True, default="")
    title = models.CharField(max_length=8, blank=True)
    federation = models.CharField(max_length=3, blank=True)
    fide_id = models.CharField(max_length=12, blank=True)
    born = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    search = models.TextField(blank=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        self.search = fold(" ".join([self.name, *self.aliases]))
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class TagField(models.Model):
    class Selection(models.TextChoices):
        SINGLE = "single", "One tag"
        MULTI = "multi", "Several tags"

    key = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80, help_text="German name")
    name_en = models.CharField(max_length=80, blank=True)
    selection = models.CharField(max_length=6, choices=Selection.choices, default=Selection.MULTI)
    on_positions = models.BooleanField(default=True)
    on_moves = models.BooleanField(default=True)
    color = models.CharField(max_length=12, default="chart-6", help_text="A chart token: chart-1 … chart-6")
    description = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.name


class Tag(models.Model):
    field = models.ForeignKey(TagField, on_delete=models.PROTECT, related_name="tags")
    key = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=100, help_text="German display name")
    name_en = models.CharField(max_length=100, blank=True)
    aliases = models.JSONField(default=list, blank=True, help_text="More search terms, any language")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    description = models.TextField(blank=True)
    task = models.CharField(max_length=120, blank=True, help_text="Objective tags: the task, {side} = Weiß/Schwarz")
    task_en = models.CharField(max_length=120, blank=True)
    base_difficulty = models.PositiveSmallIntegerField(default=2)
    weight = models.FloatField(default=1.0, help_text="How much it counts for a position's difficulty (0: not at all)")
    analysis_weight = models.FloatField(default=0.0, help_text="How much it counts as a move tag of the analysis")
    order = models.PositiveSmallIntegerField(default=0)
    search = models.TextField(blank=True, editable=False, help_text="Folded key, names and aliases")

    class Meta:
        ordering = ["field__order", "order", "id"]

    def save(self, *args, **kwargs):
        self.search = " | ".join(fold(x) for x in [self.key, self.name, self.name_en, *self.aliases] if x)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class TagLink(models.Model):
    class Origin(models.TextChoices):
        MANUAL = "manual", "By hand"
        AUTO = "auto", "Detected"
        SUGGESTED = "suggested", "Suggested"

    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="+")
    origin = models.CharField(max_length=10, choices=Origin.choices, default=Origin.MANUAL)
    detector = models.CharField(max_length=40, blank=True)
    evidence = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        abstract = True


class PositionTag(TagLink):
    position = models.ForeignKey("training.Position", on_delete=models.CASCADE, related_name="tag_links")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["position", "tag"], name="position_tag_once")]


class NodeTag(TagLink):
    node = models.ForeignKey("analysis.Node", on_delete=models.CASCADE, related_name="tag_links")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["node", "tag"], name="node_tag_once")]


class GameTag(TagLink):
    game = models.ForeignKey("library.Game", on_delete=models.CASCADE, related_name="tag_links")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["game", "tag"], name="game_tag_once")]


class TagDismissal(models.Model):
    """A tag the user removed from a position or a move: detection never adds it there again."""

    position = models.ForeignKey("training.Position", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    node = models.ForeignKey("analysis.Node", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["position", "node", "tag"], name="dismissed_once")]


class TagPreset(models.Model):
    name = models.CharField(max_length=80)
    tags = models.ManyToManyField(Tag, related_name="presets")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]


class SavedQuery(models.Model):
    key = models.SlugField(max_length=60, unique=True, help_text="q:key in queries")
    name = models.CharField(max_length=120)
    collection = models.CharField(max_length=12, default="positions")
    query = models.TextField()
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["order", "name"]


class Game(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    white = models.ForeignKey(Player, null=True, blank=True, on_delete=models.SET_NULL, related_name="white_games")
    black = models.ForeignKey(Player, null=True, blank=True, on_delete=models.SET_NULL, related_name="black_games")
    white_name = models.CharField(max_length=150, blank=True)
    black_name = models.CharField(max_length=150, blank=True)
    white_elo = models.PositiveSmallIntegerField(null=True, blank=True)
    black_elo = models.PositiveSmallIntegerField(null=True, blank=True)
    result = models.CharField(max_length=8, default="*")
    date = models.CharField(max_length=20, blank=True, help_text="PGN form: 1956.??.??")
    year = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    event = models.CharField(max_length=200, blank=True)
    site = models.CharField(max_length=200, blank=True)
    round = models.CharField(max_length=20, blank=True)
    eco = models.CharField(max_length=6, blank=True, db_index=True)
    annotator = models.CharField(max_length=150, blank=True)
    headers = models.JSONField(default=dict, blank=True, help_text="All other PGN headers")
    start_fen = models.CharField(max_length=100)
    pgn = models.TextField(blank=True, help_text="As imported")
    dedupe = models.CharField(max_length=40, blank=True, db_index=True, help_text="Hash of players, result, first plies")
    source = models.ForeignKey(Source, null=True, blank=True, on_delete=models.SET_NULL, related_name="games")
    source_ref = models.CharField(max_length=300, blank=True)
    notes = models.TextField(blank=True)
    tags = models.ManyToManyField(Tag, through=GameTag, related_name="games", blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]

    @property
    def fen(self) -> str:
        """The start of the move tree (a tree owner has a `fen`, like a Position)."""
        return self.start_fen

    @property
    def title(self) -> str:
        players = f"{self.white_name or '?'} – {self.black_name or '?'}"
        return " ".join(x for x in [players, self.result if self.result != "*" else "", str(self.year or "")] if x)

    @property
    def short_id(self) -> str:
        return f"g{self.pk}"

    def __str__(self):
        return self.title
