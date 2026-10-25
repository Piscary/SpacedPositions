"""Settings that aren't design tokens (spec 07 §5, 04 · Settings): training, keys, engine, sound and display. Stored
in Preferences.settings as {name: value}; `:set name=value` handles them like tokens, and every one has a row in the
Settings mode."""

from __future__ import annotations

from dataclasses import dataclass


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
    Setting("training.new-per-day", "Training", "New cards a day", "int", 20, "How many new cards Review introduces a day", low=0, high=200),
    Setting("training.storm-pace", "Training", "Storm pace", "enum", "medium", "The Storm clock: fast, medium or slow (adaptive to your solving times)",
            values=("fast", "medium", "slow")),
    Setting("keys.keycaps", "Keys", "Keycaps", "enum", "full", "Keys on buttons: full, compact (only the key strips), off",
            values=("full", "compact", "off")),
    Setting("keys.teach", "Keys", "Teach keys", "bool", True, "After a click, the status line shows the key for it"),
    Setting("keys.whichkey", "Keys", "Which-key panel", "bool", True, "The panel that lists what can follow a prefix (␣, g …)"),
    Setting("board.letters", "Board", "Piece letters", "enum", "en", "Letters in the board editor and typed moves shown: English (KQRBN) or German (KDTLS)",
            values=("en", "de")),
    Setting("engine.source", "Engine", "Engine", "enum", "browser", "Stockfish in the browser (WASM), or a local Stockfish program through the app",
            values=("browser", "local")),
    Setting("engine.path", "Engine", "Local engine", "text", "", "Path of a UCI engine program (empty: stockfish on the PATH)"),
    Setting("engine.lines", "Engine", "Lines", "int", 3, "How many best lines the engine shows", low=1, high=5),
    Setting("engine.depth", "Engine", "Depth", "int", 24, "How deep the engine searches", low=8, high=40),
    Setting("engine.threads", "Engine", "Threads", "int", 2, "Threads of the local engine", low=1, high=64),
    Setting("engine.hash", "Engine", "Hash (MB)", "int", 256, "Hash table of the local engine", low=16, high=4096),
    Setting("engine.arrows", "Engine", "Arrows", "bool", True, "The engine's best moves as arrows on the board"),
    Setting("sound.on", "Sound and motion", "Sounds", "bool", False, "A click on a move, a tone on right and wrong, a chord on a record"),
    Setting("display.ticker", "Sound and motion", "Counting numbers", "bool", True, "Numbers count up on the result screen and in Stats"),
    Setting("app.autostop", "App", "Stop by itself", "bool", False, "The app stops 10 minutes after the last tab was closed (started without a console: on)"),
]
BY_NAME = {s.name: s for s in SETTINGS}


def parse(name: str, raw: str) -> tuple[object, str | None]:
    """(value, error) for `:set name=raw`."""
    s = BY_NAME.get(name)
    if s is None:
        return None, f"no setting '{name}'"
    raw = raw.strip().strip("'\"")
    if s.type == "bool":
        if raw.lower() in ("on", "true", "yes", "1"):
            return True, None
        if raw.lower() in ("off", "false", "no", "0"):
            return False, None
        return None, f"{name}: on or off"
    if s.type == "enum":
        return (raw, None) if raw in s.values else (None, f"{name}: one of {', '.join(s.values)}")
    if s.type == "int":
        try:
            value = int(raw)
        except ValueError:
            return None, f"{name}: a number"
        if not s.low <= value <= s.high:
            return None, f"{name}: {s.low}–{s.high}"
        return value, None
    return raw[:500], None


def values(stored: dict | None = None) -> dict:
    """Every setting with its value (stored, else the default)."""
    stored = stored or {}
    return {s.name: stored.get(s.name, s.default) for s in SETTINGS}


def get(name: str):
    from .models import Preferences

    return values(Preferences.current().settings).get(name)
