"""Modes, views and the default layout of each mode (spec 03, 04).

A layout is a tree: a split `{"type": "split", "dir": "row"|"col", "sizes": [...], "children": [...]}` or a pane
`{"type": "pane", "id": "p1", "view": "board", "group": "A"|None, "pinned": False, "collapsed": False}`.
Phase 0 ships the layouts with placeholder views; each placeholder names the phase that builds the real view.
"""

import copy
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Mode:
    key: str
    label: str
    leader: str  # the key after ␣
    summary: str
    in_appbar: bool = True


MODES = [
    Mode("home", "Home", "h", "What to do now: due cards, one-key sessions, a paste box, recent work."),
    Mode("train", "Train", "t", "Solve puzzles: Review, Storm, Streak and custom sessions, with result screens."),
    Mode("analyse", "Analyse", "a", "One position or game: moves, variations, comments, tags, engine, puzzles."),
    Mode("collect", "Collect", "c", "Get material in fast: board editor, paste FEN/PGN, rapid entry from a book."),
    Mode("library", "Library", "l", "Find and organise positions, games, puzzles, players, sources and tags."),
    Mode("stats", "Stats", "s", "Progress: collection, analysis and training statistics, records, milestones."),
    Mode("settings", "Settings", ",", "Theme, board, pieces, keymap, training rules and data."),
    Mode("ui", "Style guide", "", "Every component in every state, and a playground for panes.", in_appbar=False),
]
MODES_BY_KEY = {m.key: m for m in MODES}


@dataclass(frozen=True)
class View:
    key: str
    label: str
    picker: str | None  # key in the view picker (spec 08 · Window)
    summary: str
    template: str | None = None
    list_view: bool = False  # binds the list keys (context view.list)
    hints: tuple = ()  # (command [args], short label) for the pane footer's key strip
    lives_in: str | None = None  # a view whose keys and state belong to one mode: elsewhere its pane says so

    @property
    def home_command(self) -> str:
        return f"mode.{self.lives_in}"

    @property
    def home_label(self) -> str:
        return MODES_BY_KEY[self.lives_in].label if self.lives_in else ""


PLACEHOLDER_HINTS = (("pane.view", "change view"), ("pane.split.vertical", "split"), ("help.context", "keys"))

BOARD_HINTS = (
    ("board.flip", "flip"),
    ("board.back", "back"),
    ("board.forward", "forward"),
    ("board.entry", "type a move"),
    ("board.setup", "set up"),
    ("board.squaretool", "square tool"),
    ("board.copyfen", "FEN"),
    ("board.copypgn", "PGN"),
)

MOVES_HINTS = (
    ("analysis.back", "back"),
    ("analysis.forward", "forward"),
    ("analysis.sibling next", "variation"),
    ("analysis.nag 1", "!"),
    ("analysis.mark good", "mark"),
    ("analysis.comment", "comment"),
    ("analysis.promote", "main line"),
    ("analysis.delete", "delete"),
)

