"""Settings that aren't design tokens (spec 07 §5, 04 · Settings): training, keys, engine, sound and display. Stored
in Preferences.settings as {name: value}; `:set name=value` handles them like tokens, and every one has a row in the
Settings mode."""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext as _t
from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Setting:
    name: str
    section: str
    label: str
    type: str  # bool | enum | int | text
    default: object
    help: str
    values: tuple = ()
    low: int = 0
    high: int = 0


SETTINGS = [
    Setting("ui.language", "Language", _("Language"), "enum", "auto", _("The language of the app: automatic follows the browser"),
            values=("auto", "en", "de", "fr", "it")),
    Setting("tags.language", "Language", _("Tag names"), "enum", "ui", _("The language of tag names: as the app, or one of its own"),
            values=("ui", "en", "de", "fr", "it")),
    Setting("training.new-per-day", "Training", _("New cards a day"), "int", 20, _("How many new cards Review introduces a day"), low=0, high=200),
    Setting("training.move-hints", "Training", _("Hints while typing a move"), "bool", True,
            _("When you type a move in a puzzle (i), arrows show the moves that fit what you typed so far")),
    Setting("training.move-complete", "Training", _("Complete typed moves"), "bool", True,
            _("In a puzzle, a typed move is played as soon as only one legal move fits; off: type the whole move")),
    Setting("training.storm-pace", "Training", _("Storm pace"), "enum", "medium", _("The Storm clock: fast, medium or slow (adaptive to your solving times)"),
            values=("fast", "medium", "slow")),
    Setting("keys.keycaps", "Keys", _("Keycaps"), "enum", "full", _("Keys on buttons: full, compact (only the key strips), off"),
            values=("full", "compact", "off")),
    Setting("keys.intro", "Keys", _("Key intro on Home"), "bool", True, _("Home shows seven keys to try, each ticked off once you have used it")),
    Setting("keys.teach", "Keys", _("Teach keys"), "bool", True, _("After a click, the status line shows the key for it")),
    Setting("keys.whichkey", "Keys", _("Which-key panel"), "bool", True, _("The panel that lists what can follow a prefix (␣, g …)")),
    Setting("board.letters", "Board", _("Piece letters"), "enum", "en",
            _("Letters of the pieces in moves, typed and shown: English (KQRBN), German (KDTLS), French (RDTFC) or Italian (RDTAC)"),
            values=("en", "de", "fr", "it")),
    Setting("engine.source", "Engine", _("Engine"), "enum", "browser", _("Stockfish in the browser (WASM), or a local Stockfish program through the app"),
            values=("browser", "local")),
    Setting("engine.path", "Engine", _("Local engine"), "text", "", _("Path of a UCI engine program (empty: stockfish on the PATH)")),
    Setting("engine.lines", "Engine", _("Lines"), "int", 3, _("How many best lines the engine shows"), low=1, high=5),
    Setting("engine.depth", "Engine", _("Depth"), "int", 24, _("How deep the engine searches"), low=8, high=40),
    Setting("engine.threads", "Engine", _("Threads"), "int", 2, _("Threads of the local engine"), low=1, high=64),
    Setting("engine.hash", "Engine", _("Hash (MB)"), "int", 256, _("Hash table of the local engine"), low=16, high=4096),
    Setting("engine.arrows", "Engine", _("Arrows"), "bool", True, _("The engine's best moves as arrows on the board")),
    Setting("sound.on", "Sound and motion", _("Sounds"), "bool", False, _("A click on a move, a tone on right and wrong, a chord on a record")),
    Setting("display.ticker", "Sound and motion", _("Counting numbers"), "bool", True, _("Numbers count up on the result screen and in Stats")),
    Setting("packs.author", "Packs", _("Your name in packs"), "text", "", _("Shown to students with the packs you make (else the player marked as you)")),
    Setting("app.updates", "App", _("Look for updates"), "bool", False, _("At most once a day, ask GitHub whether there is a newer version (nothing else is sent)")),
    Setting("app.autostop", "App", _("Stop by itself"), "bool", False, _("The app stops 10 minutes after the last tab was closed (started without a console: on)")),
]
BY_NAME = {s.name: s for s in SETTINGS}


def parse(name: str, raw: str) -> tuple[object, str | None]:
    """(value, error) for `:set name=raw`."""
    s = BY_NAME.get(name)
    if s is None:
        return None, _t("no setting '{name}'").format(name=name)
    raw = raw.strip().strip("'\"")
    if s.type == "bool":
        if raw.lower() in ("on", "true", "yes", "1"):
            return True, None
        if raw.lower() in ("off", "false", "no", "0"):
            return False, None
        return None, _t("{name}: on or off").format(name=name)
    if s.type == "enum":
        return (raw, None) if raw in s.values else (None, _t("{name}: one of {values}").format(name=name, values=", ".join(s.values)))
    if s.type == "int":
        try:
            value = int(raw)
        except ValueError:
            return None, _t("{name}: a number").format(name=name)
        if not s.low <= value <= s.high:
            return None, f"{name}: {s.low}–{s.high}"  # noqa: i18n (numbers only)
        return value, None
    return raw[:500], None


LANGUAGE_NAMES = {"en": "English", "de": "Deutsch", "fr": "Français", "it": "Italiano"}
LANGUAGES_TRANSLATED = {"en": _("English"), "de": _("German"), "fr": _("French"), "it": _("Italian")}


def value_words(value) -> str:
    """What a value can be found by in the completion: its label, and a language also by its name in the app's
    language (`ger` finds `de`, Deutsch)."""
    return f"{value_label(value)} {LANGUAGES_TRANSLATED.get(value, '')} {value}".strip()


def value_label(value) -> str:
    """How a setting's value is shown (a language by its own name, everything else translated)."""
    from django.utils.translation import pgettext

    if value in LANGUAGE_NAMES:
        return LANGUAGE_NAMES[value]
    if value == "auto":
        return _t("automatic")
    if value == "ui":
        return _t("as the app")
    return pgettext("setting value", str(value))


def values(stored: dict | None = None) -> dict:
    """Every setting with its value (stored, else the default)."""
    stored = stored or {}
    return {s.name: stored.get(s.name, s.default) for s in SETTINGS}


def get(name: str):
    from .models import Preferences

    return values(Preferences.current().settings).get(name)
