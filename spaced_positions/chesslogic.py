"""All chess rules on the server go through this module (python-chess underneath; spec 09 §13).

check_fen       a FEN's problems, each with a fix where one exists (spec 06 §4 · live validation)
canonical_fen   placement, side, castling, legal en passant: the identity of a position (duplicates)
parse_paste     what pasted text is: FEN, several FENs, PGN, a lichess link (spec 06 §6)
board_svg       a static board (MiniBoard, Diagram; spec 05 · F)
"""

from __future__ import annotations

import io
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlparse

import chess
import chess.pgn

START_FEN = chess.STARTING_FEN

# python-chess status flags → message. Fixable ones carry a fix code.
STATUS_MESSAGES = [
    (chess.STATUS_EMPTY, "the board is empty", None),
    (chess.STATUS_NO_WHITE_KING, "no white king", None),
    (chess.STATUS_NO_BLACK_KING, "no black king", None),
    (chess.STATUS_TOO_MANY_KINGS, "too many kings", None),
    (chess.STATUS_TOO_MANY_WHITE_PAWNS, "more than 8 white pawns", None),
    (chess.STATUS_TOO_MANY_BLACK_PAWNS, "more than 8 black pawns", None),
    (chess.STATUS_PAWNS_ON_BACKRANK, "a pawn on the first or last rank", None),
    (chess.STATUS_TOO_MANY_WHITE_PIECES, "more than 16 white pieces", None),
    (chess.STATUS_TOO_MANY_BLACK_PIECES, "more than 16 black pieces", None),
    (chess.STATUS_OPPOSITE_CHECK, "the side not to move is in check", "side"),
    (chess.STATUS_TOO_MANY_CHECKERS, "the king is in check from too many pieces", None),
    (chess.STATUS_IMPOSSIBLE_CHECK, "this check can't arise in a game", None),
    (chess.STATUS_INVALID_EP_SQUARE, "the en passant square is not possible", "ep"),
]


def _castling_message(board: chess.Board) -> str | None:
    clean = board.clean_castling_rights()
    if clean == board.castling_rights:
        return None
    bad = []
    for flag, rook_square, label in (
        (chess.BB_H1, chess.H1, "K"), (chess.BB_A1, chess.A1, "Q"), (chess.BB_H8, chess.H8, "k"), (chess.BB_A8, chess.A8, "q"),
    ):
        if board.castling_rights & flag and not clean & flag:
            color = chess.WHITE if label.isupper() else chess.BLACK
            king_home = chess.E1 if color else chess.E8
            if board.king(color) != king_home:
                reason = "king not on " + chess.square_name(king_home)
            else:
                reason = "rook not on " + chess.square_name(rook_square)
            bad.append(f"{label} ({reason})")
    return "castling " + ", ".join(bad) + " impossible"


def check_fen(fen: str, diagram: bool = False) -> dict:
    """Problems of a FEN. `ok` = playable position. Diagrams may be illegal: their problems are warnings."""
    fen = " ".join(fen.strip().split())
    try:
        board = chess.Board(fen)
    except ValueError as e:
        return {"ok": False, "readable": False, "fen": fen, "problems": [{"message": str(e), "fix": None}]}
    problems = []
    status = board.status()
    castling = _castling_message(board)
    if castling:
        problems.append({"message": castling, "fix": "castling"})
    for flag, message, fix in STATUS_MESSAGES:
        if status & flag:
            problems.append({"message": message, "fix": fix})
    fixed = fix_fen(fen) if any(p["fix"] for p in problems) else None
    return {
        "ok": not problems,
        "readable": True,
        "diagram": diagram,
        "fen": board.fen(),
        "fixed": fixed,
        "canonical": canonical_fen(board) if not problems else None,
        "turn": "w" if board.turn else "b",
        "problems": problems,
    }


