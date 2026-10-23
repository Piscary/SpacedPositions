"""Puzzles set up in the analysis (spec 04 · Analyse, `p` menu). A puzzle starts after its start node; its marks say
where lines end, which further solver moves are also correct and which further answers count. The solution tree the
trainer uses (training/puzzles.py) is rebuilt from the analysis after every change, so the two never disagree.

The walker keeps chess-study-manager's rules:
    · at every point where the solver moves, the main move is correct, and so are the moves marked "also correct";
    · the opponent answers with the main continuation, or with any answer added to the solution: each answer line is
      a card of its own;
    · a line stops at a move marked "end", or at the end of the analysis, at most MAX_SOLVER_MOVES deep (HARD_CAP
      when an end is marked further down);
    · an answer without a solver move after it isn't an answer line.
"""

from __future__ import annotations

from django.db import transaction

from spaced_positions.training import puzzles as training_puzzles
from spaced_positions.training.models import Puzzle

from . import tree
from .models import Node

MAX_SOLVER_MOVES, HARD_CAP = 8, 40


def solution(start: Node, marks: dict, kids: dict) -> dict | None:
    """The solution tree from `start`, or None when there's nothing to solve."""
    ends, also, extra = set(marks.get("ends", [])), set(marks.get("also", [])), set(marks.get("replies", []))
    if not kids.get(start.id):
        return None

    def end_below(node):
        stack = [node]
        while stack:
            cur = stack.pop()
            if cur.id in ends:
                return True
            stack.extend(k for i, k in enumerate(kids.get(cur.id, [])) if i == 0 or k.id in also or k.id in extra)
        return False

    def point(pos, count):
        options = []
        children = kids.get(pos.id, [])
        for mv in [children[0]] + [k for k in children[1:] if k.id in also]:
            limit = HARD_CAP if end_below(mv) else MAX_SOLVER_MOVES
            mv_kids = kids.get(mv.id, [])
            stop = mv.id in ends or not mv_kids or count + 1 >= limit
            replies = []
            if not stop:
                for i, r in enumerate(mv_kids):
                    if (i == 0 or r.id in extra) and kids.get(r.id) and r.id not in ends:
                        replies.append({"uci": r.uci, "next": point(r, count + 1)})
            options.append({"uci": mv.uci, "replies": replies})
        return {"moves": options}

    return point(start, 0)


def rebuild(puzzle: Puzzle, kids: dict | None = None) -> None:
    """Recompute a puzzle's solution from the analysis; nothing to solve → out of training (drafts keep their marks)."""
    start = puzzle.start_node
    if start is None:
        return
    kids = kids if kids is not None else tree.kids_map(tree.nodes(start.position))
    sol = solution(start, puzzle.marks or {}, kids)
    if sol is None:
        if puzzle.active:
            puzzle.active = False
            puzzle.save(update_fields=["active"])
        return
    puzzle.start_fen = start.fen
    puzzle.solution = sol
    puzzle.save(update_fields=["start_fen", "solution"])
    training_puzzles.sync_cards(puzzle)


def rebuild_all(position) -> None:
    kids = tree.kids_map(tree.nodes(position))
    for puzzle in position.puzzles.exclude(start_node=None).select_related("start_node"):
        rebuild(puzzle, kids)


# ── The `p` menu ──────────────────────────────────────────────────────────────────────────────────────────────


def puzzle_at(node: Node) -> Puzzle | None:
    """The puzzle a node belongs to: the nearest start at the node or above it."""
    starts = {p.start_node_id: p for p in node.position.puzzles.exclude(start_node=None)}
    for n in reversed(tree.path(node)):
        if n.id in starts:
            return starts[n.id]
    return None


def _solver_move(puzzle: Puzzle, node: Node) -> bool:
    return node.ply > puzzle.start_node.ply and (node.ply - puzzle.start_node.ply) % 2 == 1


