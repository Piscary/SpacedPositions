"""Distinct test positions (a position is stored once: the same FEN twice is a duplicate)."""

import chess

MATE_IN_1 = "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1"  # 1.Rd8#
KING_SQUARES = ["g1", "h1", "f1", "e1", "e2", "f2", "g2", "h2", "e3", "f3", "g3", "h3", "a1", "b1", "a2", "b2", "a3", "b3",
                "c2", "c3", "a4", "b4", "c4", "e4", "f4", "g4", "h4", "a5", "b5", "c5"]
OPENING_FIRST = ["e2e4", "d2d4", "c2c4", "g1f3", "b2b3", "g2g3", "f2f4", "b1c3", "a2a3", "h2h3", "e2e3", "d2d3", "c2c3",
                 "b2b4", "g2g4", "a2a4", "h2h4", "f2f3", "g1h3", "b1a3"]


def back_rank(i: int) -> str:
    """The back-rank mate (1.Rd8#) with the white king on the i-th free square."""
    board = chess.Board(MATE_IN_1)
    board.remove_piece_at(chess.G1)
    board.set_piece_at(chess.parse_square(KING_SQUARES[i % len(KING_SQUARES)]), chess.Piece(chess.KING, chess.WHITE))
    if KING_SQUARES[i % len(KING_SQUARES)] in ("f2", "g2", "h2"):  # those squares hold pawns: move the pawn up
        board.set_piece_at(chess.parse_square(KING_SQUARES[i % len(KING_SQUARES)][0] + "3"), chess.Piece(chess.PAWN, chess.WHITE))
    return board.fen()


def opening(i: int) -> tuple[str, list[str]]:
    """A position after a different first move, black to play e7e5 then white a developing move."""
    board = chess.Board()
    board.push_uci(OPENING_FIRST[i % len(OPENING_FIRST)])
    for reply in ("e7e5", "d7d5", "c7c5", "g8f6"):
        move = chess.Move.from_uci(reply)
        if move in board.legal_moves:
            return board.fen(), [reply]
    raise AssertionError("no reply")


def opening_line(i: int) -> tuple[str, list[str]]:
    """White to move after a different pair of first moves, and a 3-ply line (white solves with two moves)."""
    board = chess.Board()
    board.push_uci(OPENING_FIRST[i % len(OPENING_FIRST)])
    board.push_uci("a7a6" if i < len(OPENING_FIRST) else "h7h6")
    fen = board.fen()
    line = []
    for candidates in (("e2e4", "d2d4", "e2e3", "d2d3", "c2c4"), ("e7e5", "d7d5", "c7c5", "g8f6"), ("g1f3", "b1c3", "f1e2", "h2h3")):
        move = next(chess.Move.from_uci(u) for u in candidates if chess.Move.from_uci(u) in board.legal_moves)
        line.append(move.uci())
        board.push(move)
    return fen, line