VIEWS = {
    v.key: v
    for v in [
        View(
            "board", "Board", "b", "The interactive board: moves, drawings, setup, typed moves.", "views/board.html",
            hints=BOARD_HINTS,
        ),
        View(
            "moves", "Moves", "m", "The analysis as a book-style move tree.", "views/moves.html",
            hints=MOVES_HINTS,
        ),
        View(
            "engine", "Engine", "e", "Stockfish lines and evaluation.", "views/engine.html",
            hints=(("engine.toggle", "on / off"), ("engine.best", "play best"), ("engine.lines", "lines")),
        ),
        View(
            "inspector", "Inspector", "i", "The current move and position: comment, marks, puzzle setup.",
            "views/inspector.html",
            hints=(("analysis.comment", "comment"), ("analysis.annotate", "annotate"), ("analysis.puzzle start", "puzzle"),
                   ("section.next", "next section"), ("section.toggle", "fold")),
        ),
        View(
            "evalgraph", "Eval graph", "g", "The engine's evaluation over the main line; mistakes marked.", "views/evalgraph.html",
            hints=(("engine.evaluate", "evaluate"), ("analysis.back", "back"), ("analysis.forward", "forward")),
        ),
        View(
            "vargraph", "Variation graph", "r", "The move tree as a graph: the shape of a big analysis.", "views/vargraph.html",
            hints=(("analysis.sibling next", "variation"), ("analysis.forward", "forward")),
        ),
        View(
            "library", "Library", "l", "Positions, games, puzzles and more, with the query bar.", "views/library.html",
            list_view=True,
            hints=(("search.open", "query"), ("list.select", "select"), ("library.tag", "tag"), ("library.train", "train"),
                   ("library.analyse", "analyse"), ("library.trash", "trash"), ("library.display", "display")),
        ),
        View(
            "filters", "Filters", "f", "Facets that write into the library query.", "views/filters.html", list_view=True,
            hints=(("list.down", "down"), ("list.open", "add / remove"), ("library.exclude", "exclude")),
        ),
        View(
            "queue", "Session", "q", "Sessions to start, the running session (clock, combo, lives, prompt), the result.",
            "views/queue.html", lives_in="train",
        ),
        View(
            "entry", "Entry session", "s", "Source, page, diagram number and presets for rapid entry.", "views/entry.html",
            hints=(("collect.save", "save & next"), ("collect.source", "source"), ("collect.diagram up", "diagram +1"),
                   ("collect.tag", "tag"), ("collect.ready", "ready")),
            lives_in="collect",
        ),
        View(
            "chart", "Stats", "c", "Progress in charts and numbers: every number drills down.", "views/stats.html",
            hints=(("chart.next next", "next chart"), ("chart.cursor next", "points"), ("chart.drill", "drill down"),
                   ("chart.table", "table"), ("stats.period 30d", "period")),
        ),
        View(
            "pgn", "PGN / FEN", "p", "The position or game as text; paste to load.", "views/pgn.html",
            hints=(("pane.insert", "edit"), ("board.copyfen", "copy FEN"), ("board.copypgn", "copy PGN"), ("form.submit", "show what you pasted")),
        ),
        View(
            "settings", "Settings", ",", "Every setting, searchable: themes, colours, type, board, keys, training, engine, data.",
            "views/settings.html", list_view=True,
            hints=(("search.open", "search"), ("settings.step next", "change"), ("settings.edit", "edit"), ("settings.reset", "reset"),
                   ("section.next", "next section")),
        ),
        View(
            "keymap", "Keymap", "K", "Every command and its keys: ↵ binds new keys.", "views/keymap.html", list_view=True,
            hints=(("search.open", "search"), ("keymap.bind", "new keys"), ("keymap.unbind", "remove")),
        ),
        View(
            "today", "Today", "h", "What to do now: due cards, one-key sessions, today's numbers, the pattern library.",
            "views/today.html",
            hints=(("train.review", "review"), ("train.storm 3", "Storm"), ("train.weakest", "weakest"), ("section.next", "next section")),
        ),
        View(
            "continue", "Continue", "o", "The open analysis, the next diagram, a paste box, recent work.", "views/continue.html",
            list_view=True,
            hints=(("home.analysis", "analysis"), ("home.collect", "collect"), ("pane.insert", "paste box"), ("list.open", "open")),
        ),
        View(
            "components", "Components", "k", "Every component in every state.", "views/components.html",
            hints=(
                ("pane.scroll down", "scroll"), ("pane.scroll halfdown", "half page"), ("section.next", "next section"),
                ("section.toggle", "fold"), ("section.all", "fold all"), ("pane.insert", "edit a field"), ("demo.flash", "flash demo"),
            ),
        ),
    ]
}


def pane(view, group=None, **extra):
    return {"type": "pane", "view": view, "group": group, "pinned": False, "collapsed": False} | extra


def split(direction, sizes, *children):
    return {"type": "split", "dir": direction, "sizes": list(sizes), "children": list(children)}


