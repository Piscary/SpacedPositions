"""Server handlers of commands (spec 09 §4). `POST /cmd/<id>/` with JSON `{"args": [...], "context": {...}}`.

A handler returns a dict: `message` for the status line, `effects` for the client (e.g. new theme CSS), and
optionally `oob` HTML fragments for htmx to swap in.
"""

from django.conf import settings

from spaced_positions.design import lib

from . import registry
from .models import LOCAL_USER, NamedLayout, Preferences

HANDLERS = {}
MODULES = ("spaced_positions.library.commands",)  # other apps' server commands


def handlers() -> dict:
    """Every server handler, with the other apps' command modules loaded."""
    import importlib

    for name in MODULES:
        importlib.import_module(name)
    return HANDLERS


class CommandError(Exception):
    """Shown to the user in the status line."""


def command(cid: str):
    registry.command(cid)  # fails at import time for an unknown id

    def register(fn):
        HANDLERS[cid] = fn
        return fn

    return register


def _theme_effects(prefs: Preferences) -> dict:
    from .chess_views import colors_hash

    return {
        "theme": {
            "name": prefs.theme,
            "css": registry.theme_css(prefs.theme, prefs.tokens),
            "tokens": prefs.tokens,
            "boardHash": colors_hash(),
        }
    }


@command("theme.set")
def theme_set(args, context, body):
    if not args:
        raise CommandError("which theme? e.g. :theme ink")
    name = args[0]
    if name not in registry.themes()["themes"] and name not in ("", "auto"):
        raise CommandError(f"no theme '{name}'")
    prefs = Preferences.current()
    previous = prefs.theme or "auto"
    prefs.theme = "" if name == "auto" else name
    prefs.save(update_fields=["theme", "updated_at"])
    label = registry.themes()["themes"].get(prefs.theme, {}).get("label", "follow the system")
    return {
        "message": f"Theme: {label}",
        "effects": _theme_effects(prefs),
        "undo": {"command": "theme.set", "args": [previous]},
        "redo": {"command": "theme.set", "args": [name]},
    }


@command("ui.themepair")
def theme_pair(args, context, body):
    themes = registry.themes()["themes"]
    current = context.get("theme") or ("ink" if context.get("prefersDark") else "paper")
    pair = themes.get(current, {}).get("pair") or ("paper" if themes.get(current, {}).get("dark") else "ink")
    return theme_set([pair], context, body)


@command("pref.set")
def pref_set(args, context, body):
    text = " ".join(args).strip()
    if "=" not in text:
        raise CommandError("write token=value, e.g. :set main=#e2b714")
    name, value = (part.strip() for part in text.split("=", 1))
    value, error = lib.validate_token(registry.themes()["schema"], name, value.strip("'\""))
    if error:
        raise CommandError(error)
    prefs = Preferences.current()
    undo = (
        {"command": "pref.set", "args": [f"{name}={prefs.tokens[name]}"]}
        if name in prefs.tokens
        else {"command": "pref.reset", "args": [name]}
    )
    prefs.tokens = prefs.tokens | {name: value}
    prefs.save(update_fields=["tokens", "updated_at"])
    return {
        "message": f"{name} = {value}",
        "effects": _theme_effects(prefs),
        "undo": undo,
        "redo": {"command": "pref.set", "args": [f"{name}={value}"]},
    }


@command("pref.reset")
def pref_reset(args, context, body):
    prefs = Preferences.current()
    names = args or list(prefs.tokens)
    unknown = [n for n in names if n not in prefs.tokens]
    if unknown:
        raise CommandError(f"not set: {', '.join(unknown)}")
    removed = {k: prefs.tokens[k] for k in names}
    prefs.tokens = {k: v for k, v in prefs.tokens.items() if k not in names}
    prefs.save(update_fields=["tokens", "updated_at"])
    result = {"message": f"Reset {', '.join(names) or 'nothing'}", "effects": _theme_effects(prefs)}
    if len(removed) == 1:
        (name, value), = removed.items()
        result["undo"] = {"command": "pref.set", "args": [f"{name}={value}"]}
        result["redo"] = {"command": "pref.reset", "args": [name]}
    return result


@command("layout.save")
def layout_save(args, context, body):
    name = " ".join(args).strip()
    if not name:
        raise CommandError("name the layout: :layout-save <name>")
    layout = body.get("layout")
    if not isinstance(layout, dict):
        raise CommandError("no layout to save")
    NamedLayout.objects.update_or_create(
        user=LOCAL_USER, name=name, defaults={"mode": context.get("mode", ""), "layout": layout}
    )
    return {"message": f"Saved layout '{name}'"}


@command("app.quit")
def app_quit(args, context, body):
    if not settings.SPOS_LAUNCHED:
        raise CommandError("only when started with spos")
    from spaced_positions.launcher import quit_soon

    quit_soon()
    return {"message": "Stopping Spaced Positions …", "effects": {"quit": True}}
