"""`manage.py design check`: the design lint (spec 07 §7–8, 09 §13).

Each check returns a list of Problems. Errors fail CI; warnings are printed.
"""

from __future__ import annotations

import importlib.metadata
import re
import tomllib
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from . import lib


@dataclass
class Problem:
    level: str  # "error" | "warning"
    check: str
    message: str

    def __str__(self):
        return f"{self.level.upper():7} [{self.check}] {self.message}"


def err(check, message):
    return Problem("error", check, message)


def warn(check, message):
    return Problem("warning", check, message)


# ── Colour maths ──────────────────────────────────────────────────────────────────────────────────────────────────


def _rgb(hex_: str) -> tuple[float, float, float]:
    h = lib.normalise_hex(hex_)
    return tuple(int(h[i : i + 2], 16) / 255 for i in (1, 3, 5))


def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_: str) -> float:
    r, g, b = (_linear(c) for c in _rgb(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _lab_from_linear(r, g, b):
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def lab(hex_: str):
    return _lab_from_linear(*(_linear(c) for c in _rgb(hex_)))


# Machado et al. 2009, deuteranopia at full severity, applied to linear RGB.
DEUTAN = ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881))


def lab_deutan(hex_: str):
    rgb = [_linear(c) for c in _rgb(hex_)]
    sim = [min(1.0, max(0.0, sum(m * c for m, c in zip(row, rgb)))) for row in DEUTAN]
    return _lab_from_linear(*sim)


def delta_e(l1, l2) -> float:
    return sum((a - b) ** 2 for a, b in zip(l1, l2)) ** 0.5


# ── Checks ────────────────────────────────────────────────────────────────────────────────────────────────────────

CONTRAST_RULES = [
    # (foreground, backgrounds, minimum, minimum for the high-contrast theme)
    ("text", ("bg", "bg-alt", "surface"), 4.5, 7.0),
    ("text-sub", ("bg", "bg-alt"), 3.0, 4.5),
    ("main-text", ("main",), 4.5, 7.0),
    ("good", ("bg",), 3.0, 4.5),
    ("bad", ("bg",), 3.0, 4.5),
    ("warn", ("bg",), 3.0, 4.5),
    ("main", ("bg",), 3.0, 4.5),
]


def check_themes(sources: lib.Sources) -> list[Problem]:
    problems = []
    required = [n for n, s in sources.schema.items() if s["type"] == "color" and "default" not in s]
    for name, theme in sources.themes.items():
        if theme.get("extends") and theme["extends"] not in sources.themes:
            problems.append(err("themes", f"{name}: extends unknown theme '{theme['extends']}'"))
            continue
        try:
            values = lib.resolve_theme(sources, name)
        except ValueError as e:
            problems.append(err("themes", str(e)))
            continue
        for token in required:
            if token not in values:
                problems.append(err("themes", f"{name}: missing required token '{token}'"))
        for token, value in values.items():
            _, error = lib.validate_token(sources.schema, token, value)
            if error:
                problems.append(err("themes", f"{name}: {error}"))
        if any(p.message.startswith(f"{name}:") for p in problems):
            continue
        high = name == "contrast"
        for fg, bgs, minimum, minimum_high in CONTRAST_RULES:
            need = minimum_high if high else minimum
            for bg in bgs:
                ratio = contrast(values[fg], values[bg])
                if ratio < need:
                    problems.append(err("contrast", f"{name}: {fg} on {bg} is {ratio:.2f}:1, needs {need}:1"))
        de = delta_e(lab_deutan(values["good"]), lab_deutan(values["bad"]))
        if de < 20:
            problems.append(err("contrast", f"{name}: good vs bad differ by ΔE {de:.0f} for deuteranopia, needs 20"))
        dl = abs(lab(values["sq-light"])[0] - lab(values["sq-dark"])[0])
        if dl < 15:
            problems.append(err("contrast", f"{name}: sq-light vs sq-dark differ by ΔL {dl:.0f}, needs 15"))
        pair = theme.get("pair")
        if pair and pair not in sources.themes:
            problems.append(err("themes", f"{name}: pair '{pair}' is not a theme"))
    for name, spec in sources.schema.items():
        if "default" in spec:
            _, error = lib.validate_token(sources.schema, name, spec["default"])
            if error and not str(spec["default"]).startswith("var("):
                problems.append(err("tokens", f"default of {error}"))
    return problems


