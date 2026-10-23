"""The design pipeline (spec 07 §8): read the sources in `design/`, write the generated files, and lint them.

Sources                         Generated
design/tokens.toml       ─┐     static/design/tokens.css     tier 1 defaults + tier 2 (derived.css)
design/derived.css       ─┤     static/design/themes.json    every theme resolved to CSS values + the token schema
design/themes/*.toml     ─┤     static/design/commands.json  commands + keymap + prefixes, read by the client and server
design/commands/*.toml   ─┤     docs/keymap.md               the keymap reference
design/keymap/default.toml┘
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# ── Sources ───────────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass
class Sources:
    schema: dict
    version: int
    derived_css: str
    themes: dict[str, dict]
    commands: dict[str, dict]
    keymap: dict[str, dict[str, str]]
    prefixes: dict[str, str]
    licences: dict = field(default_factory=dict)
    layout_accept: set = field(default_factory=set)


def load(design_dir: Path) -> Sources:
    tokens = tomllib.loads((design_dir / "tokens.toml").read_text())
    themes = {}
    for path in sorted((design_dir / "themes").glob("*.toml")):
        theme = tomllib.loads(path.read_text())
        theme.setdefault("name", path.stem)
        themes[theme["name"]] = theme
    commands = {}
    for path in sorted((design_dir / "commands").glob("*.toml")):
        for cid, spec in tomllib.loads(path.read_text()).items():
            if cid in commands:
                raise ValueError(f"command {cid} is defined twice ({path.name})")
            commands[cid] = spec | {"file": path.name}
    keymap = tomllib.loads((design_dir / "keymap" / "default.toml").read_text())
    licences_path = design_dir / "licences.toml"
    return Sources(
        schema=tokens["tokens"],
        version=tokens.get("version", 1),
        derived_css=(design_dir / "derived.css").read_text(),
        themes=themes,
        commands=commands,
        keymap=keymap.get("context", {}),
        prefixes=keymap.get("prefixes", {}),
        licences=tomllib.loads(licences_path.read_text()) if licences_path.exists() else {},
        layout_accept=set(keymap.get("layout", {}).get("accept", [])),
    )


# ── Tokens and themes ─────────────────────────────────────────────────────────────────────────────────────────────

HEX = re.compile(r"^#(?:[0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$")


def normalise_hex(value: str) -> str | None:
    """`1f3a5f`, `#1F3A5F`, `#abc` → `#1f3a5f` (spec 05 · ColorField). None if it isn't a hex colour."""
    v = value.strip().lower()
    if not v.startswith("#"):
        v = "#" + v
    if not HEX.match(v):
        return None
    if len(v) == 4:
        v = "#" + "".join(c * 2 for c in v[1:])
    return v


def validate_token(schema: dict, name: str, value) -> tuple[object, str | None]:
    """Check and normalise one token value. Returns (value, error)."""
    spec = schema.get(name)
    if spec is None:
        return value, f"unknown token '{name}'"
    kind = spec["type"]
    if kind == "color":
        hexed = normalise_hex(str(value))
        return (hexed, None) if hexed else (value, f"{name}: '{value}' is not a hex colour")
    if kind in ("px", "number", "ms"):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return value, f"{name}: '{value}' is not a number"
        lo, hi = spec.get("min"), spec.get("max")
        if (lo is not None and number < lo) or (hi is not None and number > hi):
            return value, f"{name}: {value} is outside {lo}–{hi}"
        return (int(number) if number.is_integer() else number), None
    if kind == "enum":
        return (value, None) if value in spec["values"] else (value, f"{name}: choose one of {', '.join(spec['values'])}")
    if kind == "bool":
        if isinstance(value, bool):
            return value, None
        if str(value).lower() in ("true", "on", "yes", "1"):
            return True, None
        if str(value).lower() in ("false", "off", "no", "0"):
            return False, None
        return value, f"{name}: use true or false"
    if kind == "font":
        text = str(value).strip()
        if not text or any(c in text for c in ";{}<>"):
            return value, f"{name}: not a valid font list"
        return text, None
    return value, f"{name}: unknown type {kind}"


