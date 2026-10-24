"""The keymap with the user's overrides (spec 07 §5, 08): `:map <keys> <command> [args]`, `:unmap <keys>` and the
keymap editor. Overrides are checked with the same rules as the default keymap (design/check.py): a key can't be a
command and a prefix in one context, the browser's keys stay the browser's, global keys stay reserved."""

from __future__ import annotations

import copy

from spaced_positions.design import check, lib

from . import registry
from .models import LOCAL_USER, KeymapOverride


def effective() -> dict:
    """commands.json with the overrides applied to its keymap."""
    data = copy.deepcopy(registry.commands())
    for o in KeymapOverride.objects.filter(user=LOCAL_USER):
        bindings = data["keymap"].setdefault(o.context, {})
        if o.command:
            bindings[o.keys] = {"command": o.command, "args": list(o.args)}
        else:
            bindings.pop(o.keys, None)
    return data


def problems_with(context: str, keys: str, command: str | None, args: list[str]) -> list[str]:
    """What the keymap checks say about binding `keys` in `context` (only the problems this binding causes)."""
    data = effective()
    keymap = {c: {seq: f"{b['command']} {' '.join(b['args'])}".strip() for seq, b in bs.items()} for c, bs in data["keymap"].items()}
    before = {str(p) for p in _check(keymap, data)}
    if command:
        keymap.setdefault(context, {})[keys] = f"{command} {' '.join(args)}".strip()
    else:
        keymap.get(context, {}).pop(keys, None)
    return [p.message for p in _check(keymap, data) if str(p) not in before and p.level == "error"]


def _check(keymap: dict, data: dict):
    sources = lib.Sources(schema={}, version=1, derived_css="", themes={}, commands=data["commands"], keymap=keymap,
                          prefixes=data.get("prefixes", {}))
    return check.check_keymap(sources)


def normalise(keys: str) -> str:
    """'Space o' → 'space o' (the keymap's own spelling); raises ValueError for a key it doesn't know."""
    return " ".join(lib.parse_seq(keys))
