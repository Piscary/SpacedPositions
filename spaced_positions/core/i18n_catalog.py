"""The translation catalogues (spec 09 §14), built by `manage.py i18n`:

    extract   find every text of the interface and update locale/<lang>/LC_MESSAGES/django.po (new texts are added
              untranslated, texts no longer used are dropped)
    build     compile the .po files: django.mo for Django, static/i18n/<lang>.json for the page's JavaScript
    check     every text translated, placeholders and markup kept, compiled files up to date (part of `design check`)
    missing   the untranslated texts of all languages as JSON (for translating them)
    fill      merge a JSON file {"[context\\u0004]text": {"de": …, "fr": …, "it": …}} into the .po files

Where texts are found:
    templates   {% translate %}, {% blocktranslate %} and _("…") in tag arguments
    Python      _(…), gettext(…), gettext_lazy(…), gettext_noop(…), pgettext(…), ngettext(…) with literal strings
    JavaScript  tr("…"), trc("context", "…"), trn("one", "many", n) with literal strings (static/js/core/i18n.js)
    design      the commands' title, group and reason, the keymap's prefix names, the tokens' descriptions,
                labels and values, the settings' values
Placeholders: {name} (Python str.format and JavaScript) or %(name)s (blocktranslate); a translation keeps them all.
"""

from __future__ import annotations

import ast
import json
import re
import struct
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.utils.translation.template import templatize

from .i18n_names import token_label

LANGUAGES = ["de", "fr", "it"]
PLURAL = {"de": "nplurals=2; plural=(n != 1);", "fr": "nplurals=2; plural=(n > 1);", "it": "nplurals=2; plural=(n != 1);"}
NAMES = {"de": "German (Switzerland)", "fr": "French (Switzerland)", "it": "Italian (Switzerland)"}
EOT = "\x04"  # between a context and its text, as in gettext

PACKAGE = Path(settings.PACKAGE_DIR)
LOCALE = PACKAGE / "locale"
JS_OUT = PACKAGE / "static" / "i18n"
SKIP_TEMPLATES = {"views/components.html"}  # the style guide is for developers

PY_FUNCS = {"_": "s", "_t": "s", "gettext": "s", "gettext_lazy": "s", "gettext_noop": "s", "pgettext": "cs", "pgettext_lazy": "cs",
            "ngettext": "sp", "ngettext_lazy": "sp", "npgettext": "csp"}


@dataclass
class Entry:
    msgid: str
    plural: str = ""
    context: str = ""
    refs: list[str] = field(default_factory=list)
    msgstr: str = ""
    msgstr_plural: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.context}{EOT}{self.msgid}" if self.context else self.msgid

    @property
    def translated(self) -> bool:
        return all(self.msgstr_plural) and len(self.msgstr_plural) == 2 if self.plural else bool(self.msgstr)


# ── Finding the texts ─────────────────────────────────────────────────────────────────────────────────────────


class Found:
    def __init__(self):
        self.entries: dict[str, Entry] = {}

    def add(self, msgid: str, ref: str, plural: str = "", context: str = ""):
        if not msgid or not msgid.strip():
            return
        e = Entry(msgid, plural, context)
        if e.key not in self.entries:
            self.entries[e.key] = e
        entry = self.entries[e.key]
        if plural and not entry.plural:
            entry.plural = plural
        if ref not in entry.refs and len(entry.refs) < 3:
            entry.refs.append(ref)


def _python(found: Found, source: str, ref: str):
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
        shape = PY_FUNCS.get(name)
        if not shape or len(node.args) < len(shape):
            continue
        values = []
        for arg in node.args[: len(shape)]:
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                break
            values.append(arg.value)
        if len(values) < len(shape):
            continue
        parts = dict(zip(shape, values))
        found.add(parts["s"], f"{ref}:{node.lineno}", parts.get("p", ""), parts.get("c", ""))


def _template(found: Found, source: str, ref: str):
    _python_like(found, templatize(source), ref)