def _toggle(puzzle: Puzzle, key: str, node_id: int) -> bool:
    marks = dict(puzzle.marks or {})
    ids = list(marks.get(key, []))
    on = node_id not in ids
    marks[key] = ids + [node_id] if on else [i for i in ids if i != node_id]
    puzzle.marks = marks
    puzzle.save(update_fields=["marks"])
    return on


@transaction.atomic
def act(node: Node, action: str) -> str:
    """Apply one puzzle action at `node`; returns a message for the status line."""
    if action == "start":
        existing = node.position.puzzles.filter(start_node=node).first()
        if existing:
            return "A puzzle already starts here"
        if not node.kids.exists():
            raise tree.TreeError("play the solution first: there are no moves after this position")
        Puzzle.objects.create(position=node.position, start_node=node, start_fen=node.fen, solution={"moves": []}, active=False, origin="analysis")
        return "Puzzle set up from here (a draft: p r puts it into training)"
    puzzle = puzzle_at(node)
    if puzzle is None:
        raise tree.TreeError("no puzzle here: p s sets one up at this move")
    if action == "ready":
        puzzle.active = not puzzle.active
        puzzle.save(update_fields=["active"])
        return "Ready for training" if puzzle.active else "Taken out of training (its history stays)"
    if action == "discard":
        if puzzle.cards.filter(attempts__gt=0).exists():
            puzzle.active = False
            puzzle.start_node = None
            puzzle.save(update_fields=["active", "start_node"])
            return "Puzzle removed from the analysis (trained before: its history stays)"
        puzzle.delete()
        return "Puzzle discarded"
    if node.id == puzzle.start_node_id:
        raise tree.TreeError("that's the start of the puzzle: go to a move of its solution")
    if action == "end":
        return "The solution ends here" if _toggle(puzzle, "ends", node.id) else "End removed"
    if action == "also":
        if not _solver_move(puzzle, node):
            raise tree.TreeError("only the solver's moves can be also correct")
        return "Also correct" if _toggle(puzzle, "also", node.id) else "No longer correct"
    if action == "answers":
        if not _solver_move(puzzle, node):
            raise tree.TreeError("on a solver move: every answer to it then continues the puzzle")
        replies = list(node.kids.values_list("id", flat=True))
        marks = dict(puzzle.marks or {})
        current = set(marks.get("replies", []))
        if replies and all(r in current for r in replies[1:]):
            marks["replies"] = [r for r in current if r not in replies]
            message = "Only the main answer counts"
        else:
            marks["replies"] = sorted(current | set(replies[1:]))
            message = f"All {len(replies)} answers count: {len(replies)} lines"
        puzzle.marks = marks
        puzzle.save(update_fields=["marks"])
        return message
    raise tree.TreeError(f"unknown puzzle action {action}")


def roles(position, kids) -> dict:
    """For the move tree: {node id: role} where role is start · solver · answer · end · also, and drafts."""
    out = {}
    for p in position.puzzles.exclude(start_node=None).select_related("start_node"):
        draft = not p.active
        out[p.start_node_id] = {"role": "start", "draft": draft}
        sol = solution(p.start_node, p.marks or {}, kids)
        if not sol:
            continue
        nodes_by_parent_uci = {(n.parent_id, n.uci): n for children in kids.values() for n in children}

        def walk(point, parent_id):
            for i, option in enumerate(point["moves"]):
                node = nodes_by_parent_uci.get((parent_id, option["uci"]))
                if not node:
                    continue
                out.setdefault(node.id, {"role": "solver" if i == 0 else "also", "draft": draft})
                if not option["replies"]:
                    out[node.id] = {**out[node.id], "end": True}
                for reply in option["replies"]:
                    answer = nodes_by_parent_uci.get((node.id, reply["uci"]))
                    if answer:
                        out.setdefault(answer.id, {"role": "answer", "draft": draft})
                        walk(reply["next"], answer.id)

        walk(sol, p.start_node_id)
    return out