def fix_fen(fen: str) -> str:
    """Apply every automatic fix: impossible castling rights, impossible en passant, the side to move in check."""
    board = chess.Board(fen)
    board.castling_rights = board.clean_castling_rights()
    if board.ep_square and not board.has_legal_en_passant():
        board.ep_square = None
    if board.status() & chess.STATUS_OPPOSITE_CHECK:
        board.turn = not board.turn
        if board.status() & chess.STATUS_OPPOSITE_CHECK:
            board.turn = not board.turn  # both kings in check: leave it
    return board.fen()


def canonical_fen(board: chess.Board | str) -> str:
    if isinstance(board, str):
        board = chess.Board(board)
    return " ".join(board.fen(en_passant="legal").split(" ")[:4])


# ── Paste detection ───────────────────────────────────────────────────────────────────────────────────────────────

FEN_RE = re.compile(r"^\s*([pnbrqkPNBRQK1-8]+/){7}[pnbrqkPNBRQK1-8]+(\s+[wb](\s+(-|[KQkqA-Ha-h]+)(\s+(-|[a-h][36])(\s+\d+\s+\d+)?)?)?)?\s*$")
LICHESS_FEN_PATH = re.compile(r"^/(?:analysis|editor)(?:/(?:standard|fromPosition))?/(.+)$")
LICHESS_GAME_PATH = re.compile(r"^/([A-Za-z0-9]{8})(?:[A-Za-z0-9]{4})?(?:/(?:white|black))?/?$")


def _complete_fen(text: str) -> str:
    """A placement alone (or placement + side) becomes a full FEN with white to move and no castling."""
    parts = text.split()
    defaults = ["w", "-", "-", "0", "1"]
    return " ".join(parts + defaults[len(parts) - 1:]) if len(parts) < 6 else " ".join(parts)


def _fen_result(fen: str, source: str) -> dict:
    check = check_fen(fen)
    return {"kind": "fen", "source": source, "fen": check["fen"], "check": check}


def parse_paste(text: str) -> dict:
    """What a pasted text is. kind: fen | fens | pgn | lichess-game | unknown."""
    text = (text or "").strip()
    if not text:
        return {"kind": "unknown", "message": "the clipboard is empty"}

    if re.match(r"^https?://", text) and "lichess.org" in text:
        url = urlparse(text.split()[0])
        path = unquote(url.path)
        m = LICHESS_FEN_PATH.match(path)
        if m:
            fen = _complete_fen(m.group(1).replace("_", " "))
            if FEN_RE.match(fen):
                return _fen_result(fen, "lichess link")
        if LICHESS_GAME_PATH.match(path):
            return {
                "kind": "lichess-game",
                "message": "a lichess game link: open the game on lichess, copy its PGN and paste that",
            }
        return {"kind": "unknown", "message": "a lichess link without a position"}

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) == 1 and FEN_RE.match(_complete_fen(lines[0])):
        return _fen_result(_complete_fen(lines[0]), "FEN")
    if len(lines) > 1 and all(FEN_RE.match(_complete_fen(line)) for line in lines):
        fens = [check_fen(_complete_fen(line)) for line in lines]
        return {"kind": "fens", "fens": [f["fen"] for f in fens], "bad": sum(not f["ok"] for f in fens)}

    if "[" in text or re.search(r"\b1\.\s*[a-hKQRBNO]", text):
        return _parse_pgn(text)
    return {"kind": "unknown", "message": "not a FEN, PGN or lichess link"}


def _parse_pgn(text: str) -> dict:
    stream = io.StringIO(text)
    games = []
    while len(games) < 500:
        game = chess.pgn.read_game(stream)
        if game is None:
            break
        if not game.errors or list(game.mainline_moves()):
            games.append(game)
    if not games:
        return {"kind": "unknown", "message": "looks like PGN, but no game could be read"}
    first = games[0]
    board = first.board()
    start = board.fen()
    moves = []
    for move in first.mainline_moves():
        moves.append({"uci": move.uci(), "san": board.san(move)})
        board.push(move)
    headers = {k: v for k, v in first.headers.items() if v and v != "?"}
    return {
        "kind": "pgn",
        "games": len(games),
        "start": start,
        "moves": moves,
        "headers": headers,
        "title": _game_title(headers),
        "errors": [str(e) for e in first.errors][:3],
    }