def resolve_theme(sources: Sources, name: str, _seen=()) -> dict:
    """All base-token values of a theme: schema defaults ← extended theme ← this theme."""
    theme = sources.themes[name]
    if name in _seen:
        raise ValueError(f"theme {name}: circular extends")
    values = {k: v["default"] for k, v in sources.schema.items() if "default" in v}
    if theme.get("extends"):
        values |= resolve_theme(sources, theme["extends"], _seen + (name,))
    for table in ("color", "board", "type", "shape", "tokens"):
        values |= theme.get(table, {})
    return values


def css_value(spec: dict, value) -> str:
    kind = spec["type"]
    if kind == "px":
        return f"{value}px"
    if kind == "ms":
        return f"{value}ms"
    if kind == "enum" and "css-values" in spec:
        return spec["css-values"][value]
    return str(value)


def css_vars(sources: Sources, values: dict) -> dict[str, str]:
    """Custom properties for a set of token values (only tokens with css != false)."""
    out = {}
    for name, value in values.items():
        spec = sources.schema.get(name)
        if not spec or spec.get("css") is False:
            continue
        out["--" + spec.get("var", name)] = css_value(spec, value)
    return out


def block(selector: str, props: dict[str, str]) -> str:
    return selector + " {\n" + "".join(f"  {k}: {v};\n" for k, v in props.items()) + "}\n"


# ── Keys ──────────────────────────────────────────────────────────────────────────────────────────────────────────

NAMED_KEYS = {
    "space", "enter", "esc", "tab", "backspace", "delete", "up", "down", "left", "right",
    "home", "end", "pageup", "pagedown", *(f"f{i}" for i in range(1, 13)),
}
MODIFIERS = ("mod", "ctrl", "alt", "shift")
BROWSER_RESERVED = {
    "mod+w", "mod+t", "mod+n", "mod+q", "mod+l", "mod+r", "mod+tab", "mod+h", "mod+j",
    *(f"mod+{i}" for i in range(1, 10)),
    "f5", "f11", "f12", "ctrl+tab", "alt+left", "alt+right",
}
ALTGR_CHARS = set("[]{}\\|@~")
DISPLAY = {
    "space": "␣", "enter": "↵", "esc": "Esc", "tab": "⇥", "backspace": "⌫", "delete": "⌦",
    "up": "↑", "down": "↓", "left": "←", "right": "→", "home": "Home", "end": "End",
    "pageup": "PgUp", "pagedown": "PgDn", "shift": "⇧", "alt": "⌥", "ctrl": "Ctrl",
}


def split_key(token: str) -> tuple[list[str], str]:
    """`mod+shift+z` → (['mod', 'shift'], 'z'). `+` and `mod++` have '+' as their key."""
    if token == "+":
        return [], "+"
    if token.endswith("++"):
        return token[:-2].split("+"), "+"
    *mods, key = token.split("+")
    return mods, key


def parse_key(token: str) -> str:
    """Validate and normalise one key of a sequence (`mod+shift+z`, `G`, `space`). Raises ValueError."""
    mods, key = split_key(token)
    for m in mods:
        if m not in MODIFIERS:
            raise ValueError(f"unknown modifier '{m}' in '{token}'")
    if len(key) == 1:
        if mods == ["shift"]:
            raise ValueError(f"'{token}': write the character itself (e.g. 'U' or '?'), not shift+")
        if mods and key.isalpha():
            key = key.lower()  # with a modifier, letters match by key; shift is written out
    elif key not in NAMED_KEYS:
        raise ValueError(f"unknown key '{key}' in '{token}'")
    return "+".join([*(m for m in MODIFIERS if m in mods), key])


def parse_seq(seq: str) -> list[str]:
    return [parse_key(t) for t in seq.split(" ") if t]


