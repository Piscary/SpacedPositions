"""The analysis of a position (spec 04 · Analyse): a move tree with one root, and the undo journal (spec 09 §5).

Node      one node per move; the root (uci "") is the position itself and holds the root comment and its
          drawings. Children are ordered: the first is the main continuation.
Journal   every change to an analysis keeps a snapshot of the tree before and after (tree.py), so `u` / `U` can
          undo and redo it, also after a reload.
"""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from spaced_positions.core.models import LOCAL_USER
from spaced_positions.training.models import Position


class Node(models.Model):
    class Mark(models.TextChoices):
        NONE = "", _("None")
        GOOD = "good", _("Good")
        DUBIOUS = "dubious", _("Dubious")
        BAD = "bad", _("Bad")

    # The owner of the tree: a position or a game, exactly one of the two (spec 11 §1 Game). No index of their own:
    # the (position, parent) and (game, parent) indexes start with them.
    position = models.ForeignKey(Position, null=True, blank=True, on_delete=models.CASCADE, related_name="nodes", db_index=False)
    game = models.ForeignKey("library.Game", null=True, blank=True, on_delete=models.CASCADE, related_name="nodes", db_index=False)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="kids")
    order = models.PositiveSmallIntegerField(default=0)
    uci = models.CharField(max_length=5, blank=True)
    san = models.CharField(max_length=12, blank=True)
    ply = models.PositiveSmallIntegerField(default=0)
    fen = models.CharField(max_length=100, help_text="The position after the move (the root: the start)")
    comment = models.TextField(blank=True)
    nags = models.JSONField(default=list, blank=True, help_text="Annotation symbols as NAG numbers: [1, 16] = ! and ±")
    mark = models.CharField(max_length=8, choices=Mark.choices, blank=True)
    color = models.CharField(max_length=7, blank=True, help_text="A free line colour (hex)")
    shapes = models.JSONField(default=list, blank=True, help_text="Arrows and circles (chessground shapes)")
    squares = models.JSONField(default=dict, blank=True, help_text="Filled squares {e4: 'green'}")
    tags = models.ManyToManyField("library.Tag", through="library.NodeTag", related_name="nodes", blank=True)
    # the engine's evaluation of the position after the move, from white's side (`:evaluate`, the eval graph)
    eval_cp = models.IntegerField(null=True, blank=True)
    eval_mate = models.SmallIntegerField(null=True, blank=True)
    eval_depth = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]
        indexes = [models.Index(fields=["position", "parent"]), models.Index(fields=["game", "parent"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(position__isnull=False, game__isnull=True) | models.Q(position__isnull=True, game__isnull=False),
                name="node_has_one_owner",
            )
        ]

    @property
    def owner(self):
        """The position or game whose tree this is."""
        return self.position if self.position_id else self.game

    @property
    def is_root(self) -> bool:
        return self.parent_id is None


class JournalEntry(models.Model):
    user = models.CharField(max_length=64, default=LOCAL_USER)
    label = models.CharField(max_length=120)
    position = models.ForeignKey(Position, null=True, blank=True, on_delete=models.CASCADE, related_name="journal")
    game = models.ForeignKey("library.Game", null=True, blank=True, on_delete=models.CASCADE, related_name="journal")
    before = models.JSONField()
    after = models.JSONField()
    undone = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-id"]
