"""Modes, views and the default layout of each mode (spec 03, 04).

A layout is a tree: a split `{"type": "split", "dir": "row"|"col", "sizes": [...], "children": [...]}` or a pane
`{"type": "pane", "id": "p1", "view": "board", "group": "A"|None, "pinned": False, "collapsed": False}`.
Phase 0 ships the layouts with placeholder views; each placeholder names the phase that builds the real view.
"""

import copy
from dataclasses import dataclass


@dataclass(frozen=True)
class Mode:
    key: str
    label: str
    leader: str  # the key after ␣
    phase: int
    summary: str
    in_appbar: bool = True


MODES = [
    Mode("home", "Home", "h", 2, "What to do now: due cards, one-key sessions, a paste box, recent work."),
    Mode("train", "Train", "t", 2, "Solve puzzles: Review, Storm, Streak and custom sessions, with result screens."),
    Mode("analyse", "Analyse", "a", 3, "One position or game: moves, variations, comments, tags, engine, puzzles."),
    Mode("collect", "Collect", "c", 4, "Get material in fast: board editor, paste FEN/PGN, rapid entry from a book."),
    Mode("library", "Library", "l", 4, "Find and organise positions, games, puzzles, players, sources and tags."),
    Mode("stats", "Stats", "s", 5, "Progress: collection, analysis and training statistics, records, milestones."),
    Mode("settings", "Settings", ",", 6, "Theme, board, pieces, keymap, training rules and data."),
    Mode("ui", "Style guide", "", 0, "Every component in every state, and a playground for panes.", in_appbar=False),
]
MODES_BY_KEY = {m.key: m for m in MODES}


@dataclass(frozen=True)
class View:
    key: str
    label: str
    picker: str | None  # key in the view picker (spec 08 · Window)
    phase: int  # 0 = available now
    summary: str
    template: str | None = None
    list_view: bool = False  # binds the list keys (context view.list)
    hints: tuple = ()  # (command [args], short label) for the pane footer's key strip


PLACEHOLDER_HINTS = (("pane.view", "change view"), ("pane.split.vertical", "split"), ("help.context", "keys"))
LIST_HINTS = (
    ("list.down", "down"),
    ("list.up", "up"),
    ("list.select", "select"),
    ("list.visual", "range"),
    ("list.open", "open"),
    ("list.first", "first"),
)

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

VIEWS = {
    v.key: v
    for v in [
        View(
            "board", "Board", "b", 0, "The interactive board: moves, drawings, setup, typed moves.", "views/board.html",
            hints=BOARD_HINTS,
        ),
        View("moves", "Moves", "m", 3, "The analysis as a book-style move tree."),
        View("engine", "Engine", "e", 3, "Stockfish lines and evaluation."),
        View("inspector", "Inspector", "i", 3, "The current move and position: comment, tags, marks, puzzle setup."),
        View("evalgraph", "Eval graph", "g", 3, "Evaluation over a game."),
        View("vargraph", "Variation graph", "r", 3, "The move tree as a graph."),
        View("library", "Library", "l", 4, "Positions, games, puzzles and more, with the query bar."),
        View("filters", "Filters", None, 4, "Facets that write into the library query."),
        View("queue", "Session", "q", 2, "The running training session: clock, combo, lives, prompt."),
        View("entry", "Entry session", None, 4, "Source, page, diagram number and presets for rapid entry."),
        View("chart", "Chart", "c", 5, "Statistics charts."),
        View(
            "pgn", "PGN / FEN", "p", 0, "The position or game as text; paste to load.", "views/pgn.html",
            hints=(("pane.insert", "edit"), ("board.copyfen", "copy FEN"), ("board.copypgn", "copy PGN"), ("form.submit", "show what you pasted")),
        ),
        View("tags", "Tags", "t", 4, "The tag vocabulary."),
        View("settings", "Settings", None, 6, "Every setting, searchable."),
        View(
            "welcome", "About this mode", None, 0, "What this mode is for.", "views/welcome.html",
            hints=(("pane.scroll down", "scroll"), ("mode.ui", "style guide"), ("cmdline.open", "commands"), ("help.context", "keys")),
        ),
        View(
            "notes", "Notes", "n", 0, "A text field: try the Insert layer.", "views/notes.html",
            hints=(("pane.insert", "edit"), ("form.submit", "submit"), ("layer.escape", "leave the field")),
        ),
        View("demo", "Demo list", "d", 0, "A keyboard list: j/k, x, v, Enter.", "views/demo_list.html", True, LIST_HINTS),
        View("preview", "Linked preview", "v", 0, "Follows the cursor of its link group.", "views/preview.html",
             hints=(("pane.group", "link group"), ("pane.pin", "pin"))),
        View(
            "components", "Components", "k", 0, "Every component in every state.", "views/components.html",
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
    "home": split("row", [55, 45], pane("welcome"), pane("demo", "A")),
    "train": split("row", [64, 36], pane("board", "A"), pane("queue", "A")),
    "analyse": split(
        "row",
        [50, 50],
        split("col", [78, 22], pane("board", "A"), pane("evalgraph", "A")),
        split("col", [16, 50, 34], pane("engine", "A"), pane("moves", "A"), pane("inspector", "A")),
    ),
    "collect": split("row", [55, 45], pane("board", "A"), split("col", [55, 45], pane("entry"), pane("pgn", "A"))),
    "library": split("row", [18, 44, 38], pane("filters"), pane("demo", "A"), pane("board", "A")),
    "stats": split("row", [60, 40], pane("chart"), pane("welcome")),
    "settings": split("row", [65, 35], pane("settings"), pane("welcome")),
    "ui": split("row", [56, 44], pane("components"), split("col", [42, 58], pane("demo", "A"), pane("board", "A"))),
}


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
    """Check a layout posted by the client before storing it."""
    if depth > 12 or not isinstance(node, dict):
        return False
    if node.get("type") == "pane":
        return node.get("view") in VIEWS and isinstance(node.get("id"), str)
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