TOKEN_CALL = re.compile(r"\b(_|gettext|pgettext|ngettext|npgettext)\(")


def _python_like(found: Found, text: str, ref: str):
    """templatize() output isn't Python, but its gettext calls are: read each call's literal arguments."""
    for m in TOKEN_CALL.finditer(text):
        name, i, args = m.group(1), m.end(), []
        while True:
            lit = re.match(r"\s*u?('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")\s*(,|\))", text[i:], re.S)
            if not lit:
                break
            args.append(ast.literal_eval(lit.group(1)))
            i += lit.end()
            if lit.group(2) == ")":
                break
        shape = PY_FUNCS.get(name, "s")
        if len(args) >= len(shape):
            parts = dict(zip(shape, args))
            found.add(parts["s"], ref, parts.get("p", ""), parts.get("c", ""))


JS_STRING = r'"(?:[^"\\\n]|\\.)*"'
JS_CALLS = [
    (re.compile(rf"\btr\(\s*({JS_STRING})"), "s"),
    (re.compile(rf"\btrc\(\s*({JS_STRING})\s*,\s*({JS_STRING})"), "cs"),
    (re.compile(rf"\btrn\(\s*({JS_STRING})\s*,\s*({JS_STRING})"), "sp"),
]


def _javascript(found: Found, source: str, ref: str):
    for pattern, shape in JS_CALLS:
        for m in pattern.finditer(source):
            parts = dict(zip(shape, (json.loads(g) for g in m.groups())))
            line = source.count("\n", 0, m.start()) + 1
            found.add(parts["s"], f"{ref}:{line}", parts.get("p", ""), parts.get("c", ""))


def _design(found: Found):
    design = Path(settings.DESIGN_DIR)
    for path in sorted((design / "commands").glob("*.toml")):
        for cid, c in tomllib.loads(path.read_text()).items():
            if isinstance(c, dict):
                for key in ("title", "group", "reason"):
                    if c.get(key):
                        found.add(c[key], f"design/commands/{path.name}:{cid}")
    keymap = tomllib.loads((design / "keymap" / "default.toml").read_text())
    for label in keymap.get("prefixes", {}).values():
        found.add(label, "design/keymap/default.toml")
    tokens = tomllib.loads((design / "tokens.toml").read_text())["tokens"]
    for name, spec in tokens.items():
        found.add(token_label(name), f"design/tokens.toml:{name}")
        if spec.get("description"):
            found.add(spec["description"], f"design/tokens.toml:{name}")
        for value in spec.get("values", []):
            if isinstance(value, str):
                found.add(value, f"design/tokens.toml:{name}", context="setting value")
    from . import settings as user_settings

    for s in user_settings.SETTINGS:
        for value in s.values:
            found.add(value, f"core/settings.py:{s.name}", context="setting value")


def extract() -> dict[str, Entry]:
    found = Found()
    for path in sorted((PACKAGE / "templates").rglob("*.html")):
        rel = path.relative_to(PACKAGE / "templates").as_posix()
        if rel not in SKIP_TEMPLATES:
            _template(found, path.read_text(), f"templates/{rel}")
    for path in sorted(PACKAGE.rglob("*.py")):
        rel = path.relative_to(PACKAGE).as_posix()
        if "/migrations/" in rel or rel.startswith("core/i18n_catalog") or (rel.startswith("design/") and rel != "design/lib.py"):
            continue
        _python(found, path.read_text(), rel)
    for path in sorted((PACKAGE / "static" / "js").rglob("*.js")):
        _javascript(found, path.read_text(), path.relative_to(PACKAGE).as_posix())
    _design(found)
    return found.entries


# ── .po files ─────────────────────────────────────────────────────────────────────────────────────────────────


