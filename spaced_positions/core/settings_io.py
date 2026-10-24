"""Settings as one TOML file (spec 07 §5): the theme, the token overrides, the settings, the key bindings, the named
layouts and the user's themes, so a setup moves to another machine with copy and paste. Importing checks every
value like `:set` and `:map` do; what can't be used is listed, the rest is applied. A pasted theme (`name`,
`extends`, `[color]` …) is imported as a theme of its own."""

from __future__ import annotations

import json
import tomllib

from spaced_positions.design import lib

from . import keymap, registry, settings, themes, user_pieces
from .models import LOCAL_USER, KeymapOverride, NamedLayout, Preferences, UserTheme
from .themes import toml_value

BOARD_PREFIXES = ("sq-", "arrow-", "board-", "piece-")


def _key(k: str) -> str:
    return k if k.replace("-", "").replace("_", "").isalnum() else json.dumps(k)


def export_toml() -> str:
    prefs = Preferences.current()
    schema = registry.themes()["schema"]
    lines = ["# Spaced Positions settings · :settings-import or Settings → Data to use them", f'theme = "{prefs.theme or "auto"}"', ""]
    colors = {k: v for k, v in prefs.tokens.items() if schema.get(k, {}).get("type") == "color" and not k.startswith(BOARD_PREFIXES)}
    board = {k: v for k, v in prefs.tokens.items() if k.startswith(BOARD_PREFIXES)}
    rest = {k: v for k, v in prefs.tokens.items() if k not in colors and k not in board}
    for table, items in (("color", colors), ("board", board), ("tokens", rest),
                         ("settings", {k: v for k, v in prefs.settings.items() if k != "engine.path"})):  # the path is this machine's
        if items:
            lines.append(f"[{table}]")
            lines += [f"{_key(k)} = {toml_value(v)}" for k, v in sorted(items.items())]
            lines.append("")
    overrides = list(KeymapOverride.objects.filter(user=LOCAL_USER))
    bound = [o for o in overrides if o.command and o.context == "global"]
    if bound:
        lines.append("[keys]")
        lines += [f'{json.dumps(o.keys)} = {json.dumps(" ".join([o.command, *o.args]))}' for o in bound]
        lines.append("")
    unmapped = [o for o in overrides if not o.command and o.context == "global"]
    if unmapped:
        lines.append("[keys.unmap]")
        lines += [f"{json.dumps(o.keys)} = true" for o in unmapped]
        lines.append("")
    for context in sorted({o.context for o in overrides if o.context != "global"}):
        lines.append(f'[keys.contexts.{json.dumps(context)}]')
        lines += [f'{json.dumps(o.keys)} = {json.dumps(" ".join([o.command, *o.args]))}' for o in overrides if o.context == context]
        lines.append("")
    for t in UserTheme.objects.filter(user=LOCAL_USER):
        lines.append(f"[themes.{_key(t.name)}]")
        lines += [f"label = {toml_value(t.label)}", f"extends = {toml_value(t.extends)}"]
        lines.append(f"values = {{ {', '.join(f'{_key(k)} = {toml_value(v)}' for k, v in sorted(t.values.items()))} }}")
        lines.append("")
    for layout in NamedLayout.objects.filter(user=LOCAL_USER):
        lines += ["[[layouts]]", f"name = {toml_value(layout.name)}", f"mode = {toml_value(layout.mode)}",
                  f"layout = {toml_value(json.dumps(layout.layout))}", ""]
    return "\n".join(lines).rstrip() + "\n"


