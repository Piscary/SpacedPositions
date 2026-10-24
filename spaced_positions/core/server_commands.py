"""Server handlers of commands (spec 09 §4). `POST /cmd/<id>/` with JSON `{"args": [...], "context": {...}}`.

A handler returns a dict: `message` for the status line, `effects` for the client (e.g. new theme CSS), and
optionally `oob` HTML fragments for htmx to swap in.
"""

from django.conf import settings

from spaced_positions.design import lib

from . import registry, themes
from . import settings as user_settings
from .models import LOCAL_USER, NamedLayout, Preferences

HANDLERS = {}
MODULES = ("spaced_positions.library.commands", "spaced_positions.library.edit")  # other apps' server commands


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
            "css": themes.theme_css(prefs.theme, prefs.tokens),
            "tokens": prefs.tokens,
            "boardHash": colors_hash(),
        }
    }


@command("theme.set")
def theme_set(args, context, body):
    if not args:
        raise CommandError("which theme? e.g. :theme ink")
    name = args[0]
    known = themes.all_themes()
    if name not in known and name not in ("", "auto"):
        raise CommandError(f"no theme '{name}'")
    prefs = Preferences.current()
    previous = prefs.theme or "auto"
    prefs.theme = "" if name == "auto" else name
    prefs.save(update_fields=["theme", "updated_at"])
    label = known.get(prefs.theme, {}).get("label", "follow the system")
    return {
        "message": f"Theme: {label}",
        "effects": _theme_effects(prefs),
        "undo": {"command": "theme.set", "args": [previous]},
        "redo": {"command": "theme.set", "args": [name]},
    }


@command("ui.themepair")
def theme_pair(args, context, body):
    known = themes.all_themes()
    current = context.get("theme") or ("ink" if context.get("prefersDark") else "paper")
    pair = known.get(current, {}).get("pair") or ("paper" if known.get(current, {}).get("dark") else "ink")
    return theme_set([pair], context, body)


@command("pref.set")
def pref_set(args, context, body):
    text = " ".join(args).strip()
    if "=" not in text:
        raise CommandError("write token=value, e.g. :set main=#e2b714")
    name, value = (part.strip() for part in text.split("=", 1))
    if name in user_settings.BY_NAME:
        return _setting_set(name, value)
    from .user_pieces import validate_token

    value, error = validate_token(registry.themes()["schema"], name, value.strip("'\""))
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


def _setting_set(name: str, raw: str) -> dict:
    value, error = user_settings.parse(name, raw)
    if error:
        raise CommandError(error)
    prefs = Preferences.current()
    before = user_settings.values(prefs.settings)[name]
    prefs.settings = prefs.settings | {name: value}
    prefs.save(update_fields=["settings", "updated_at"])
    shown = {True: "on", False: "off"}.get(value, value) if isinstance(value, bool) else value
    old = {True: "on", False: "off"}.get(before, before) if isinstance(before, bool) else before
    return {
        "message": f"{name} = {shown}",
        "effects": {"settings": user_settings.values(prefs.settings)},
        "undo": {"command": "pref.set", "args": [f"{name}={old}"]},
        "redo": {"command": "pref.set", "args": [f"{name}={shown}"]},
    }


@command("pref.reset")
def pref_reset(args, context, body):
    prefs = Preferences.current()
    if args and all(a in user_settings.BY_NAME for a in args):
        before = user_settings.values(prefs.settings)
        prefs.settings = {k: v for k, v in prefs.settings.items() if k not in args}
        prefs.save(update_fields=["settings", "updated_at"])
        result = {"message": f"Reset {', '.join(args)}", "effects": {"settings": user_settings.values(prefs.settings)}}
        if len(args) == 1:
            old = before[args[0]]
            old = {True: "on", False: "off"}.get(old, old) if isinstance(old, bool) else old
            result["undo"] = {"command": "pref.set", "args": [f"{args[0]}={old}"]}
            result["redo"] = {"command": "pref.reset", "args": args}
        return result
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


# ── User themes (spec 07 §4) ──────────────────────────────────────────────────────────────────────────────────


@command("theme.save")
def theme_save(args, context, body):
    """`:theme-save <name>`: the current theme with the colour overrides becomes a theme of its own."""
    from django.utils.text import slugify

    from .models import UserTheme

    label = " ".join(args).strip()
    if not label:
        raise CommandError("a name, e.g. :theme-save my nord")
    prefs = Preferences.current()
    known = themes.all_themes()
    base_name = prefs.theme if prefs.theme in known else ("ink" if context.get("prefersDark") else "paper")
    base = known[base_name]
    extends = base.get("extends", base_name) if base.get("user") else base_name
    values = {k: v for k, v in (base["values"] | prefs.tokens).items() if registry.themes()["themes"][extends]["values"].get(k) != v}
    name = slugify(label)[:60] or "theme"
    if name in registry.themes()["themes"]:
        raise CommandError(f"'{name}' is a built-in theme: choose another name")
    UserTheme.objects.update_or_create(user=LOCAL_USER, name=name, defaults={"label": label, "extends": extends, "values": values})
    prefs.theme, prefs.tokens = name, {k: v for k, v in prefs.tokens.items() if k not in values}
    prefs.save(update_fields=["theme", "tokens", "updated_at"])
    warnings = themes.contrast_problems(themes.all_themes()[name]["values"])
    message = f"Theme {label} saved and chosen" + (f" · check contrast: {'; '.join(warnings[:2])}" if warnings else "")
    return {"message": message, "effects": _theme_effects(prefs) | {"themes": themes.all_themes()}}


