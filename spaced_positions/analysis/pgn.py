"""PGN in and out of move trees (spec 06 §6, 11 §4): variations, comments, NAGs and lichess drawings
(`[%cal Ge2e4]` arrows, `[%csl Rd5]` circles) survive both ways."""

from __future__ import annotations

import io
import re

import chess
import chess.engine
import chess.pgn
import chess.svg

from . import tree

BRUSH_TO_PGN = {"green": "green", "red": "red", "blue": "blue", "yellow": "yellow"}
PGN_TO_BRUSH = {"green": "green", "red": "red", "blue": "blue", "yellow": "yellow"}


# ── Out ───────────────────────────────────────────────────────────────────────────────────────────────────────


def _arrows(node) -> list[chess.svg.Arrow]:
    out = []
    for shape in node.shapes or []:
        try:
            tail = chess.parse_square(shape["orig"])
            head = chess.parse_square(shape.get("dest") or shape["orig"])
        except (KeyError, ValueError):
            continue
        out.append(chess.svg.Arrow(tail, head, color=BRUSH_TO_PGN.get(shape.get("brush"), "green")))
    for square, brush in (node.squares or {}).items():
        try:
            s = chess.parse_square(square)
        except ValueError:
            continue
        out.append(chess.svg.Arrow(s, s, color=BRUSH_TO_PGN.get(brush, "green")))
    return out


def _fill(game_node, node, kids):
    for kid in kids.get(node.id, []):
        move = chess.Move.from_uci(kid.uci)
        child = game_node.add_variation(move, comment=kid.comment or "", nags=set(kid.nags or []))
        arrows = _arrows(kid)
        if arrows:
            child.set_arrows(arrows)
        if kid.pgn_eval_mate is not None or kid.pgn_eval_cp is not None:  # written back as they came (spec 15 §2)
            score = chess.engine.Mate(kid.pgn_eval_mate) if kid.pgn_eval_mate is not None else chess.engine.Cp(kid.pgn_eval_cp)
            child.set_eval(chess.engine.PovScore(score, chess.WHITE), kid.pgn_eval_depth)
        if kid.clock_ms is not None:
            child.set_clock(kid.clock_ms / 1000)
        if kid.emt_ms is not None:
            child.set_emt(kid.emt_ms / 1000)
        _fill(child, kid, kids)


def _game_of(owner, headers: dict) -> chess.pgn.Game:
    nodes = tree.nodes(owner)
    kids = tree.kids_map(nodes)
    root = next(n for n in nodes if n.parent_id is None)
    game = chess.pgn.Game()
    for k, v in headers.items():
        if v:
            game.headers[k] = str(v)
    if owner.fen != chess.STARTING_FEN:
        game.setup(chess.Board(owner.fen))
    game.comment = root.comment or ""
    arrows = _arrows(root)
    if arrows:
        game.set_arrows(arrows)
    _fill(game, root, kids)
    return game


def export_position(position) -> str:
    headers = {"Event": position.title or position.short_id, "Site": position.citation, "Annotator": "Spaced Positions"}
    game = _game_of(position, headers)
    for k in ("White", "Black", "Date", "Round", "Result"):
        if game.headers.get(k) in ("?", "????.??.??"):
            del game.headers[k]
    return str(game)


def export_game(g) -> str:
    headers = {"Event": g.event, "Site": g.site, "Date": g.date or "????.??.??", "Round": g.round, "White": g.white_name or "?",
               "Black": g.black_name or "?", "Result": g.result, "WhiteElo": g.white_elo, "BlackElo": g.black_elo,
               "ECO": g.eco, "Annotator": g.annotator, **(g.headers or {})}
    return str(_game_of(g, headers))


# ── In ────────────────────────────────────────────────────────────────────────────────────────────────────────


def read_games(text: str, limit: int = 20000):
    """The games in a PGN text (python-chess is forgiving; games with errors keep what it could read)."""
    return games_in(io.StringIO(text), limit)


def games_in(stream, limit: int = 20000):
    """The games in a PGN stream (a file of any size: read one game at a time)."""
    found = 0
    while found < limit:
        game = chess.pgn.read_game(stream)
        if game is None:
            return
        if game.next() is None and "FEN" not in game.headers:
            continue  # no moves and no position: text that isn't a game
        found += 1
        yield game


def shapes_of(game_node) -> tuple[list, dict]:
    """Chessground shapes and filled squares from a node's [%cal]/[%csl]."""
    shapes, squares = [], {}
    for arrow in game_node.arrows():
        brush = PGN_TO_BRUSH.get(arrow.color, "green")
        if arrow.tail == arrow.head:
            shapes.append({"orig": chess.square_name(arrow.tail), "brush": brush})
        else:
            shapes.append({"orig": chess.square_name(arrow.tail), "dest": chess.square_name(arrow.head), "brush": brush})
    return shapes, squares


COMMANDS = re.compile(r"\s*\[%(?:cal|csl|eval|clk|emt)\s+[^\]]*\]\s*")


def comment_of(game_node) -> str:
    """The comment without its commands (python-chess keeps them in the text): drawings become shapes, evaluations
    and clocks fields of the move (spec 15)."""
    return COMMANDS.sub(" ", game_node.comment or "").strip()


def annotations_of(game_node) -> dict:
    """The PGN's evaluation ([%eval], from white's side) and clocks ([%clk], [%emt]) of a move, as Node fields."""
    out = {}
    score = game_node.eval()
    if score is not None:
        white = score.white()
        if white.is_mate():
            out["pgn_eval_mate"] = white.mate()
        else:
            out["pgn_eval_cp"] = white.score()
        out["pgn_eval_depth"] = game_node.eval_depth()
    if game_node.clock() is not None:
        out["clock_ms"] = round(game_node.clock() * 1000)
    if game_node.emt() is not None:
        out["emt_ms"] = round(game_node.emt() * 1000)
    return out


def fill_tree(root_node, game: chess.pgn.Game) -> int:
    """Add a parsed game's moves under a tree's root (existing moves are reused). Returns the number of moves added."""
    from .models import Node

    added = 0
    root_node.comment = root_node.comment or comment_of(game)
    root_node.shapes, root_node.squares = shapes_of(game)
    root_node.save()
    stack = [(game, root_node)]
    while stack:
        game_node, node = stack.pop()
        for order, variation in enumerate(game_node.variations):
            uci = variation.move.uci()
            child = node.kids.filter(uci=uci).first()
            if child is None:
                board = game_node.board()
                if variation.move not in board.legal_moves:
                    break
                san = board.san(variation.move)
                board.push(variation.move)
                shapes, squares = shapes_of(variation)
                child = Node.objects.create(
                    position=node.position, game=node.game, parent=node, order=order, uci=uci, san=san, ply=node.ply + 1,
                    fen=board.fen(), comment=comment_of(variation), nags=sorted(n for n in variation.nags if n in tree.NAGS),
                    shapes=shapes, squares=squares, **annotations_of(variation),
                )
                added += 1
            elif (found := annotations_of(variation)) and child.pgn_eval_cp is None and child.pgn_eval_mate is None and child.clock_ms is None:
                Node.objects.filter(pk=child.pk).update(**found)  # a move that was there already: what the PGN adds
            stack.append((variation, child))
    return added
