"""The generated design registry (commands, keymap, themes) as the server sees it. Source of truth: `design/`,
built into static/design/*.json by `manage.py design build`."""

import json
from functools import lru_cache

from django.conf import settings

from spaced_positions.design import lib


def _load(name: str) -> dict:
    path = settings.DESIGN_OUT / name
    return _load_cached(str(path), path.stat().st_mtime_ns)


@lru_cache(maxsize=8)
def _load_cached(path: str, _mtime: int) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def commands() -> dict:
    return _load("commands.json")


def themes() -> dict:
    return _load("themes.json")


def command(cid: str) -> dict:
    try:
        return commands()["commands"][cid]
    except KeyError:
        raise KeyError(f"unknown command '{cid}' (see design/commands/)") from None


def primary_keys(cid: str, args: list[str] | None = None) -> list[str] | None:
    """The first binding of a command (as key tokens), in keymap order, matching `args` if given."""
    for bindings in commands()["keymap"].values():
        for seq, binding in bindings.items():
            if binding["command"] == cid and (args is None or binding["args"] == args):
                return seq.split(" ")
    return None


def theme_css(theme: str, overrides: dict) -> str:
    """The `<style id="theme">` block: the theme's base tokens + the user's overrides (spec 07 §4).
    An empty theme name follows the OS: paper, or ink in dark mode."""
    data = themes()
    schema = data["schema"]
    sources = lib.Sources(schema=schema, version=1, derived_css="", themes={}, commands={}, keymap={}, prefixes={})
    user = lib.css_vars(sources, overrides)
    if theme and theme in data["themes"]:
        return lib.block(":root", data["themes"][theme]["css"] | user)
    light, dark = data["themes"]["paper"]["css"], data["themes"]["ink"]["css"]
    return (
        lib.block(":root", light | user)
        + "@media (prefers-color-scheme: dark) {\n"
        + lib.block("  :root", dark | user)
        + "}\n"
    )
