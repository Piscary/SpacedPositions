"""Coaching (spec 17). The coach's side: lessons (material in an order, with notes), assignments (a lesson sent as
homework) and the results students send back. The student's side: the homework received with a pack."""

import uuid

from django.db import models
from django.utils import timezone

from spaced_positions.core.models import LOCAL_USER


class Lesson(models.Model):
    user = models.CharField(max_length=64, default=LOCAL_USER)
    title = models.CharField(max_length=120)
    notes = models.TextField(blank=True)
    pack = models.ForeignKey("library.Pack", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                             help_text="The pack its homework goes out as (one per lesson: a newer homework is a new version)")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title


class LessonItem(models.Model):
    """A position or a game of a lesson, with the coach's note (what to ask, what to show)."""

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="items")
    order = models.PositiveIntegerField(default=0)
    position = models.ForeignKey("training.Position", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    game = models.ForeignKey("library.Game", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["order", "id"]


class Assignment(models.Model):
    """Homework sent out: which positions, with which instructions; results name its uuid."""

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    lesson = models.ForeignKey(Lesson, null=True, blank=True, on_delete=models.SET_NULL, related_name="assignments")
    title = models.CharField(max_length=120)
    instructions = models.TextField(blank=True)
    due = models.DateField(null=True, blank=True)
    positions = models.JSONField(default=list, help_text="Position uuids, in the lesson's order")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]


class HomeworkResult(models.Model):
    """What one student sent back for one assignment (a results file); a newer file replaces it."""

    assignment = models.CharField(max_length=36, db_index=True)
    student = models.CharField(max_length=120)
    data = models.JSONField(default=dict)
    received_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["assignment", "student"], name="result_assignment_student")]


class Homework(models.Model):
    """The student's side: homework that came with a pack."""

    assignment = models.CharField(max_length=36, unique=True)
    title = models.CharField(max_length=120)
    coach = models.CharField(max_length=120, blank=True)
    instructions = models.TextField(blank=True)
    due = models.DateField(null=True, blank=True)
    positions = models.JSONField(default=list, help_text="Position uuids, in the coach's order")
    received_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True, help_text="When the results file was last written")

    class Meta:
        ordering = ["due", "-received_at"]
