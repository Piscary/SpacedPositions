"""Modes, views and the default layout of each mode (spec 03, 04).

A layout is a tree: a split `{"type": "split", "dir": "row"|"col", "sizes": [...], "children": [...]}` or a pane
`{"type": "pane", "id": "p1", "view": "board", "group": "A"|None, "pinned": False, "collapsed": False}`.
"""

import copy
import re
from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Mode:
    key: str
    label: str
    leader: str  # the key after ␣
    summary: str
    in_appbar: bool = True


MODES = [
    Mode("home", _("Home"), "h", _("What to do now: due cards, one-key sessions, a paste box, recent work.")),
    Mode("train", _("Train"), "t", _("Solve puzzles: Review, Storm, Streak and custom sessions, with result screens.")),
    Mode("analyse", _("Analyse"), "a", _("One position or game: moves, variations, comments, tags, engine, puzzles.")),
    Mode("collect", _("Collect"), "c", _("Get material in fast: board editor, paste FEN/PGN, rapid entry from a book.")),
    Mode("library", _("Library"), "l", _("Find and organise positions, games, puzzles, players, sources and tags.")),
    Mode("stats", _("Stats"), "s", _("Progress: collection, analysis and training statistics, records, milestones.")),
    Mode("settings", _("Settings"), ",", _("Theme, board, pieces, keymap, training rules and data.")),
    Mode("ui", _("Style guide"), "", _("Every component in every state, and a playground for panes."), in_appbar=False),
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


PLACEHOLDER_HINTS = (("pane.view", _("change view")), ("pane.split.vertical", _("split")), ("help.context", _("keys")))

BOARD_HINTS = (
    ("board.flip", _("flip")),
    ("board.back", _("back")),
    ("board.forward", _("forward")),
    ("board.entry", _("type a move")),
    ("board.setup", _("set up the position")),
    ("board.squaretool", _("square tool")),
    ("board.copyfen", "FEN"),
    ("board.copypgn", "PGN"),
)

MOVES_HINTS = (
    ("analysis.back", _("back")),
    ("analysis.forward", _("forward")),
    ("analysis.sibling next", _("variation")),
    ("analysis.nag 1", "!"),
    ("analysis.mark good", _("mark")),
    ("analysis.comment", _("comment")),
    ("analysis.promote", _("main line")),
    ("analysis.delete", _("delete")),
)

VIEWS = {
    v.key: v
    for v in [
        View(
            "board", _("Board"), "b", _("The interactive board: moves, drawings, setup, typed moves."), "views/board.html",
            hints=BOARD_HINTS,
        ),
        View(
            "moves", _("Moves"), "m", _("The analysis as a book-style move tree."), "views/moves.html",
            hints=MOVES_HINTS,
        ),
        View(
            "engine", _("Engine"), "e", _("Stockfish lines and evaluation."), "views/engine.html",
            hints=(("engine.toggle", _("on / off")), ("engine.best", _("play best")), ("engine.lines", _("lines"))),
        ),
        View(
            "inspector", _("Inspector"), "i", _("The current move and position: comment, marks, tags, source."),
            "views/inspector.html",
            hints=(("analysis.comment", _("comment")), ("analysis.annotate", _("annotate")), ("analysis.tags", _("tags")),
                   ("section.next", _("next section")), ("section.toggle", _("fold"))),
        ),
        View(
            "puzzle", _("Puzzle"), "z", _("The puzzle at the cursor: its start, its solution lines, whether it is in training."),
            "views/puzzle.html",
            hints=(("analysis.puzzle start", _("set up")), ("analysis.puzzle end", _("end")), ("analysis.puzzle also", _("also correct")),
                   ("analysis.puzzle ready", _("training")), ("analysis.subject next", _("next position"))),
        ),
        View(
            "evalgraph", _("Eval graph"), "g", _("The engine's evaluation over the main line; mistakes marked."), "views/evalgraph.html",
            hints=(("engine.evaluate", _("evaluate")), ("analysis.back", _("back")), ("analysis.forward", _("forward"))),
        ),
        View(
            "vargraph", _("Variation graph"), "r", _("The move tree as a graph: the shape of a big analysis."), "views/vargraph.html",
            hints=(("analysis.sibling next", _("variation")), ("analysis.forward", _("forward"))),
        ),
        View(
            "library", _("Library"), "l", _("Positions, games, puzzles and more, with the query bar."), "views/library.html",
            list_view=True,
            hints=(("search.open", _("query")), ("list.select", _("select")), ("library.tag", _("tag")), ("library.train", _("train")),
                   ("library.analyse", _("analyse")), ("library.trash", _("trash")), ("library.display", _("display"))),
        ),
        View(
            "filters", _("Filters"), "f", _("Facets that write into the library query."), "views/filters.html", list_view=True,
            hints=(("list.down", _("down")), ("list.open", _("add / remove")), ("library.exclude", _("exclude"))),
        ),
        View(
            "queue", _("Session"), "q", _("Sessions to start, the running session (clock, combo, lives, prompt), the result."),
            "views/queue.html", lives_in="train",
        ),
        View(
            "entry", _("Entry session"), "s", _("Source, page, diagram number and presets for rapid entry."), "views/entry.html",
            hints=(("collect.save", _("save & next")), ("collect.source", _("source")), ("collect.diagram up", _("diagram +1")),
                   ("collect.tag", _("tag")), ("collect.ready", _("ready"))),
            lives_in="collect",
        ),
        View(
            "chart", _("Stats"), "c", _("Progress in charts and numbers: every number drills down."), "views/stats.html",
            hints=(("chart.next next", _("next chart")), ("chart.cursor next", _("points")), ("chart.drill", _("drill down")),
                   ("chart.table", _("table")), ("stats.period 30d", _("period"))),
        ),
        View(
            "pgn", _("PGN / FEN"), "p", _("The position or game as text; paste to load."), "views/pgn.html",
            hints=(("pane.insert", _("edit")), ("board.copyfen", _("copy FEN")), ("board.copypgn", _("copy PGN")), ("form.submit", _("show what you pasted"))),
        ),
        View(
            "settings", _("Settings"), ",", _("Every setting, searchable: themes, colours, type, board, keys, training, engine, data."),
            "views/settings.html", list_view=True,
            hints=(("search.open", _("search")), ("settings.step next", _("change")), ("settings.edit", _("edit")), ("settings.reset", _("reset")),
                   ("section.next", _("next section"))),
        ),
        View(
            "keymap", _("Keymap"), "K", _("Every command and its keys: ↵ binds new keys."), "views/keymap.html", list_view=True,
            hints=(("search.open", _("search")), ("keymap.bind", _("new keys")), ("keymap.unbind", _("remove"))),
        ),
        View(
            "today", _("Today"), "h", _("What to do now: due cards, one-key sessions, today's numbers, the pattern library."),
            "views/today.html",
            hints=(("train.review", _("review")), ("train.storm 3", _("Storm")), ("train.weakest", _("weakest")), ("section.next", _("next section"))),
        ),
        View(
            "continue", _("Continue"), "o", _("The open analysis, the next diagram, a paste box, recent work."), "views/continue.html",
            list_view=True,
            hints=(("home.analysis", _("analysis")), ("home.collect", _("collect")), ("pane.insert", _("paste box")), ("list.open", _("open"))),
        ),
        View(
            "components", _("Components"), "k", _("Every component in every state."), "views/components.html",
            hints=(
                ("pane.scroll down", _("scroll")), ("pane.scroll halfdown", _("half page")), ("section.next", _("next section")),
                ("section.toggle", _("fold")), ("section.all", _("fold all")), ("pane.insert", _("edit a field")), ("demo.flash", _("flash demo")),
            ),
        ),
    ]
}


# The pane menu (`⋯` in the header, a right click on it, ␣ w w): each view's commands, so everything can be reached
# with the mouse too. Entries are "command [args]" with a label where the command's own title isn't specific enough.
# The pane's own commands (split, view, link group …) follow in every menu (static/js/core/panemenu.js).
VIEW_MENUS = {
    "board": [("board.start", None), ("board.back", None), ("board.forward", None), ("board.end", None), ("board.flip", None),
              ("board.entry", None), ("board.setup", None), ("board.squaretool", None), ("board.cleardrawings", None),
              ("board.copyfen", None), ("board.copypgn", None), ("board.lichess", None), ("board.pieces", None)],
    "moves": [("analysis.start", None), ("analysis.back", None), ("analysis.forward", None), ("analysis.end", None),
              ("analysis.sibling next", _("Next variation at this move")), ("analysis.sibling prev", _("Previous variation at this move")),
              ("analysis.mainline", None), ("analysis.fold", None), ("analysis.foldall", None), ("analysis.comment", None),
              ("analysis.rootcomment", None), ("analysis.annotate", None), ("analysis.mark good", _("Mark as good")),
              ("analysis.mark bad", _("Mark as bad")), ("analysis.mark clear", _("Remove the mark")), ("analysis.tags", None),
              ("analysis.positiontags", None), ("analysis.promote", None), ("analysis.moveup", None), ("analysis.movedown", None),
              ("analysis.delete", None), ("analysis.puzzle start", _("Puzzle: starts after this move")),
              ("analysis.puzzle end", _("Puzzle: the solution ends here")), ("analysis.puzzle ready", _("Puzzle: ready for training")),
              ("analysis.subject next", _("Next position of the list")), ("analysis.subject prev", _("Previous position of the list")),
              ("analysis.newposition", None), ("analysis.moments", None)],
    "engine": [("engine.toggle", None), ("engine.best", None), ("engine.lines", None), ("engine.evaluate", None)],
    "inspector": [("analysis.comment", None), ("analysis.annotate", None), ("analysis.tags", None), ("analysis.positiontags", None),
                  ("library.detect", None), ("section.next", None), ("section.all", None)],
    "puzzle": [("analysis.puzzle start", _("Puzzle: starts after this move")), ("analysis.puzzle end", _("Puzzle: the solution ends here")),
               ("analysis.puzzle also", _("Puzzle: also correct")), ("analysis.puzzle answers", _("Puzzle: all answers count")),
               ("analysis.puzzle ready", _("Puzzle: ready for training")), ("analysis.puzzle discard", _("Puzzle: discard")),
               ("analysis.start", None), ("analysis.subject next", None), ("analysis.subject prev", None)],
    "evalgraph": [("engine.evaluate", None), ("analysis.moments", None), ("analysis.back", None), ("analysis.forward", None)],
    "vargraph": [("analysis.back", None), ("analysis.forward", None), ("analysis.sibling next", _("Next variation at this move")),
                 ("analysis.foldall", None)],
    "library": [("search.open", None), ("library.clear", None), ("library.unfilter", None), ("help.search", None),
                ("list.select", None), ("list.visual", None), ("list.selectall", None), ("library.tag", None), ("library.train", None),
                ("library.analyse", None), ("library.beside", None), ("library.export", None), ("library.copyfen", None),
                ("library.detect", None), ("library.trash", None), ("library.restore", None), ("library.sort", None),
                ("library.foldall", None), ("library.display", None), ("library.savequery", None)],
    "filters": [("library.exclude", None), ("library.clear", None), ("library.unfilter", None), ("help.search", None)],
    "queue": [("train.review", None), ("train.storm 3", _("Storm, 3 minutes")), ("train.streak 0", _("Streak")), ("train.weakest", None),
              ("train.again", None), ("train.hint", None), ("train.giveup", None), ("train.quit", None)],
    "entry": [("collect.save", None), ("collect.saveopen", None), ("collect.source", None), ("collect.page up", _("Next page")),
              ("collect.page down", _("Previous page")), ("collect.diagram up", _("Next diagram number")),
              ("collect.diagram down", _("Previous diagram number")), ("collect.tag", None), ("collect.untag", None),
              ("collect.ready", None), ("collect.duplicate", None), ("board.setup", None)],
    "chart": [("chart.next next", _("Next chart")), ("chart.next prev", _("Previous chart")), ("chart.drill", None), ("chart.table", None),
              ("stats.period 7d", _("Period: 7 days")), ("stats.period 30d", _("Period: 30 days")), ("stats.period 90d", _("Period: 90 days")),
              ("stats.period 1y", _("Period: a year")), ("stats.period all", _("Period: everything"))],
    "pgn": [("pane.insert", None), ("board.copyfen", None), ("board.copypgn", None), ("form.submit", _("Show what you pasted"))],
    "settings": [("search.open", None), ("settings.step next", _("Next value")), ("settings.step prev", _("Previous value")),
                 ("settings.edit", None), ("settings.reset", None), ("settings.keymap", None), ("settings.export", None),
                 ("theme.save", None), ("theme.export", None), ("app.backup", None), ("app.folder", None)],
    "keymap": [("search.open", None), ("keymap.bind", None), ("keymap.unbind", None)],
    "today": [("train.review", None), ("train.storm 3", _("Storm, 3 minutes")), ("train.streak 0", _("Streak")), ("train.weakest", None),
              ("train.again", None), ("pack.starter", None), ("pack.import", None), ("home.dismiss", None)],
    "continue": [("home.analysis", None), ("home.collect", None), ("pane.insert", None), ("list.open", None)],
}


def menu_of(view: str) -> list[dict]:
    """The pane menu's entries of a view, for the page (boot data)."""
    out = []
    for binding, label in VIEW_MENUS.get(view, []):
        cid, *args = binding.split()
        out.append({"cmd": cid, "args": args, "label": str(label) if label else ""})
    return out


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
        split("col", [70, 30], pane("board", "A"), pane("puzzle", "A")),
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
    ), split(
        "row", [50, 50],
        pane("board", "A"),
        split("col", [18, 46, 36], pane("engine", "A"), pane("moves", "A"), pane("inspector", "A")),
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