def display_key(token: str, mac: bool = True) -> str:
    mods, key = split_key(token)
    shown = [("⌘" if mac else "Ctrl") if m == "mod" else DISPLAY.get(m, m) for m in mods]
    shown.append(DISPLAY.get(key, key.upper() if mods and key.isalpha() else key))
    return ("" if mac else "+").join(shown)


def parse_binding(value: str) -> tuple[str, list[str]]:
    cid, *args = value.split(" ")
    return cid, args


# ── `when` expressions (the same grammar as static/js/core/when.js) ──────────────────────────────────────────────

WHEN_TOKEN = re.compile(r"\s*(?:(&&|\|\||==|!=|>=|<=|[!<>()])|('[^']*')|(\d+(?:\.\d+)?)|([A-Za-z_][\w.]*))")


def check_when(expr: str) -> str | None:
    """Return an error message if `expr` doesn't parse, else None."""
    tokens, pos = [], 0
    expr = expr.strip()
    while pos < len(expr):
        m = WHEN_TOKEN.match(expr, pos)
        if not m or m.end() == pos:
            return f"can't read '{expr[pos:]}'"
        tokens.append(next(g for g in m.groups() if g is not None))
        pos = m.end()
    i = 0

    def peek():
        return tokens[i] if i < len(tokens) else None

    def take():
        nonlocal i
        i += 1
        return tokens[i - 1]

    def primary():
        t = take() if peek() else None
        if t is None:
            raise ValueError("unexpected end")
        if t == "!":
            return primary()
        if t == "(":
            orexpr()
            if take() != ")":
                raise ValueError("missing )")
            return
        if t in ("&&", "||", "==", "!=", ">", "<", ">=", "<=", ")"):
            raise ValueError(f"unexpected '{t}'")

    def comparison():
        primary()
        if peek() in ("==", "!=", ">", "<", ">=", "<="):
            take()
            primary()

    def andexpr():
        comparison()
        while peek() == "&&":
            take()
            comparison()

    def orexpr():
        andexpr()
        while peek() == "||":
            take()
            andexpr()

    try:
        orexpr()
        if i != len(tokens):
            return f"unexpected '{tokens[i]}'"
    except (ValueError, IndexError) as e:
        return str(e)
    return None


# ── Build ─────────────────────────────────────────────────────────────────────────────────────────────────────────

COMMAND_FIELDS = {
    "title", "group", "aliases", "args", "when", "reason", "handler", "undoable", "repeatable",
    "sticky", "danger", "hidden", "phase", "file",
}
ARG_TYPES = {"int", "enum", "text", "view", "buffer", "theme", "token", "tokenname", "layout", "pieceset", "position"}


def keymap_json(sources: Sources) -> dict:
    out = {}
    for context, bindings in sources.keymap.items():
        out[context] = {}
        for seq, value in bindings.items():
            cid, args = parse_binding(value)
            out[context][" ".join(parse_seq(seq))] = {"command": cid, "args": args}
    return out


def commands_json(sources: Sources) -> dict:
    commands = {}
    for cid, spec in sources.commands.items():
        commands[cid] = {k: v for k, v in spec.items() if k != "file"}
        commands[cid].setdefault("handler", "client")
    return {
        "version": sources.version,
        "commands": commands,
        "keymap": keymap_json(sources),
        "prefixes": {" ".join(parse_seq(k)): v for k, v in sources.prefixes.items()},
        "order": ["overlay", "layer", "view", "pane", "mode", "global"],
    }


def themes_json(sources: Sources) -> dict:
    themes = {}
    for name, theme in sources.themes.items():
        values = resolve_theme(sources, name)
        themes[name] = {
            "label": theme.get("label", name.title()),
            "dark": bool(theme.get("dark")),
            "pair": theme.get("pair"),
            "values": values,
            "css": css_vars(sources, values),
        }
    schema = {
        name: {k: v for k, v in spec.items() if k in ("type", "description", "values", "min", "max", "css", "var", "css-values")}
        for name, spec in sources.schema.items()
    }
    return {"version": sources.version, "themes": themes, "schema": schema}


