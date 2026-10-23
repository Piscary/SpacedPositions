"""The analysis of a position (spec 04 · Analyse): a move tree with one root, and the undo journal (spec 09 §5).

Node      one node per move; the root (uci "") is the position itself and holds the root comment and its
          drawings. Children are ordered: the first is the main continuation.
Journal   every change to an analysis keeps a snapshot of the tree before and after (tree.py), so `u` / `U` can
          undo and redo it, also after a reload.
"""

from django.db import models
from django.utils import timezone

from spaced_positions.core.models import LOCAL_USER
from spaced_positions.training.models import Position


class Node(models.Model):
    class Mark(models.TextChoices):
        NONE = "", "None"
        GOOD = "good", "Good"
        DUBIOUS = "dubious", "Dubious"
        BAD = "bad", "Bad"

    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name="nodes")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="kids")
    order = models.PositiveSmallIntegerField(default=0)
    uci = models.CharField(max_length=5, blank=True)
    san = models.CharField(max_length=12, blank=True)
    ply = models.PositiveSmallIntegerField(default=0)
    fen = models.CharField(max_length=100, help_text="The position after the move (the root: the start)")
    comment = models.TextField(blank=True)
    nags = models.JSONField(default=list, blank=True, help_text="Annotation symbols: ['!', '+-'] …")
    mark = models.CharField(max_length=8, choices=Mark.choices, blank=True)
    color = models.CharField(max_length=7, blank=True, help_text="A free line colour (hex)")
    shapes = models.JSONField(default=list, blank=True, help_text="Arrows and circles (chessground shapes)")
    squares = models.JSONField(default=dict, blank=True, help_text="Filled squares {e4: 'green'}")

    class Meta:
        ordering = ["order", "id"]
        indexes = [models.Index(fields=["position", "parent"])]

    @property
    def is_root(self) -> bool:
        return self.parent_id is None


class JournalEntry(models.Model):
    user = models.CharField(max_length=64, default=LOCAL_USER)
    label = models.CharField(max_length=120)
    position = models.ForeignKey(Position, null=True, blank=True, on_delete=models.CASCADE, related_name="journal")
    before = models.JSONField()
    after = models.JSONField()
    undone = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-id"]