def check_commands(sources: lib.Sources) -> list[Problem]:
    problems = []
    aliases: dict[str, str] = {}
    for cid, spec in sources.commands.items():
        if not re.fullmatch(r"[a-z]+(\.[a-z0-9]+)*", cid):
            problems.append(err("commands", f"{cid}: ids are lower-case dotted words"))
        unknown = set(spec) - lib.COMMAND_FIELDS
        if unknown:
            problems.append(err("commands", f"{cid}: unknown field(s) {', '.join(sorted(unknown))}"))
        if not spec.get("title"):
            problems.append(err("commands", f"{cid}: needs a title"))
        if spec.get("handler", "client") not in ("client", "server", "both"):
            problems.append(err("commands", f"{cid}: handler must be client, server or both"))
        if spec.get("when"):
            error = lib.check_when(spec["when"])
            if error:
                problems.append(err("commands", f"{cid}: when '{spec['when']}': {error}"))
            if not spec.get("reason"):
                problems.append(warn("commands", f"{cid}: has a `when` but no `reason` to show when it is disabled"))
        for arg in spec.get("args", []):
            if arg.get("type") not in lib.ARG_TYPES:
                problems.append(err("commands", f"{cid}: argument '{arg.get('name')}' has unknown type {arg.get('type')}"))
            if arg.get("type") == "enum" and not arg.get("values"):
                problems.append(err("commands", f"{cid}: enum argument '{arg.get('name')}' needs values"))
        for alias in spec.get("aliases", []):
            if alias in aliases:
                problems.append(err("commands", f"alias ':{alias}' is used by {aliases[alias]} and {cid}"))
            aliases[alias] = cid
    return problems


def _contexts_together(a: str, b: str) -> bool:
    """Can contexts a and b be active at the same time (so their bindings must not overlap as prefixes)?"""
    kinds = {a.split(".")[0], b.split(".")[0]}
    if a == b:
        return False
    if "layer" in kinds or "overlay" in kinds:
        return False  # modal: a layer/overlay takes its keys first and is left with esc
    if a.startswith("view.") and b.startswith("view."):
        return False  # one view per focused pane
    if a.startswith("mode.") and b.startswith("mode."):
        return "mode.analyse" in (a, b)  # an analysis can sit in any mode's layout, with its keys (keys.js)
    if a.startswith("state.") and b.startswith("state."):
        return False  # one Train state at a time
    for x, y in ((a, b), (b, a)):
        if x.startswith("state.") and y.startswith("mode.") and y != "mode.train":
            return False  # the state contexts belong to Train
    return True


def check_keymap(sources: lib.Sources) -> list[Problem]:
    problems = []
    parsed: dict[str, dict[tuple, tuple[str, list[str]]]] = {}
    for context, bindings in sources.keymap.items():
        if not re.fullmatch(r"global|pane|(mode|view|layer|overlay|state)\.[a-z]+(-[a-z]+)?", context):
            problems.append(err("keymap", f"unknown context '{context}'"))
        parsed[context] = {}
        for seq, value in bindings.items():
            try:
                keys = tuple(lib.parse_seq(seq))
            except ValueError as e:
                problems.append(err("keymap", f"{context}: {e}"))
                continue
            cid, args = lib.parse_binding(value)
            command = sources.commands.get(cid)
            if command is None:
                problems.append(err("keymap", f"{context} '{seq}': unknown command '{cid}'"))
                continue
            problems += _check_args(context, seq, cid, command, args)
            if keys in parsed[context]:
                problems.append(err("keymap", f"{context}: '{seq}' is bound twice"))
            parsed[context][keys] = (cid, args)
            for key in keys:
                if key in lib.BROWSER_RESERVED:
                    problems.append(err("reserved", f"{context} '{seq}': the browser owns '{key}'"))
                if key in lib.ALTGR_CHARS and key not in sources.layout_accept:
                    problems.append(warn("layout", f"{context} '{seq}': '{key}' needs AltGr/Option on QWERTZ or AZERTY"))

    # A key is a command or a prefix, never both (no timeouts), within one context and across active contexts.
    names = list(parsed)
    for a in names:
        problems += _prefix_conflicts(a, parsed[a], a, parsed[a])
    for a, b in combinations(names, 2):
        if _contexts_together(a, b):
            problems += _prefix_conflicts(a, parsed[a], b, parsed[b])

    # Global keys are reserved: no view, pane or mode context may rebind their first key.
    reserved = {keys[0] for keys in parsed.get("global", {})}
    for context, bindings in parsed.items():
        if context == "global" or context.split(".")[0] in ("layer", "overlay"):
            continue
        for keys in bindings:
            if keys[0] in reserved:
                problems.append(err("keymap", f"{context} '{' '.join(keys)}': '{keys[0]}' is reserved by global"))

    for prefix in sources.prefixes:
        keys = tuple(lib.parse_seq(prefix))
        if not any(k[: len(keys)] == keys and len(k) > len(keys) for b in parsed.values() for k in b):
            problems.append(warn("keymap", f"prefix '{prefix}' has no bindings under it"))
    return problems


