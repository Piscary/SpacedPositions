"""Achievements (spec 05 · H, 04 · Stats): milestones, records and level-ups, dated and announced once."""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Achievement(models.Model):
    class Kind(models.TextChoices):
        LIBRARY = "library", _("Pattern library")
        DAYSTREAK = "daystreak", _("Days in a row")
        RETENTION = "retention", _("Retention")
        STORM = "storm", _("Storm")
        STREAK = "streak", _("Streak")
        RECORD = "record", _("Record")
        LEVEL = "level", _("Level-up")

    kind = models.CharField(max_length=10, choices=Kind.choices)
    key = models.CharField(max_length=100, blank=True, help_text="records: storm-5, streak-0 · level-ups: the tag key")
    value = models.IntegerField()
    label = models.CharField(max_length=200)
    reached_at = models.DateTimeField(default=timezone.now)
    session = models.ForeignKey("training.Session", null=True, blank=True, on_delete=models.SET_NULL, related_name="achievements")
    seen = models.BooleanField(default=False, help_text="Announced (status line, Home)")

    class Meta:
        ordering = ["-reached_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["kind", "key", "value"], name="achievement_once")]

    def __str__(self):
        return self.label

    @property
    def text(self) -> str:
        """The label in the language of the request (the stored label is in the language it was reached in)."""
        from spaced_positions.library.models import Tag

        from . import metrics

        if self.kind in metrics.MILESTONE_TEXT:
            return metrics.milestone_text(self.kind, self.value)
        if self.kind == self.Kind.RECORD:
            return metrics.record_label(self.key, self.value)
        tag = Tag.objects.filter(key=self.key).first() if self.kind == self.Kind.LEVEL else None
        if tag is not None and 1 <= self.value < len(metrics.LEVELS):
            return metrics.level_text(tag, self.value)
        return self.label


class ActivityLog(models.Model):
    """Activity that left no other trace here (e.g. analysis work brought in by an import). Stats count it with the rest."""

    class Kind(models.TextChoices):
        COLLECT = "collect", _("Collect")
        ANALYSE = "analyse", _("Analyse")

    kind = models.CharField(max_length=10, choices=Kind.choices)
    points = models.SmallIntegerField(default=1)
    at = models.DateTimeField(db_index=True)
    label = models.CharField(max_length=200, blank=True)
    origin = models.CharField(max_length=40, unique=True)

    class Meta:
        ordering = ["at"]
