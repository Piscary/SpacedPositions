"""Puzzles set up in the analysis (spec 04 · Analyse, `p` menu). A puzzle starts after its start node; its marks say
where lines end, which further solver moves are also correct and which further answers count. The solution tree the
trainer uses (training/puzzles.py) is rebuilt from the analysis after every change, so the two never disagree.

The walker's rules:
    · at every point where the solver moves, the main move is correct, and so are the moves marked "also correct";
    · the opponent answers with the main continuation, or with any answer added to the solution: each answer line is
      a card of its own;
    · a line stops at a move marked "end", or at the end of the analysis, at most MAX_SOLVER_MOVES deep (HARD_CAP
      when an end is marked further down);
    · an answer without a solver move after it isn't an answer line.
"""

from __future__ import annotations

from django.db import transaction
from django.utils.translation import gettext as _

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
    if tree.is_game(position):
        return
    kids = tree.kids_map(tree.nodes(position))
    for puzzle in position.puzzles.exclude(start_node=None).select_related("start_node"):
        rebuild(puzzle, kids)


# ── The `p` menu ──────────────────────────────────────────────────────────────────────────────────────────────


def puzzle_at(node: Node) -> Puzzle | None:
    """The puzzle a node belongs to: the nearest start at the node or above it."""
    if node.game_id:
        return None
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
    if node.game_id:
        raise tree.TreeError(_("puzzles come from positions: :new-position takes this move's position out of the game"))
    if action == "start":
        existing = node.position.puzzles.filter(start_node=node).first()
        if existing:
            return _("A puzzle already starts here")
        if not node.kids.exists():
            raise tree.TreeError(_("play the solution first: there are no moves after this position"))
        Puzzle.objects.create(position=node.position, start_node=node, start_fen=node.fen, solution={"moves": []}, active=False, origin="analysis")
        return _("Puzzle set up from here (a draft: p r puts it into training)")
    puzzle = puzzle_at(node)
    if puzzle is None:
        raise tree.TreeError(_("no puzzle here: p s sets one up at this move"))
    if action == "ready":
        puzzle.active = not puzzle.active
        puzzle.save(update_fields=["active"])
        return _("Ready for training") if puzzle.active else _("Taken out of training (its history stays)")
    if action == "discard":
        if puzzle.cards.filter(attempts__gt=0).exists():
            puzzle.active = False
            puzzle.start_node = None
            puzzle.save(update_fields=["active", "start_node"])
            return _("Puzzle removed from the analysis (trained before: its history stays)")
        puzzle.delete()
        return _("Puzzle discarded")
    if node.id == puzzle.start_node_id:
        raise tree.TreeError(_("that's the start of the puzzle: go to a move of its solution"))
    if action == "end":
        return _("The solution ends here") if _toggle(puzzle, "ends", node.id) else _("End removed")
    if action == "also":
        if not _solver_move(puzzle, node):
            raise tree.TreeError(_("only the solver's moves can be also correct"))
        return _("Also correct") if _toggle(puzzle, "also", node.id) else _("No longer correct")
    if action == "answers":
        if not _solver_move(puzzle, node):
            raise tree.TreeError(_("on a solver move: every answer to it then continues the puzzle"))
        replies = list(node.kids.values_list("id", flat=True))
        marks = dict(puzzle.marks or {})
        current = set(marks.get("replies", []))
        if replies and all(r in current for r in replies[1:]):
            marks["replies"] = [r for r in current if r not in replies]
            message = _("Only the main answer counts")
        else:
            marks["replies"] = sorted(current | set(replies[1:]))
            message = _("All {n} answers count: {n} lines").format(n=len(replies))
        puzzle.marks = marks
        puzzle.save(update_fields=["marks"])
        return message
    raise tree.TreeError(_("unknown puzzle action {action}").format(action=action))


def roles(position, kids) -> dict:
    """For the move tree: {node id: role} where role is start · solver · answer · end · also, and drafts."""
    out = {}
    if tree.is_game(position):
        return out
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


# ── The Puzzle pane ──────────────────────────────────────────────────────────────────────────────────────────────


def _start_label(node: Node) -> str:
    if node.parent_id is None:
        return _("from the start position")
    return _("after {move}").format(move=_move_text(node))


def _move_text(node: Node) -> str:
    fields = node.fen.split()  # the position after the move: its side to move is the other one
    full = int(fields[5]) if len(fields) > 5 else 1
    return f"{full}.{node.san}" if fields[1] == "b" else f"{full - 1}…{node.san}"