DEFAULTS = {
    "home": split("row", [55, 45], pane("today"), pane("continue", "A")),
    "train": split("row", [60, 40], pane("board", "A"), pane("queue", "A")),
    "analyse": split(
        "row",
        [50, 50],
        pane("board", "A"),
        split("col", [18, 46, 36], pane("engine", "A"), pane("moves", "A"), pane("inspector", "A")),
    ),
    "collect": split("row", [55, 45], pane("board", "A"), split("col", [55, 45], pane("entry"), pane("pgn", "A"))),
    "library": split("row", [20, 50, 30], pane("filters", "A"), pane("library", "A"), pane("board", "A")),
    "stats": pane("chart"),
    "settings": split("row", [62, 38], pane("settings"), pane("keymap")),
    "ui": split("row", [56, 44], pane("components"), split("col", [42, 58], pane("library", "A"), pane("board", "A"))),
}


# Defaults of earlier versions: a saved layout that is still exactly one of them was never changed by the user, so
# it moves to the current default (the placeholders of a mode become its real views).
OLD_DEFAULTS = {
    "library": [split("row", [18, 44, 38], pane("filters"), pane("demo", "A"), pane("board", "A"))],
    "analyse": [split(
        "row", [50, 50],
        split("col", [78, 22], pane("board", "A"), pane("evalgraph", "A")),
        split("col", [16, 50, 34], pane("engine", "A"), pane("moves", "A"), pane("inspector", "A")),
    )],
    "collect": [],
    "home": [split("row", [55, 45], pane("welcome"), pane("demo", "A"))],
    "stats": [split("row", [60, 40], pane("chart"), pane("welcome"))],
    "settings": [split("row", [65, 35], pane("settings"), pane("welcome"))],
}


def _shape(node: dict):
    if node["type"] == "pane":
        return ("pane", node.get("view"), node.get("group"), bool(node.get("pinned")), bool(node.get("collapsed")))
    return ("split", node["dir"], tuple(round(s) for s in node["sizes"]), tuple(_shape(c) for c in node["children"]))


def is_old_default(mode: str, layout: dict) -> bool:
    return any(_shape(layout) == _shape(old) for old in OLD_DEFAULTS.get(mode, []))


def default_layout(mode: str) -> dict:
    layout = copy.deepcopy(DEFAULTS[mode])
    number_panes(layout, assign_ids=True)
    return layout


def number_panes(layout: dict, assign_ids=False) -> list[dict]:
    """Panes in reading order (depth-first); sets `n` (1-based) and, if asked, ids p1, p2, …"""
    panes = []

    def walk(node):
        if node["type"] == "pane":
            panes.append(node)
        else:
            for child in node["children"]:
                walk(child)

    walk(layout)
    for i, p in enumerate(panes, 1):
        p["n"] = i
        if assign_ids or not p.get("id"):
            p["id"] = f"p{i}"
    return panes


def for_template(node: dict) -> dict:
    """A copy of the tree where each split's children carry their size (Django templates can't zip lists)."""
    if node["type"] == "pane":
        return node
    return node | {"items": [{"size": s, "node": for_template(c)} for s, c in zip(node["sizes"], node["children"])]}


def valid_layout(node, depth=0) -> bool:
    """Check a layout (posted by the client, or stored) before using it. A view the app no longer has is allowed: its
    pane says so (components/pane.html), and the rest of the arrangement stays as the user made it."""
    if depth > 12 or not isinstance(node, dict):
        return False
    if node.get("type") == "pane":
        view = node.get("view")
        return isinstance(view, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,30}", view) is not None and isinstance(node.get("id"), str)
    if node.get("type") == "split":
        children, sizes = node.get("children"), node.get("sizes")
        return (
            node.get("dir") in ("row", "col")
            and isinstance(children, list)
            and isinstance(sizes, list)
            and len(children) == len(sizes) >= 1
            and all(isinstance(s, (int, float)) and s >= 0 for s in sizes)
            and all(valid_layout(c, depth + 1) for c in children)
        )
    return False
