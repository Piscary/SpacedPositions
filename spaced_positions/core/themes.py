"""Themes for the page: the built-in ones (design/themes, built into themes.json) and the user's (UserTheme), which
extend a built-in theme (spec 07 §4)."""

from __future__ import annotations

from spaced_positions.design import lib

from . import registry
from .models import LOCAL_USER, UserTheme


def _sources():
    schema = registry.themes()["schema"]
    return lib.Sources(schema=schema, version=1, derived_css="", themes={}, commands={}, keymap={}, prefixes={})


def all_themes() -> dict:
    """{name: {label, dark, pair, values, css, user}} for every theme."""
    data = registry.themes()["themes"]
    out = {name: t | {"user": False} for name, t in data.items()}
    sources = _sources()
    for t in UserTheme.objects.filter(user=LOCAL_USER):
        base = data.get(t.extends) or data["paper"]
        values = base["values"] | t.values
        out[t.name] = {"label": t.label, "dark": base["dark"], "pair": base.get("pair"), "values": values,
                       "css": lib.css_vars(sources, values), "user": True, "extends": t.extends}
    return out


def theme_css(theme: str, overrides: dict) -> str:
    """The `<style id="theme">` block: the theme's base tokens + the user's overrides. No theme: follow the OS."""
    themes = all_themes()
    user = lib.css_vars(_sources(), overrides)
    if theme and theme in themes:
        return lib.block(":root", themes[theme]["css"] | user)
    light, dark = themes["paper"]["css"], themes["ink"]["css"]
    return lib.block(":root", light | user) + "@media (prefers-color-scheme: dark) {\n" + lib.block("  :root", dark | user) + "}\n"


def contrast_problems(values: dict) -> list[str]:
    """The design lint's contrast rules for one theme's values (a user theme is saved anyway, with these warnings)."""
    from spaced_positions.design.check import CONTRAST_RULES, contrast

    out = []
    for fg, bgs, minimum, _high in CONTRAST_RULES:
        for bg in bgs:
            try:
                ratio = contrast(values[fg], values[bg])
            except (KeyError, ValueError):
                continue
            if ratio < minimum:
                out.append(f"{fg} on {bg} {ratio:.1f}:1 (needs {minimum}:1)")
    return out


def to_toml(name: str, label: str, extends: str, values: dict) -> str:
    """A theme as TOML (`:theme-export`), in the built-in themes' format."""
    schema = registry.themes()["schema"]
    colors = {k: v for k, v in values.items() if schema.get(k, {}).get("type") == "color" and not k.startswith(("sq-", "arrow-"))}
    board = {k: v for k, v in values.items() if k.startswith(("sq-", "arrow-", "board-", "piece-"))}
    rest = {k: v for k, v in values.items() if k not in colors and k not in board}
    lines = [f'name = "{name}"', f'label = "{label}"', f'extends = "{extends}"', ""]
    for table, items in (("color", colors), ("board", board), ("tokens", rest)):
        if items:
            lines.append(f"[{table}]")
            lines += [f'{k} = {toml_value(v)}' for k, v in items.items()]
            lines.append("")
    return "\n".join(lines)


def toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'