def import_toml(text: str) -> dict:
    """Apply a settings (or theme) TOML; returns {ok, message, problems, effects}."""
    from .server_commands import _keymap_effects, _theme_effects

    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        return {"ok": False, "message": f"not TOML: {e}", "problems": []}
    if "extends" in data and ("color" in data or "board" in data) and "theme" not in data:
        return _import_theme(data)
    prefs = Preferences.current()
    schema = registry.themes()["schema"]
    problems, applied = [], 0
    for table in ("themes",):
        for name, t in (data.get(table) or {}).items():
            result = _import_theme({"name": name, "label": t.get("label", name), "extends": t.get("extends", "paper"), "tokens": t.get("values", {})})
            if not result["ok"]:
                problems.append(result["message"])
    tokens = {}
    for table in ("color", "board", "tokens"):
        for name, value in (data.get(table) or {}).items():
            checked, error = user_pieces.validate_token(schema, name, value)
            if error:
                problems.append(error)
            else:
                tokens[name] = checked
    stored = dict(prefs.settings)
    for name, value in (data.get("settings") or {}).items():
        if name == "engine.path":  # which program runs is set by hand, never by a pasted file
            problems.append("engine.path is set by hand in Settings → Engine, not imported")
            continue
        raw = {True: "on", False: "off"}.get(value, value) if isinstance(value, bool) else str(value)
        checked, error = settings.parse(name, raw)
        if error:
            problems.append(error)
        else:
            stored[name] = checked
    theme = data.get("theme")
    if theme is not None:
        if theme in ("auto", "") or theme in themes.all_themes():
            prefs.theme = "" if theme == "auto" else theme
        else:
            problems.append(f"no theme '{theme}'")
    prefs.tokens = tokens
    prefs.settings = stored
    prefs.save()
    applied += len(tokens) + len(data.get("settings") or {})
    keys = data.get("keys") or {}
    bindings = [("global", k, v) for k, v in keys.items() if isinstance(v, str)]
    bindings += [(ctx, k, v) for ctx, table in (keys.get("contexts") or {}).items() for k, v in table.items()]
    unmaps = [k for k, v in (keys.get("unmap") or {}).items() if v]
    commands = registry.commands()["commands"]
    for context, seq, value in bindings:
        cid, *args = str(value).split()
        try:
            seq = keymap.normalise(seq)
        except ValueError as e:
            problems.append(str(e))
            continue
        if cid not in commands:
            problems.append(f"{seq}: no command '{cid}'")
            continue
        errors = keymap.problems_with(context, seq, cid, args)
        if errors:
            problems.append(errors[0])
            continue
        KeymapOverride.objects.update_or_create(user=LOCAL_USER, context=context, keys=seq, defaults={"command": cid, "args": args})
        applied += 1
    for seq in unmaps:
        try:
            seq = keymap.normalise(seq)
        except ValueError as e:
            problems.append(str(e))
            continue
        KeymapOverride.objects.update_or_create(user=LOCAL_USER, context="global", keys=seq, defaults={"command": "", "args": []})
        applied += 1
    for layout in data.get("layouts") or []:
        try:
            tree = json.loads(layout["layout"])
        except (KeyError, ValueError, TypeError):
            problems.append(f"layout {layout.get('name', '?')}: unreadable")
            continue
        NamedLayout.objects.update_or_create(user=LOCAL_USER, name=str(layout["name"])[:60], defaults={"mode": layout.get("mode", ""), "layout": tree})
        applied += 1
    message = f"Imported {applied} setting{'s' if applied != 1 else ''}" + (f" · {len(problems)} skipped: {problems[0]}" if problems else "")
    return {"ok": True, "message": message, "problems": problems,
            "effects": _theme_effects(prefs) | {"settings": settings.values(prefs.settings), "themes": themes.all_themes()} | _keymap_effects()}


def _import_theme(data: dict) -> dict:
    from django.utils.text import slugify

    from .server_commands import _theme_effects

    builtin = registry.themes()["themes"]
    extends = data.get("extends", "paper")
    if extends not in builtin:
        return {"ok": False, "message": f"a theme extends a built-in theme ({', '.join(builtin)}), not '{extends}'", "problems": []}
    schema = registry.themes()["schema"]
    values, problems = {}, []
    for table in ("color", "board", "tokens"):
        for name, value in (data.get(table) or {}).items():
            checked, error = user_pieces.validate_token(schema, name, value)
            if error:
                problems.append(error)
            else:
                values[name] = checked
    name = slugify(str(data.get("name", "")))[:60] or "imported"
    if name in builtin:
        name = f"{name}-mine"
    label = str(data.get("label") or name)[:80]
    UserTheme.objects.update_or_create(user=LOCAL_USER, name=name, defaults={"label": label, "extends": extends, "values": values})
    warnings = themes.contrast_problems(builtin[extends]["values"] | values)
    message = f"Theme {label} imported (:theme {name})" + (f" · check contrast: {warnings[0]}" if warnings else "")
    return {"ok": True, "message": message, "problems": problems,
            "effects": _theme_effects(Preferences.current()) | {"themes": themes.all_themes()}}