def _quote(s: str) -> str:
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t")
    if "\n" not in s:
        return f'"{s}"'
    lines = s.split("\n")
    parts = [line + "\\n" for line in lines[:-1]] + ([lines[-1]] if lines[-1] else [])
    return '""\n' + "\n".join(f'"{p}"' for p in parts)


def _unquote(s: str) -> str:
    return ast.literal_eval(s) if s else ""


def po_path(lang: str) -> Path:
    return LOCALE / lang / "LC_MESSAGES" / "django.po"


def read_po(path: Path) -> dict[str, Entry]:
    entries: dict[str, Entry] = {}
    if not path.exists():
        return entries
    current: dict = {}
    last = None

    def flush():
        if "msgid" in current and current["msgid"]:
            e = Entry(current["msgid"], current.get("msgid_plural", ""), current.get("msgctxt", ""), current.get("refs", []),
                      current.get("msgstr", ""), [current.get(f"msgstr[{i}]", "") for i in range(2)] if current.get("msgid_plural") else [])
            entries[e.key] = e

    for raw in path.read_text().splitlines() + [""]:
        line = raw.strip()
        if not line:
            flush()
            current, last = {}, None
        elif line.startswith("#:"):
            current.setdefault("refs", []).extend(line[2:].split())
        elif line.startswith("#"):
            continue
        elif line.startswith('"'):
            current[last] = current.get(last, "") + _unquote(line)
        else:
            key, _, value = line.partition(" ")
            current[key], last = _unquote(value), key
    return entries


def write_po(lang: str, entries: dict[str, Entry]):
    path = po_path(lang)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = [
        f"# Spaced Positions: {NAMES[lang]}. Built with `manage.py i18n extract`; translate the msgstr lines.",
        'msgid ""',
        'msgstr ""',
        f'"Language: {lang}\\n"',
        '"MIME-Version: 1.0\\n"',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
        f'"Plural-Forms: {PLURAL[lang]}\\n"',
        "",
    ]
    for e in entries.values():
        if e.refs:
            out.append("#: " + " ".join(e.refs))
        if e.context:
            out.append(f"msgctxt {_quote(e.context)}")
        out.append(f"msgid {_quote(e.msgid)}")
        if e.plural:
            out.append(f"msgid_plural {_quote(e.plural)}")
            forms = (e.msgstr_plural + ["", ""])[:2]
            out += [f"msgstr[{i}] {_quote(forms[i])}" for i in range(2)]
        else:
            out.append(f"msgstr {_quote(e.msgstr)}")
        out.append("")
    path.write_text("\n".join(out))


def merge(lang: str, found: dict[str, Entry]) -> tuple[int, int]:
    """The .po file of a language with exactly the found texts; earlier translations are kept. (added, dropped)."""
    old = read_po(po_path(lang))
    merged = {}
    for key, e in found.items():
        prev = old.get(key)
        merged[key] = Entry(e.msgid, e.plural, e.context, e.refs, prev.msgstr if prev else "",
                            (prev.msgstr_plural if prev and prev.msgstr_plural else []) if e.plural else [])
    write_po(lang, merged)
    return len(set(found) - set(old)), len(set(old) - set(found))


# ── Compiled files ────────────────────────────────────────────────────────────────────────────────────────────


def mo_bytes(lang: str, entries: dict[str, Entry]) -> bytes:
    """GNU .mo (what Python's gettext reads): the header, then each translated text."""
    header = f"Language: {lang}\nMIME-Version: 1.0\nContent-Type: text/plain; charset=UTF-8\nPlural-Forms: {PLURAL[lang]}\n"
    pairs = [("", header)]
    for e in entries.values():
        if not e.translated:
            continue
        source = (f"{e.context}{EOT}" if e.context else "") + e.msgid + (f"\0{e.plural}" if e.plural else "")
        pairs.append((source, "\0".join(e.msgstr_plural) if e.plural else e.msgstr))
    pairs.sort(key=lambda p: p[0].encode())
    ids = [k.encode() for k, _ in pairs]
    strs = [v.encode() for _, v in pairs]
    n = len(pairs)
    start = 7 * 4 + 16 * n
    offsets, blob = [], b""
    for s in ids:
        offsets.append((len(s), start + len(blob)))
        blob += s + b"\0"
    for s in strs:
        offsets.append((len(s), start + len(blob)))
        blob += s + b"\0"
    head = struct.pack("<7I", 0x950412DE, 0, n, 7 * 4, 7 * 4 + 8 * n, 0, 0)
    return head + b"".join(struct.pack("<2I", *o) for o in offsets) + blob


