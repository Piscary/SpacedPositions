"""Achievements (spec 05 · H, 04 · Stats): milestones, records and level-ups, dated and announced once."""

from django.db import models
from django.utils import timezone


class Achievement(models.Model):
    class Kind(models.TextChoices):
        LIBRARY = "library", "Pattern library"
        DAYSTREAK = "daystreak", "Days in a row"
        RETENTION = "retention", "Retention"
        STORM = "storm", "Storm"
        STREAK = "streak", "Streak"
        RECORD = "record", "Record"
        LEVEL = "level", "Level-up"

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


class ActivityLog(models.Model):
    """Activity that left no other trace here: the old app's analysis work (phase 7). Stats count it with the rest."""

    class Kind(models.TextChoices):
        COLLECT = "collect", "Collect"
        ANALYSE = "analyse", "Analyse"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    points = models.SmallIntegerField(default=1)
    at = models.DateTimeField(db_index=True)
    label = models.CharField(max_length=200, blank=True)
    origin = models.CharField(max_length=40, unique=True)

    class Meta:
        ordering = ["at"]
