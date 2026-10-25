"""Operations on an analysis tree, and its snapshots for the undo journal (spec 09 §5).

Every change goes through `change(position, label)`: it takes a snapshot before and after, writes a JournalEntry
and rebuilds the position's puzzles from the tree (puzzles.py). `restore` puts a snapshot back by comparing ids, so
nodes keep their ids and the puzzles that point at them stay linked.
"""

from __future__ import annotations

from contextlib import contextmanager

import chess
from django.db import transaction
from django.utils.translation import gettext as _

from spaced_positions import chesslogic
from spaced_positions.core.models import LOCAL_USER
from spaced_positions.library.models import Game
from spaced_positions.training.models import Position, Puzzle

from .models import JournalEntry, Node

NODE_FIELDS = ("parent_id", "order", "uci", "san", "ply", "fen", "comment", "nags", "mark", "color", "shapes", "squares")
NAGS = {1: "!", 2: "?", 3: "!!", 4: "??", 5: "!?", 6: "?!", 7: "□", 10: "=", 13: "∞", 14: "⩲", 15: "⩱", 16: "±", 17: "∓", 18: "+−", 19: "−+"}
MOVE_NAGS = (1, 2, 3, 4, 5, 6, 7)


class TreeError(ValueError):
    """Shown to the user in the status line. `conflict`: a question for the user rather than an error."""

    def __init__(self, message: str, conflict: bool = False):
        super().__init__(message)
        self.conflict = conflict


def is_game(owner) -> bool:
    """A tree belongs to a position or a game (spec 11 §1 Game); games have no puzzles and a fixed start."""
    return isinstance(owner, Game)


def owner_of(**kwargs) -> dict:
    """{'position': p} or {'game': g}: the owner fields of a node or journal entry."""
    owner = kwargs["owner"]
    return {"game": owner} if is_game(owner) else {"position": owner}


def puzzles_of(owner):
    return Puzzle.objects.none() if is_game(owner) else owner.puzzles.all()


def root(position) -> Node:
    node = position.nodes.filter(parent=None).first()
    if node is None:
        node = Node.objects.create(**owner_of(owner=position), fen=position.fen)
    return node


def nodes(position: Position) -> list[Node]:
    return list(position.nodes.order_by("ply", "order", "id"))


def kids_map(all_nodes) -> dict[int | None, list[Node]]:
    kids: dict[int | None, list[Node]] = {}
    for n in sorted(all_nodes, key=lambda n: (n.order, n.id)):
        kids.setdefault(n.parent_id, []).append(n)
    return kids


# ── JSON for the client ───────────────────────────────────────────────────────────────────────────────────────


def node_json(n: Node) -> dict:
    return {
        "id": n.id, "parent": n.parent_id, "order": n.order, "uci": n.uci, "san": n.san, "ply": n.ply, "fen": n.fen,
        "comment": n.comment, "nags": n.nags, "mark": n.mark, "color": n.color, "shapes": n.shapes, "squares": n.squares,
        "eval": None if n.eval_cp is None and n.eval_mate is None else {"cp": n.eval_cp, "mate": n.eval_mate, "depth": n.eval_depth},
    }


def tree_json(position) -> dict:
    r = root(position)
    puzzles = [
        {"id": str(p.uuid), "start": p.start_node_id, "active": p.active, "marks": p.marks, "cards": p.cards.filter(in_solution=True).count()}
        for p in puzzles_of(position).exclude(start_node=None)
    ]
    if is_game(position):
        about = {"id": str(position.uuid), "kind": "game", "title": position.title, "fen": position.fen,
                 "source": " · ".join(x for x in [position.event, position.site, position.date] if x), "objective": "",
                 "difficulty": None, "tags": []}
    else:
        about = {"id": str(position.uuid), "kind": "position", "title": position.title, "fen": position.fen,
                 "source": position.citation, "objective": position.task, "difficulty": position.difficulty,
                 "tags": position.tag_names}
    return {
        "position": about,
        "root": r.id,
        "nodes": [node_json(n) for n in nodes(position)],
        "puzzles": puzzles,
    }


# ── Snapshots and the journal ─────────────────────────────────────────────────────────────────────────────────