def js_catalog(entries: dict[str, Entry]) -> dict:
    out = {}
    for e in entries.values():
        if e.translated:
            out[e.key] = e.msgstr_plural if e.plural else e.msgstr
    return out


def compiled(lang: str) -> dict[Path, bytes]:
    entries = read_po(po_path(lang))
    return {
        po_path(lang).with_suffix(".mo"): mo_bytes(lang, entries),
        JS_OUT / f"{lang}.json": json.dumps(js_catalog(entries), ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(),
    }


def build() -> list[Path]:
    written = []
    for lang in LANGUAGES:
        for path, data in compiled(lang).items():
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists() or path.read_bytes() != data:
                path.write_bytes(data)
                written.append(path)
    return written


# ── Checks ────────────────────────────────────────────────────────────────────────────────────────────────────

PLACEHOLDER = re.compile(r"\{\w+\}|%\(\w+\)[sd]|%[sd]")
MARKUP = re.compile(r"</?(?:a|b|br|code|em|i|kbd|p|span|strong)\b")


def _same_marks(source: str, translation: str) -> bool:
    return (sorted(PLACEHOLDER.findall(source)) == sorted(PLACEHOLDER.findall(translation))
            and sorted(MARKUP.findall(source)) == sorted(MARKUP.findall(translation)))


def check() -> list[str]:
    errors = []
    found = extract()
    for lang in LANGUAGES:
        entries = read_po(po_path(lang))
        new = [k for k in found if k not in entries]
        if new:
            errors.append(f"{lang}: {len(new)} texts not in the catalogue yet (manage.py i18n extract), e.g. {new[0]!r}")
        untranslated = [e.key for e in entries.values() if not e.translated]
        if untranslated:
            errors.append(f"{lang}: {len(untranslated)} texts not translated, e.g. {untranslated[0]!r}")
        for e in entries.values():
            if not e.translated:
                continue
            pairs = [(e.msgid, e.msgstr)] if not e.plural else [(e.plural, f) for f in e.msgstr_plural]
            for source, translation in pairs:
                # a singular may name the number in words; only the plural form must keep every placeholder
                if not _same_marks(source, translation) and not (e.plural and source == e.plural and "{n}" not in translation
                                                                and _same_marks(source.replace("{n}", ""), translation)):
                    errors.append(f"{lang}: {e.key!r}: placeholders or markup differ in {translation!r}")
        for path, data in compiled(lang).items():
            if not path.exists() or path.read_bytes() != data:
                errors.append(f"{path.relative_to(PACKAGE)} is out of date (manage.py i18n build)")
    return errors


def missing() -> dict:
    out = {}
    for lang in LANGUAGES:
        for e in read_po(po_path(lang)).values():
            if not e.translated:
                out.setdefault(e.key, {"plural": e.plural} if e.plural else {})
    return out


def fill(translations: dict) -> int:
    """Merge {"key": {"de": "…" or ["one", "many"], …}}; returns how many texts were filled."""
    n = 0
    for lang in LANGUAGES:
        entries = read_po(po_path(lang))
        for key, langs in translations.items():
            e = entries.get(key)
            value = langs.get(lang)
            if e is None or value is None:
                continue
            if e.plural:
                e.msgstr_plural = list(value) if isinstance(value, list) else [value, value]
            else:
                e.msgstr = value
            n += 1
        write_po(lang, entries)
    return n