def _prefix_conflicts(ca, a, cb, b) -> list[Problem]:
    problems = []
    for ka in a:
        for kb in b:
            if len(ka) < len(kb) and kb[: len(ka)] == ka:
                problems.append(
                    err("keymap", f"'{' '.join(ka)}' ({ca}) is a command and a prefix of '{' '.join(kb)}' ({cb})")
                )
            elif ca != cb and len(kb) < len(ka) and ka[: len(kb)] == kb:
                problems.append(
                    err("keymap", f"'{' '.join(kb)}' ({cb}) is a command and a prefix of '{' '.join(ka)}' ({ca})")
                )
    return problems


def _check_args(context, seq, cid, command, args) -> list[Problem]:
    specs = command.get("args", [])
    required = [a for a in specs if not a.get("optional")]
    if len(args) > len(specs):
        return [err("keymap", f"{context} '{seq}': {cid} takes {len(specs)} argument(s)")]
    if len(args) < len(required) and command.get("handler", "client") == "server":
        return [err("keymap", f"{context} '{seq}': {cid} needs {len(required)} argument(s)")]
    problems = []
    for value, spec in zip(args, specs):
        if spec["type"] == "enum" and value not in spec["values"]:
            problems.append(err("keymap", f"{context} '{seq}': '{value}' is not one of {spec['values']}"))
        if spec["type"] == "int" and not value.isdigit():
            problems.append(err("keymap", f"{context} '{seq}': '{value}' is not a number"))
    return problems


def check_reachability(sources: lib.Sources) -> list[Problem]:
    bound = {lib.parse_binding(v)[0] for b in sources.keymap.values() for v in b.values()}
    return [
        err("reachability", f"{cid}: no key and hidden from the command line")
        for cid, spec in sources.commands.items()
        if spec.get("hidden") and not spec.get("internal") and cid not in bound and not spec.get("aliases")
    ]


CMD_IN_TEMPLATE = re.compile(r"""\{%\s*cmd\s+["']([\w.]+)["']|data-cmd=["']([\w.]+)["']""")
JS_HANDLER = re.compile(r"""handle\(\s*["']([\w.]+)["']""")
JS_RUN = re.compile(r"""\brun\(\s*["']([\w.]+)["']""")


def check_references(sources: lib.Sources, templates_dir: Path, js_dir: Path, server_handlers: set[str]) -> list[Problem]:
    problems = []
    for path in sorted(templates_dir.rglob("*.html")):
        for m in CMD_IN_TEMPLATE.finditer(path.read_text()):
            cid = m.group(1) or m.group(2)
            if cid not in sources.commands:
                problems.append(err("references", f"{path.relative_to(templates_dir)}: unknown command '{cid}'"))
    client_handlers = set()
    for path in sorted(js_dir.rglob("*.js")):
        text = path.read_text()
        client_handlers |= set(JS_HANDLER.findall(text))
        for cid in JS_RUN.findall(text):
            if cid not in sources.commands:
                problems.append(err("references", f"{path.name}: runs unknown command '{cid}'"))
    for cid in client_handlers - set(sources.commands):
        problems.append(err("references", f"a client handler exists for unknown command '{cid}'"))
    for cid, spec in sources.commands.items():
        handler = spec.get("handler", "client")
        if handler in ("client", "both") and cid not in client_handlers:
            problems.append(err("implemented", f"{cid}: no client handler (handle('{cid}', …) in static/js)"))
        if handler in ("server", "both") and cid not in server_handlers:
            problems.append(err("implemented", f"{cid}: no server handler (@command('{cid}') in core/server_commands.py or a module in its MODULES)"))
    return problems


CSS_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|(?<![\w.-])(?!0px)\d*\.?\d+px\b|(?<![\w.-])\d*\.?\d+m?s\b")


def check_css_literals(css_dir: Path) -> list[Problem]:
    problems = []
    for path in sorted(css_dir.rglob("*.css")):
        text = re.sub(r"/\*(?!\s*lint-allow).*?\*/", lambda m: " " * len(m.group()), path.read_text(), flags=re.S)
        for number, line in enumerate(text.splitlines(), 1):
            if "lint-allow" in line:
                continue
            for m in CSS_LITERAL.finditer(line):
                problems.append(
                    err("literals", f"{path.name}:{number}: '{m.group()}' — use a token (or mark the line /* lint-allow */)")
                )
    return problems