def _game_title(headers: dict) -> str:
    white, black = headers.get("White"), headers.get("Black")
    if white or black:
        year = (headers.get("Date") or "")[:4].strip("?.")
        return f"{white or '?'} – {black or '?'}" + (f" {year}" if year else "")
    return headers.get("Event", "game")


# ── Static boards ─────────────────────────────────────────────────────────────────────────────────────────────────


PIECES_DIR = Path(__file__).resolve().parent / "static" / "pieces"
_SVG_ROOT = re.compile(r"<svg\b([^>]*)>(.*)</svg>", re.S)


@lru_cache(maxsize=256)
def _piece_symbol(piece_set: str, code: str) -> str:
    """A piece as a <symbol id="ps-<set>-<code>">, its internal ids prefixed so several pieces can share one SVG."""
    text = (PIECES_DIR / piece_set / f"{code}.svg").read_text()
    m = _SVG_ROOT.search(text)
    attrs, inner = m.group(1), m.group(2)
    view_box = re.search(r'viewBox="([^"]+)"', attrs)
    if view_box:
        box = view_box.group(1)
    else:
        width = re.search(r'width="([\d.]+)', attrs)
        height = re.search(r'height="([\d.]+)', attrs)
        box = f"0 0 {width.group(1) if width else 45} {height.group(1) if height else 45}"
    prefix = f"ps-{piece_set}-{code}-"
    inner = re.sub(r'\bid="([^"]+)"', lambda i: f'id="{prefix}{i.group(1)}"', inner)
    inner = re.sub(r"url\(#([^)]+)\)", lambda r: f"url(#{prefix}{r.group(1)})", inner)
    inner = re.sub(r'href="#([^"]+)"', lambda r: f'href="#{prefix}{r.group(1)}"', inner)
    return f'<symbol id="ps-{piece_set}-{code}" viewBox="{box}">{inner}</symbol>'


def board_svg(
    fen: str, size: int = 160, flipped: bool = False, light: str = "#f0d9b5", dark: str = "#b58863", pieces: str = "cburnett",
) -> str:
    """A static board as SVG, for MiniBoard and Diagram, in the user's piece set. Illegal positions (diagrams) are
    drawn as they are. Each piece kind is defined once (<symbol>) and placed with <use>."""
    placement = fen.split()[0] if fen.strip() else START_FEN.split()[0]
    board = chess.BaseBoard(placement)
    if not (PIECES_DIR / pieces).is_dir():
        pieces = "cburnett"
    squares, uses, codes = [], [], set()
    for square in chess.SQUARES:
        file, rank = chess.square_file(square), chess.square_rank(square)
        x, y = (7 - file, rank) if flipped else (file, 7 - rank)
        if (file + rank) % 2 == 0:
            squares.append(f'<rect x="{x * 100}" y="{y * 100}" width="100" height="100"/>')
        piece = board.piece_at(square)
        if piece:
            code = ("w" if piece.color else "b") + piece.symbol().upper()
            codes.add(code)
            uses.append(f'<use href="#ps-{pieces}-{code}" x="{x * 100}" y="{y * 100}" width="100" height="100"/>')
    symbols = "".join(_piece_symbol(pieces, c) for c in sorted(codes))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 800 800" '
        f'width="{size}" height="{size}"><defs>{symbols}</defs>'
        f'<rect width="800" height="800" fill="{light}"/><g fill="{dark}">{"".join(squares)}</g>{"".join(uses)}</svg>'
    )


def valid_placement(fen: str) -> bool:
    try:
        chess.BaseBoard((fen or "").split()[0])
    except (ValueError, IndexError):
        return False
    return True
