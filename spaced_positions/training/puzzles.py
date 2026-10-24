"""Solution trees, their lines (cards), and what the trainer in the browser gets.

A solution tree starts where the solver moves:

    point  = {"moves": [option, …]}              options[0] is the main move; the others are also correct
    option = {"uci": "e2e4", "replies": [reply]} no replies: the line ends here, solved
    reply  = {"uci": "e7e5", "next": point}      replies[0] is the main answer; each answer is a line of its own

Rules (the same in the trainer, static/js/islands/train.js):
    · at a point, any option is correct, and so is any mating move when the main move mates;
    · the opponent answers along the card's line while the solver follows it; after another correct move it answers
      with that option's main reply;
    · every way the opponent can answer along the main moves is one card (`lines`).
"""

from __future__ import annotations

import chess
from django.db import transaction

from spaced_positions import chesslogic

from .models import Card, Position, Puzzle

MAX_SOLVER_MOVES = 12


def from_line(ucis: list[str]) -> dict:
    """A tree from one line [solver, answer, solver, …]. A trailing answer (no solver move after it) is dropped."""
    if len(ucis) % 2 == 0:
        ucis = ucis[:-1]
    if not ucis:
        raise ValueError("a puzzle needs at least one move")

    def point(i):
        option = {"uci": ucis[i], "replies": []}
        if i + 2 < len(ucis) and (i // 2) + 1 < MAX_SOLVER_MOVES:
            option["replies"].append({"uci": ucis[i + 1], "next": point(i + 2)})
        return {"moves": [option]}

    return point(0)


def lines(tree: dict) -> list[list[str]]:
    """Every way the opponent can answer along the main solver moves: [[uci, …], …], the main line first."""

    def walk(p):
        main = p["moves"][0]
        if not main["replies"]:
            return [[main["uci"]]]
        out = []
        for reply in main["replies"]:
            for rest in walk(reply["next"]):
                out.append([main["uci"], reply["uci"], *rest])
        return out

    return walk(tree)


def validate(start_fen: str, tree: dict) -> None:
    """Every move of the tree is legal from where it is played. Raises ValueError."""

    def walk(board, p):
        if not p.get("moves"):
            raise ValueError("a point without moves")
        for option in p["moves"]:
            move = chess.Move.from_uci(option["uci"])
            if move not in board.legal_moves:
                raise ValueError(f"illegal solver move {option['uci']} in {board.fen()}")
            board.push(move)
            for reply in option.get("replies", []):
                answer = chess.Move.from_uci(reply["uci"])
                if answer not in board.legal_moves:
                    raise ValueError(f"illegal answer {reply['uci']} in {board.fen()}")
                board.push(answer)
                walk(board, reply["next"])
                board.pop()
            board.pop()

    walk(chess.Board(start_fen), tree)


def _mirror_uci(uci: str) -> str:
    move = chess.Move.from_uci(uci)
    return chess.Move(chess.square_mirror(move.from_square), chess.square_mirror(move.to_square), move.promotion).uci()


def mirror(tree: dict) -> dict:
    """The tree for the mirrored position (colours swapped, board flipped top to bottom)."""
    return {
        "moves": [
            {"uci": _mirror_uci(o["uci"]), "replies": [{"uci": _mirror_uci(r["uci"]), "next": mirror(r["next"])} for r in o.get("replies", [])]}
            for o in tree["moves"]
        ]
    }


def first_move_only(tree: dict) -> dict:
    return {"moves": [{"uci": o["uci"], "replies": []} for o in tree["moves"]]}


def solver_moves(line: list[str]) -> int:
    return (len(line) + 1) // 2


def difficulty(card: Card) -> float:
    """For ordering Storm and Streak (easy → hard): the position's difficulty, else the line's length."""
    if card.puzzle.position.difficulty:
        return card.puzzle.position.difficulty + solver_moves(card.line) / 100
    return min(5, 1 + solver_moves(card.line))


@transaction.atomic
def sync_cards(puzzle: Puzzle) -> list[Card]:
    """One card per line; cards of lines no longer in the solution stay (history) but leave training."""
    found = []
    keys = set()
    for line in lines(puzzle.solution):
        key = " ".join(line)
        keys.add(key)
        card, _ = Card.objects.get_or_create(puzzle=puzzle, line_key=key, defaults={"line": line})
        if not card.in_solution:
            card.in_solution = True
            card.save(update_fields=["in_solution"])
        found.append(card)
    puzzle.cards.exclude(line_key__in=keys).update(in_solution=False)
    return found


@transaction.atomic
def create_from_line(start_fen: str, ucis: list[str], title: str = "", origin: str = "board") -> Puzzle:
    """A puzzle from a line played on a board (`:puzzle`): the side to move solves, the moves alternate. It is made
    through the analysis (the line becomes the main line from the start, the solution ends where the line ends), so
    every puzzle can be edited in Analyse."""
    from spaced_positions.analysis import puzzles as analysis_puzzles
    from spaced_positions.analysis import tree

    check = chesslogic.check_fen(start_fen)
    if not check["ok"]:
        raise ValueError("the start position isn't legal: " + "; ".join(p["message"] for p in check["problems"]))
    validate(check["fen"], from_line(ucis))
    position = Position.alive.filter(canonical=check["canonical"]).first()
    if position is None:
        position = tree.create_position(check["fen"], [], title=title, origin=origin)
    root = tree.root(position)
    existing = position.puzzles.filter(start_node=root).first()
    if existing is not None:
        if any(line[: len(ucis)] == list(ucis) for line in lines(existing.solution)):
            return existing  # the same puzzle again
        raise ValueError(f"{position.short_id} already has a puzzle from this position: edit it in Analyse (p a, p o)")
    with tree.change(position, "Puzzle from a board line"):
        end = tree.add_line(root, ucis)
        tree.promote(end)
        analysis_puzzles.act(root, "start")
        puzzle = position.puzzles.get(start_node=root)
        puzzle.marks = {"ends": [end.id], "also": [], "replies": []}
        puzzle.active = True
        puzzle.origin = origin
        puzzle.save(update_fields=["marks", "active", "origin"])
    puzzle.refresh_from_db()
    return puzzle


def payload(card: Card, *, mirrored: bool = False, first_only: bool = False) -> dict:
    """What the trainer needs for one card. Mirrored: the colours swapped, so a white puzzle is solved as black."""
    puzzle, position = card.puzzle, card.puzzle.position
    fen, tree, line = puzzle.start_fen, puzzle.solution, list(card.line)
    if mirrored:
        fen = chess.Board(fen).mirror().fen()
        tree = mirror(tree)
        line = [_mirror_uci(u) for u in line]
    if first_only:
        tree = first_move_only(tree)
        line = line[:1]
    side = fen.split()[1]
    return {
        "card": str(card.uuid),
        "puzzle": str(puzzle.uuid),
        "position": str(position.uuid),
        "startNode": puzzle.start_node_id,
        "fen": fen,
        "solver": side,
        "tree": tree,
        "line": line,
        "mirrored": mirrored,
        "firstOnly": first_only,
        "stage": card.stage,
        "title": position.title,
        "source": position.citation,
        "objective": position.task_for(side),
        "tags": position.tag_names,
        "difficulty": position.difficulty,
    }
