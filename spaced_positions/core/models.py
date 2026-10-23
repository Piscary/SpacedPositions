"""UI state that survives reloads (spec 09 §8). The app is local and single-user for now, but every row has a
`user` key so hosting later needs no redesign; locally it is always "local"."""

from django.db import models

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
        return cls.objects.get_or_create(user=LOCAL_USER)[0]