def tokens_css(sources: Sources) -> str:
    """Tier 1 defaults of the non-colour tokens + tier 2. Colours come from the theme block in the page."""
    defaults = {k: v["default"] for k, v in sources.schema.items() if "default" in v and v["type"] != "color"}
    return (
        "/* Generated by `manage.py design build` from design/tokens.toml and design/derived.css. Do not edit. */\n"
        "@layer tokens {\n"
        + _indent(block(":root", css_vars(sources, defaults)))
        + _indent(sources.derived_css.split("*/", 1)[1].strip() + "\n")
        + "}\n"
    )


def keymap_md(sources: Sources) -> str:
    commands = sources.commands
    lines = [
        "# Keymap (generated)",
        "",
        "Generated by `manage.py design build` from `design/keymap/default.toml`. Do not edit; the spec's",
        "reference is `spec/08-keymap.md`.",
        "",
    ]
    for context, bindings in sources.keymap.items():
        lines += [f"## {context}", "", "| Keys | Command | Id |", "|---|---|---|"]
        for seq, value in bindings.items():
            cid, args = parse_binding(value)
            keys = " ".join(f"`{display_key(t)}`" for t in parse_seq(seq))
            title = commands.get(cid, {}).get("title", "?")
            lines.append(f"| {keys} | {title}{' ' + ' '.join(args) if args else ''} | `{cid}` |")
        lines.append("")
    return "\n".join(lines)


def _indent(text: str) -> str:
    return "".join(("  " + line if line.strip() else line) for line in text.splitlines(True))


PIECE_CODES = [c + r for c in "wb" for r in "KQRBNP"]
ROLES = {"K": "king", "Q": "queen", "R": "rook", "B": "bishop", "N": "knight", "P": "pawn"}


def piece_sets(sources: Sources) -> list[str]:
    return list(sources.schema["piece-set"]["values"])


def pieces_css(sources: Sources) -> str:
    """Piece images for chessground, switched by <html data-pieces="…"> (spec 07 §6). The default set needs no
    attribute; the others win by specificity."""
    default = sources.schema["piece-set"]["default"]
    lines = ["/* Generated by `manage.py design build` from the piece-set token. Do not edit. */", "@layer base {"]
    for name in piece_sets(sources):
        prefix = "" if name == default else f':root[data-pieces="{name}"] '
        for code in PIECE_CODES:
            color = "white" if code[0] == "w" else "black"
            lines.append(f'  {prefix}.cg-wrap piece.{ROLES[code[1]]}.{color} {{ background-image: url("../pieces/{name}/{code}.svg"); }}')
    lines.append("}")
    return "\n".join(lines) + "\n"


def generated(sources: Sources, out_dir: Path, docs_dir: Path) -> dict[Path, str]:
    themes = themes_json(sources)
    themes["pieces"] = {
        name: {k: v for k, v in sources.licences.get("pieces", {}).get(name, {}).items() if k in ("label", "author", "licence")}
        for name in piece_sets(sources)
    }
    return {
        out_dir / "tokens.css": tokens_css(sources),
        out_dir / "pieces.css": pieces_css(sources),
        out_dir / "themes.json": json.dumps(themes, indent=1, ensure_ascii=False) + "\n",
        out_dir / "commands.json": json.dumps(commands_json(sources), indent=1, ensure_ascii=False) + "\n",
        docs_dir / "keymap.md": keymap_md(sources),
    }


def build(design_dir: Path, out_dir: Path, docs_dir: Path) -> list[Path]:
    files = generated(load(design_dir), out_dir, docs_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    for path, text in files.items():
        path.write_text(text)
    return list(files)


def generated_is_current(design_dir: Path, out_dir: Path, docs_dir: Path) -> list[str]:
    """Names of generated files that differ from what a build would write."""
    files = generated(load(design_dir), out_dir, docs_dir)
    return [p.name for p, text in files.items() if not p.exists() or p.read_text() != text]