def _cursor_role(puzzle: Puzzle | None, node: Node, role: dict) -> tuple[str, str]:
    """(kind, sentence): where the cursor is in the puzzle, in words."""
    if puzzle is None:
        return "none", _("No puzzle at this move. A puzzle starts after a move (or at the start position): the solver plays the moves that follow.")
    if node.id == puzzle.start_node_id:
        return "start", _("The puzzle starts here: the side to move finds the solution.")
    kind = role.get("role")
    end = " " + _("The line ends here.") if role.get("end") else ""
    if kind == "solver":
        return "solver", _("A solver move: the trainer expects it.") + end
    if kind == "also":
        return "also", _("Also correct: the trainer accepts it too, and goes on with the main line.") + end
    if kind == "answer":
        return "answer", _("An answer: the trainer plays it for the opponent.") + end
    if _solver_move(puzzle, node):
        return "outside", _("Not part of the solution: the solver's move here is another one. Also correct (p a) accepts it too.")
    return "outside", _("Not part of the solution: an answer the trainer doesn't play. All answers count (p o) on the move before adds it.")


def pane(position, node: Node) -> dict:
    """What the Puzzle pane shows for the move at the cursor: the puzzles of the position, the one the cursor is in,
    the cursor's role in it, its lines (the cards), and for every action whether it applies here and why not."""
    if tree.is_game(position):
        return {"game": True}
    all_nodes = tree.nodes(position)
    kids = tree.kids_map(all_nodes)
    by_id = {n.id: n for n in all_nodes}
    puzzle = puzzle_at(node)
    the_roles = roles(position, kids)
    kind, where = _cursor_role(puzzle, node, the_roles.get(node.id, {}))
    puzzles = []
    for p in position.puzzles.exclude(start_node=None).select_related("start_node").order_by("start_node__ply", "id"):
        puzzles.append({"id": p.id, "node": p.start_node_id, "label": _start_label(p.start_node), "active": p.active,
                        "current": puzzle is not None and p.id == puzzle.id,
                        "cards": p.cards.filter(in_solution=True).count()})
    out = {"game": False, "node": node, "puzzles": puzzles, "puzzle": puzzle, "kind": kind, "where": where}
    starts_here = position.puzzles.filter(start_node=node).exists()
    out["can_start"] = "" if not starts_here and kids.get(node.id) else (
        _("a puzzle already starts here") if starts_here else _("play the solution first: there are no moves after this one"))
    if puzzle is None:
        return out
    start = by_id[puzzle.start_node_id]
    marks = puzzle.marks or {}
    solver = _solver_move(puzzle, node)
    on_start = node.id == puzzle.start_node_id
    out.update({
        "start_label": _start_label(start),
        "side": _("White") if start.fen.split()[1] == "w" else _("Black"),
        "cards": puzzle.cards.filter(in_solution=True).count(),
        "attempts": sum(puzzle.cards.values_list("attempts", flat=True)),
        "can_end": _("go to a move after the start") if on_start else "",
        "end_on": node.id in marks.get("ends", []),
        "can_also": "" if solver and not on_start else _("go to one of the solver's moves"),
        "also_on": node.id in marks.get("also", []),
        "can_answers": "" if solver and not on_start else _("go to one of the solver's moves"),
        # one sentence for the buttons that don't apply here
        "why": _("At the start: go to a move of the solution to mark it.") if on_start else (
            "" if solver else _("On an answer: Also correct and All answers count need one of the solver's moves.")),
    })
    # the lines (one card each), as text, each going to its last move on a click
    sol = solution(start, marks, kids)
    shown = []
    for ucis in (training_puzzles.lines(sol) if sol else []):
        parent, moves = start, []
        for uci in ucis:
            child = next((k for k in kids.get(parent.id, []) if k.uci == uci), None)
            if child is None:
                break
            moves.append(child)
            parent = child
        if moves:
            shown.append({"node": moves[-1].id, "moves": moves, "has_cursor": node in moves})
    out["can_ready"] = "" if shown else _("nothing to solve yet: play the solution after the start")
    out["lines"] = shown[:12]
    out["more_lines"] = max(0, len(shown) - 12)
    out["solver_moves"] = sorted({training_puzzles.solver_moves([m.uci for m in line["moves"]]) for line in shown})
    return out
