"""UI state that survives reloads (spec 09 §8). The app is local and single-user for now, but every row has a
`user` key so hosting later needs no redesign; locally it is always "local"."""

from django.db import IntegrityError, models
from django.utils import timezone

LOCAL_USER = "local"


class UIState(models.Model):
    """Per mode: the layout tree, the focused pane and the mode's subject/cursor."""

    user = models.CharField(max_length=64, default=LOCAL_USER)
    mode = models.CharField(max_length=24)
    layout = models.JSONField(default=dict)
    focus = models.CharField(max_length=24, blank=True)
    subject = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "mode"], name="uistate_user_mode")]


class NamedLayout(models.Model):
    """`:layout save <name>`."""

    user = models.CharField(max_length=64, default=LOCAL_USER)
    name = models.CharField(max_length=60)
    mode = models.CharField(max_length=24)
    layout = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "name"], name="namedlayout_user_name")]


class Preferences(models.Model):
    """Theme, token overrides and other settings (spec 07 §5). `tokens` holds overrides on top of the theme,
    keyed by token name (`main`, `font-size`, ...)."""

    user = models.CharField(max_length=64, default=LOCAL_USER, unique=True)
    theme = models.CharField(max_length=60, default="")  # empty: follow the OS (paper / ink)
    tokens = models.JSONField(default=dict, blank=True)
    settings = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls) -> "Preferences":
        try:
            return cls.objects.get_or_create(user=LOCAL_USER)[0]
        except IntegrityError:  # created by a concurrent request (many MiniBoards load at once)
            return cls.objects.get(user=LOCAL_USER)


class UserTheme(models.Model):
    """A theme made in the app (spec 07 §4): a built-in theme it extends plus base-token values on top."""

    user = models.CharField(max_length=64, default=LOCAL_USER)
    name = models.SlugField(max_length=60)
    label = models.CharField(max_length=80)
    extends = models.CharField(max_length=60, default="paper")
    values = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["label"]
        constraints = [models.UniqueConstraint(fields=["user", "name"], name="user_theme_once")]


class KeymapOverride(models.Model):
    """A key bound by the user (`:map`, the keymap editor), or a default binding taken away (`:unmap`)."""

    user = models.CharField(max_length=64, default=LOCAL_USER)
    context = models.CharField(max_length=40, default="global")
    keys = models.CharField(max_length=60, help_text="Key tokens separated by spaces: 'space o', 'Q'")
    command = models.CharField(max_length=80, blank=True, help_text="Empty: unmapped")
    args = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["context", "keys"]
        constraints = [models.UniqueConstraint(fields=["user", "context", "keys"], name="keymap_override_once")]


class UsageCount(models.Model):
    """How often a command ran on a day, and how (spec 14 §5): the usage report's counts. Counts only, never what
    a command worked on; kept in this database and sent nowhere. `name` is a command id or `error.js` /
    `error.server` for the errors the app caught."""

    user = models.CharField(max_length=64, default=LOCAL_USER)
    day = models.DateField()
    name = models.CharField(max_length=80)
    source = models.CharField(max_length=10, help_text="key · mouse · hint · cmdline · error")
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "day", "name", "source"], name="usage_user_day_name_source")]