@command("theme.delete")
def theme_delete(args, context, body):
    from .models import UserTheme

    name = " ".join(args).strip()
    found = UserTheme.objects.filter(user=LOCAL_USER, name=name).first()
    if found is None:
        raise CommandError(f"no theme of yours called '{name}' (built-in themes stay)")
    found.delete()
    prefs = Preferences.current()
    if prefs.theme == name:
        prefs.theme = found.extends
        prefs.save(update_fields=["theme", "updated_at"])
    return {"message": f"Theme {found.label} deleted", "effects": _theme_effects(prefs) | {"themes": themes.all_themes()}}


@command("theme.export")
def theme_export(args, context, body):
    """`:theme-export`: the current theme with your overrides as TOML (the client copies it)."""
    prefs = Preferences.current()
    known = themes.all_themes()
    name = prefs.theme if prefs.theme in known else ("ink" if context.get("prefersDark") else "paper")
    t = known[name]
    extends = t.get("extends", name)
    base = registry.themes()["themes"][extends]["values"]
    values = {k: v for k, v in (t["values"] | prefs.tokens).items() if base.get(k) != v}
    text = themes.to_toml(f"{name}-mine" if not t.get("user") else name, f"{t['label']} (mine)" if not t.get("user") else t["label"], extends, values)
    return {"message": "Theme copied as TOML: paste it into Settings → Data to import it elsewhere", "effects": {"copy": text}}


# ── Keymap overrides (spec 07 §5, 08) ─────────────────────────────────────────────────────────────────────────


def _keymap_effects() -> dict:
    from . import keymap

    return {"registry": keymap.effective()}


@command("key.map")
def key_map(args, context, body):
    """`:map <keys> <command> [args]`: keys may be several tokens (`space o`); the first known command id ends them."""
    args = " ".join(args).split()  # the command line sends the binding as one text
    where, args = (args[0][1:], args[1:]) if args and args[0].startswith("@") else ("global", args)  # @view.library: another context
    from . import keymap
    from .models import KeymapOverride

    commands = registry.commands()["commands"]
    split = next((i for i, a in enumerate(args) if a in commands), None)
    if not split:
        raise CommandError("write the keys, then the command: :map space o train.storm 5")
    try:
        keys = keymap.normalise(" ".join(args[:split]))
    except ValueError as e:
        raise CommandError(str(e)) from None
    cid, cargs = args[split], args[split + 1:]
    problems = keymap.problems_with(where, keys, cid, cargs)
    if problems:
        raise CommandError(problems[0])
    old = KeymapOverride.objects.filter(user=LOCAL_USER, context=where, keys=keys).first()
    KeymapOverride.objects.update_or_create(user=LOCAL_USER, context=where, keys=keys, defaults={"command": cid, "args": cargs})
    result = {"message": f"{keys} → {commands[cid]['title']}", "effects": _keymap_effects(),
              "redo": {"command": "key.map", "args": [*([f"@{where}"] if where != "global" else []), *keys.split(), cid, *cargs]}}
    result["undo"] = ({"command": "key.map", "args": [*([f"@{where}"] if where != "global" else []), *keys.split(), old.command, *old.args]} if old and old.command
                      else {"command": "key.reset", "args": [*([f"@{where}"] if where != "global" else []), *keys.split()]})
    return result


@command("key.unmap")
def key_unmap(args, context, body):
    args = " ".join(args).split()  # the command line sends the binding as one text
    where, args = (args[0][1:], args[1:]) if args and args[0].startswith("@") else ("global", args)  # @view.library: another context
    from . import keymap
    from .models import KeymapOverride

    try:
        keys = keymap.normalise(" ".join(args))
    except ValueError as e:
        raise CommandError(str(e)) from None
    bound = keymap.effective()["keymap"].get(where, {}).get(keys)
    if bound is None:
        raise CommandError(f"'{keys}' isn't bound in {where}")
    KeymapOverride.objects.update_or_create(user=LOCAL_USER, context=where, keys=keys, defaults={"command": "", "args": []})
    return {"message": f"{keys} unmapped (was {registry.commands()['commands'][bound['command']]['title']})", "effects": _keymap_effects(),
            "undo": {"command": "key.reset", "args": [*([f"@{where}"] if where != "global" else []), *keys.split()]}, "redo": {"command": "key.unmap", "args": [*([f"@{where}"] if where != "global" else []), *keys.split()]}}


@command("key.reset")
def key_reset(args, context, body):
    """`:map-reset [keys]`: back to the default binding (all overrides without keys)."""
    args = " ".join(args).split()  # the command line sends the binding as one text
    where, args = (args[0][1:], args[1:]) if args and args[0].startswith("@") else ("global", args)  # @view.library: another context
    from . import keymap
    from .models import KeymapOverride

    rows = KeymapOverride.objects.filter(user=LOCAL_USER)
    if args:
        rows = rows.filter(keys=keymap.normalise(" ".join(args)), context=where)
    n = rows.count()
    rows.delete()
    return {"message": f"Reset {n} key binding{'s' if n != 1 else ''} to the defaults", "effects": _keymap_effects()}