def snapshot(position: Position) -> dict:
    return {
        "fen": position.fen,
        "nodes": [{"id": n.id, **{f: getattr(n, f) for f in NODE_FIELDS}} for n in nodes(position)],
        "puzzles": [
            {"id": p.id, "start_node_id": p.start_node_id, "marks": p.marks, "active": p.active}
            for p in puzzles_of(position)
        ],
    }


@transaction.atomic
def restore(position: Position, snap: dict) -> None:
    from . import puzzles as analysis_puzzles

    if not is_game(position):
        position.fen = snap["fen"]
        position.save(update_fields=["fen"])
    wanted = {n["id"]: n for n in snap["nodes"]}
    current = {n.id: n for n in position.nodes.all()}
    position.nodes.exclude(id__in=wanted).delete()
    for data in sorted(snap["nodes"], key=lambda n: n["ply"]):
        node = current.get(data["id"]) or Node(id=data["id"], **owner_of(owner=position))
        for f in NODE_FIELDS:
            setattr(node, f, data[f])
        node.save()
    known = {p["id"]: p for p in snap["puzzles"]}
    for puzzle in puzzles_of(position):
        if puzzle.id in known:
            p = known[puzzle.id]
            puzzle.start_node_id, puzzle.marks, puzzle.active = p["start_node_id"], p["marks"], p["active"]
            puzzle.save(update_fields=["start_node", "marks", "active"])
        elif puzzle.cards.filter(attempts__gt=0).exists():
            puzzle.active = False  # made after the snapshot and trained since: keep its history, out of training
            puzzle.save(update_fields=["active"])
        else:
            puzzle.delete()
    analysis_puzzles.rebuild_all(position)


@contextmanager
def change(position: Position, label: str):
    """Wrap a change: journal entry with before/after snapshots, puzzles rebuilt from the tree."""
    from . import puzzles as analysis_puzzles

    with transaction.atomic():
        before = snapshot(position)
        yield
        analysis_puzzles.rebuild_all(position)
        after = snapshot(position)
        if after != before:
            JournalEntry.objects.filter(user=LOCAL_USER, undone=True).delete()  # a new change ends the redo chain
            JournalEntry.objects.create(user=LOCAL_USER, label=label[:120], before=before, after=after, **owner_of(owner=position))


# ── Moves ─────────────────────────────────────────────────────────────────────────────────────────────────────


def _move(fen: str, uci: str) -> tuple[chess.Board, chess.Move]:
    board = chess.Board(fen)
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        raise TreeError(_("not a move: {move}").format(move=uci)) from None
    if move not in board.legal_moves:
        raise TreeError(_("{move} is not legal here").format(move=uci))
    return board, move


def play(parent: Node, uci: str) -> tuple[Node, bool]:
    """The child of `parent` with this move: the existing one, or a new last child. Returns (node, created)."""
    existing = parent.kids.filter(uci=uci).first()
    if existing:
        return existing, False
    board, move = _move(parent.fen, uci)
    san = board.san(move)
    board.push(move)
    order = parent.kids.count()
    node = Node.objects.create(
        position=parent.position, game=parent.game, parent=parent, order=order, uci=uci, san=san, ply=parent.ply + 1, fen=board.fen(),
    )
    return node, True


def add_line(parent: Node, ucis: list[str]) -> Node:
    node = parent
    for uci in ucis:
        node, _ = play(node, uci)
    return node


def delete(node: Node) -> Node:
    if node.is_root:
        raise TreeError(_("the start position can't be deleted"))
    parent = node.parent
    node.delete()
    for i, kid in enumerate(parent.kids.order_by("order", "id")):
        if kid.order != i:
            kid.order = i
            kid.save(update_fields=["order"])
    return parent


def _put_first(node: Node) -> None:
    siblings = list(node.parent.kids.order_by("order", "id"))
    siblings.remove(node)
    for i, n in enumerate([node, *siblings]):
        if n.order != i:
            n.order = i
            n.save(update_fields=["order"])


def promote(node: Node) -> None:
    """Make the line through `node` the main line: first child at every branch from the root down to it."""
    n = node
    while n.parent_id is not None:
        _put_first(n)
        n = n.parent