ALLOWED_LICENCES = (
    "MIT", "BSD", "Apache", "ISC", "0BSD", "Zero-Clause", "ZPL", "Zope", "LGPL", "GPL", "Python Software Foundation",
    "PSF", "OFL", "CC0", "CC-BY", "CC BY", "Unlicense",
)


def _licence_of(dist: importlib.metadata.Distribution) -> str:
    meta = dist.metadata
    expression = meta.get("License-Expression") or ""
    licence = meta.get("License") or ""
    classifiers = " ".join(c for c in meta.get_all("Classifier") or [] if c.startswith("License"))
    return " ".join(x for x in (expression, licence if len(licence) < 200 else "", classifiers) if x)


def check_licences(sources: lib.Sources, pyproject: Path, vendor_dir: Path) -> list[Problem]:
    problems = []
    deps = tomllib.loads(pyproject.read_text())["project"]["dependencies"]
    for dep in deps:
        name = re.split(r"[<>=!~\[ ;]", dep, maxsplit=1)[0]
        try:
            licence = _licence_of(importlib.metadata.distribution(name))
        except importlib.metadata.PackageNotFoundError:
            problems.append(warn("licences", f"{name}: not installed, licence not checked"))
            continue
        if not any(a.lower() in licence.lower() for a in ALLOWED_LICENCES):
            problems.append(err("licences", f"{name}: licence '{licence or 'unknown'}' is not on the allowlist"))
    vendored = sources.licences.get("vendor", {})
    for path in sorted(vendor_dir.glob("*")):
        if path.name.startswith(".") or not path.is_file():
            continue  # licences/ holds the licence texts
        entry = vendored.get(path.name)
        if not entry:
            problems.append(err("licences", f"static/vendor/{path.name}: not listed in design/licences.toml"))
        elif not any(a.lower() in entry.get("licence", "").lower() for a in ALLOWED_LICENCES):
            problems.append(err("licences", f"static/vendor/{path.name}: licence '{entry.get('licence')}' not allowed"))
    return problems


def check_piece_sets(sources: lib.Sources, pieces_dir: Path) -> list[Problem]:
    """Every piece set of the token exists with all 12 pieces, a LICENSE and an allowed licence; nothing extra."""
    problems = []
    names = lib.piece_sets(sources)
    listed = sources.licences.get("pieces", {})
    for name in names:
        folder = pieces_dir / name
        missing = [code for code in lib.PIECE_CODES if not (folder / f"{code}.svg").exists()]
        if missing:
            problems.append(err("pieces", f"{name}: missing {', '.join(missing) or 'folder'}"))
        if not (folder / "LICENSE").exists():
            problems.append(err("pieces", f"{name}: no LICENSE file"))
        licence = listed.get(name, {}).get("licence", "")
        if not licence:
            problems.append(err("pieces", f"{name}: not listed in design/licences.toml [pieces]"))
        elif not any(a.lower() in licence.lower() for a in ALLOWED_LICENCES):
            problems.append(err("pieces", f"{name}: licence '{licence}' doesn't allow redistributing the app"))
        for svg in folder.glob("*.svg"):
            text = svg.read_text()
            if re.search(r"<script|javascript:|\bon[a-z]+\s*=|<foreignObject|href=\"(?!#)", text, re.I):
                problems.append(err("pieces", f"{name}/{svg.name}: scripts or external references are not allowed"))
    for folder in pieces_dir.iterdir() if pieces_dir.exists() else []:
        if folder.is_dir() and folder.name not in names:
            problems.append(err("pieces", f"{folder.name}: a piece set folder that the piece-set token doesn't list"))
    return problems


def run_all(*, design_dir, out_dir, docs_dir, templates_dir, js_dir, css_dir, pyproject, vendor_dir, server_handlers, pieces_dir=None):
    sources = lib.load(design_dir)
    problems = []
    problems += check_themes(sources)
    problems += check_commands(sources)
    problems += check_keymap(sources)
    problems += check_reachability(sources)
    problems += check_references(sources, templates_dir, js_dir, server_handlers)
    problems += check_css_literals(css_dir)
    problems += check_licences(sources, pyproject, vendor_dir)
    if pieces_dir is not None:
        problems += check_piece_sets(sources, pieces_dir)
    stale = lib.generated_is_current(design_dir, out_dir, docs_dir)
    if stale:
        problems.append(err("generated", f"out of date: {', '.join(stale)} — run `manage.py design build`"))
    return problems