def reorder(node: Node, step: int) -> None:
    if node.is_root:
        return
    siblings = list(node.parent.kids.order_by("order", "id"))
    i = siblings.index(node)
    j = max(0, min(len(siblings) - 1, i + step))
    siblings[i], siblings[j] = siblings[j], siblings[i]
    for k, n in enumerate(siblings):
        if n.order != k:
            n.order = k
            n.save(update_fields=["order"])


def edit(node: Node, data: dict) -> None:
    """Comment, annotation symbols, mark, colour, drawings."""
    fields = []
    if "comment" in data:
        node.comment = str(data["comment"])[:5000]
        fields.append("comment")
    if "nags" in data:
        nags = [int(x) for x in data["nags"] if int(x) in NAGS]
        move_nags = [x for x in nags if x in MOVE_NAGS][-1:]  # one move symbol at a time
        node.nags = move_nags + [x for x in nags if x not in MOVE_NAGS][-1:]
        fields.append("nags")
    if "mark" in data:
        node.mark = data["mark"] if data["mark"] in Node.Mark.values else ""
        fields.append("mark")
    if "color" in data:
        node.color = _hex(data["color"])
        fields.append("color")
    if "shapes" in data and isinstance(data["shapes"], list):
        node.shapes = [s for s in data["shapes"] if isinstance(s, dict) and "orig" in s][:64]
        fields.append("shapes")
    if "squares" in data and isinstance(data["squares"], dict):
        node.squares = {k: v for k, v in data["squares"].items() if len(k) == 2}
        fields.append("squares")
    if fields:
        node.save(update_fields=fields)


def _hex(value) -> str:
    from spaced_positions.design.lib import normalise_hex

    return (normalise_hex(str(value)) or "") if value else ""


def change_root(position: Position, fen: str, force: bool = False) -> int:
    """Correct the position (spec 06 §4): the analysis is kept when every move is still legal; otherwise, with
    `force`, the moves are dropped. Returns the number of moves dropped."""
    if is_game(position):
        raise TreeError(_("a game's start position can't be changed"))
    check = chesslogic.check_fen(fen)
    if not check["readable"]:
        raise TreeError(_("not a FEN"))
    all_nodes = nodes(position)
    kids = kids_map(all_nodes)
    r = next(n for n in all_nodes if n.parent_id is None)
    replay: list[tuple[Node, str, str]] = []
    legal = True

    def walk(node, fen_here):
        nonlocal legal
        for kid in kids.get(node.id, []):
            try:
                board, move = _move(fen_here, kid.uci)
            except TreeError:
                legal = False
                return
            san = board.san(move)
            board.push(move)
            replay.append((kid, san, board.fen()))
            walk(kid, board.fen())

    walk(r, check["fen"])
    position.fen = check["fen"]
    position.canonical = check["canonical"] or chesslogic.canonical_fen(check["fen"])
    if legal:
        position.save(update_fields=["fen", "canonical"])
        r.fen = check["fen"]
        r.save(update_fields=["fen"])
        for node, san, after in replay:
            node.san, node.fen = san, after
            node.save(update_fields=["san", "fen"])
        return 0
    if not force:
        dropped = len(all_nodes) - 1
        raise TreeError(_("the analysis has moves that aren't legal in the corrected position ({n} moves would go)").format(n=dropped), conflict=True)
    dropped = len(all_nodes) - 1
    position.save(update_fields=["fen", "canonical"])
    r.kids.all().delete()
    r.fen = check["fen"]
    r.save(update_fields=["fen"])
    return dropped


def path(node: Node) -> list[Node]:
    out = []
    while node is not None:
        out.append(node)
        node = node.parent
    return list(reversed(out))


@transaction.atomic
def create_position(start_fen: str, ucis: list[str], title: str = "", origin: str = "analysis") -> Position:
    """A new position with these moves as its main line (paste → analyse, a board line → analyse)."""
    check = chesslogic.check_fen(start_fen)
    if not check["ok"]:
        raise TreeError(_("not a legal position: {problems}").format(problems="; ".join(p["message"] for p in check["problems"])))
    position = Position.objects.create(fen=check["fen"], canonical=check["canonical"], title=title[:200], origin=origin)
    add_line(root(position), ucis)
    return position

