"""Tag detection with python-chess (spec 11 · Tags).

`detect(position)` looks at the position and at the main line of its analysis and returns findings
(tag key, evidence, apply): applied findings become tags with origin "auto", the rest are suggestions (shown dashed
until accepted). `move_findings(node)` finds the motifs of one move (move tags). `store` saves findings and respects
the user's own decisions: a tag the user removed is never added again (TagDismissal), a manual tag is never touched,
and detection only withdraws the tags it set itself.

What is detected
- Phase (material and development), endgame type (material), elementary mates (K+Q/R/BB/BN vs K).
- Objective: "mate in N" when the main line ends in mate by the side to move; otherwise a mate-in-1/2 search.
- Mating patterns, by the geometry of the final mate position (back rank, smothered, Arabian, Anastasia, …).
- Tactical motifs along the solution: double / discovered check, forks, pins, skewers and discovered attacks
  (confirmed by a later capture), sacrifices, (under-)promotion, en passant, perpetual check, stalemate, and as
  suggestions quiet moves, decoys, deflections, removal of the guard, clearance, king hunts.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import chess
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}
PHASE = {chess.KNIGHT: 1, chess.BISHOP: 1, chess.ROOK: 2, chess.QUEEN: 4}
NAMES = {chess.PAWN: gettext_noop("pawn"), chess.KNIGHT: gettext_noop("knight"), chess.BISHOP: gettext_noop("bishop"), chess.ROOK: gettext_noop("rook"), chess.QUEEN: gettext_noop("queen"), chess.KING: gettext_noop("king")}
MAX_PLIES = 24  # longer main lines are game continuations, not puzzle solutions
MOTIF_PLIES = 12  # motifs are looked for in the first moves only
SEARCH_SECONDS = 1.5
DETECTOR = "pychess"


@dataclass
class Finding:
    tag: str
    evidence: str
    apply: bool


def label(board: chess.Board, move: chess.Move) -> str:
    """'22.Bf5+' / '22…Bf5+' for evidence texts."""
    number = board.fullmove_number
    return f"{number}{'.' if board.turn == chess.WHITE else '…'}{board.san(move)}"


def material(board, color) -> int:
    return sum(VALUE[p.piece_type] for p in board.piece_map().values() if p.color == color and p.piece_type != chess.KING)


def balance(board, color) -> int:
    return material(board, color) - material(board, not color)


def pieces(board, color) -> list[int]:
    """Non-pawn, non-king piece types of one side, strongest first."""
    return sorted((p.piece_type for p in board.piece_map().values() if p.color == color and p.piece_type not in (chess.PAWN, chess.KING)),
                  reverse=True)


def material_key(board) -> str:
    def side(color):
        return "".join(sym * len(board.pieces(chess.PIECE_SYMBOLS.index(sym.lower()), color)) for sym in "KQRBNP")
    return f"{side(chess.WHITE)}v{side(chess.BLACK)}"


# ── Static features ───────────────────────────────────────────────────────────────────────────────────────────


def phase(board) -> tuple[str, str]:
    score = sum(PHASE.get(p.piece_type, 0) for p in board.piece_map().values())
    white, black = pieces(board, chess.WHITE), pieces(board, chess.BLACK)
    pawns = len(board.pieces(chess.PAWN, chess.WHITE)) + len(board.pieces(chess.PAWN, chess.BLACK))
    desc = f"Material {material_key(board)}"
    if (len(white) <= 2 and len(black) <= 2 and score <= 12) or score <= 8:
        return "endgame", desc
    home_minors = sum(1 for sq, kind in ((chess.B1, chess.KNIGHT), (chess.G1, chess.KNIGHT), (chess.C1, chess.BISHOP), (chess.F1, chess.BISHOP),
                                         (chess.B8, chess.KNIGHT), (chess.G8, chess.KNIGHT), (chess.C8, chess.BISHOP), (chess.F8, chess.BISHOP))
                      if board.piece_type_at(sq) == kind)
    if score >= 22 and pawns >= 14 and (1 < board.fullmove_number <= 10 or home_minors >= 3):
        return "opening", desc + _(", {home_minors} minor pieces still at home").format(home_minors=home_minors)
    return "middlegame", desc


def endgame_type(board) -> str | None:
    w, b = pieces(board, chess.WHITE), pieces(board, chess.BLACK)
    wp, bp = len(board.pieces(chess.PAWN, chess.WHITE)), len(board.pieces(chess.PAWN, chess.BLACK))
    a, z = (w, b) if len(w) >= len(b) else (b, w)
    zp = bp if a is w else wp
    if not a and not z:
        return "pawn-endgame" if wp + bp else None
    if not z:
        if not zp:
            return None  # mating material against a bare king: see basic_mate
        return {chess.ROOK: "rook-vs-pawns", chess.QUEEN: "queen-vs-pawns", chess.BISHOP: "minor-vs-pawns",
                chess.KNIGHT: "minor-vs-pawns"}.get(a[0], "other-endgame") if len(a) == 1 else "other-endgame"
    pair = (tuple(a), tuple(z))
    R, B, N, Q = chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.QUEEN
    if pair == ((R,), (R,)):
        return "rook-pawn-vs-rook" if wp + bp == 1 else "rook-endgame"
    if pair == ((R, R), (R, R)):
        return "double-rook-endgame"
    if pair == ((B,), (B,)):
        colors = {(chess.square_file(sq) + chess.square_rank(sq)) % 2 for sq in board.pieces(B, chess.WHITE) | board.pieces(B, chess.BLACK)}
        return "bishop-endgame" if len(colors) == 1 else "opposite-bishop-endgame"
    if pair == ((N,), (N,)):
        return "knight-endgame"
    if sorted(pair) == sorted(((B,), (N,))):
        return "bishop-vs-knight"
    if len(a) == 1 and len(z) == 1 and R in (a[0], z[0]) and {a[0], z[0]} - {R} <= {B, N} and a[0] != z[0]:
        return "rook-vs-minor"
    if len(a) == 2 and len(z) == 2 and a[0] == R and z[0] == R and a[1] in (B, N) and z[1] in (B, N):
        return "rook-minor-endgame"
    if pair == ((Q,), (Q,)):
        return "queen-endgame"
    if sorted(pair) == sorted(((Q,), (R,))):
        return "queen-vs-rook"
    if Q in a and Q in z and all(t in (Q, R) for t in a + z) or (a == [Q] and z == [R, R]) or (z == [Q] and a == [R, R]):
        return "heavy-piece-endgame"
    return "other-endgame"


def basic_mate(board) -> str | None:
    if board.pieces(chess.PAWN, chess.WHITE) or board.pieces(chess.PAWN, chess.BLACK):
        return None
    w, b = pieces(board, chess.WHITE), pieces(board, chess.BLACK)
    strong = w if not b else b if not w else None
    if strong is None:
        return None
    color = chess.WHITE if strong is w else chess.BLACK
    if strong == [chess.QUEEN]:
        return "mate-queen"
    if strong == [chess.ROOK]:
        return "mate-rook"
    if strong == [chess.BISHOP, chess.BISHOP]:
        squares = list(board.pieces(chess.BISHOP, color))
        if (chess.square_file(squares[0]) + chess.square_rank(squares[0])) % 2 != (chess.square_file(squares[1]) + chess.square_rank(squares[1])) % 2:
            return "mate-two-bishops"
    if strong == [chess.BISHOP, chess.KNIGHT]:
        return "mate-bishop-knight"
    return None


# ── Mate search (when there is no solution yet) ───────────────────────────────────────────────────────────────


def mates_in_one(board) -> list[chess.Move]:
    found = []
    for move in board.legal_moves:
        if board.gives_check(move):
            board.push(move)
            if board.is_checkmate():
                found.append(move)
            board.pop()
    return found


def mate_in_two(board, deadline) -> chess.Move | None:
    """First move of a forced mate in 2, or None (also when the time budget runs out)."""
    ordered = sorted(board.legal_moves, key=lambda m: (not board.gives_check(m), not board.is_capture(m)))
    for move in ordered:
        if time.monotonic() > deadline:
            return None
        board.push(move)
        replies = list(board.legal_moves)
        ok = bool(replies) and not board.is_checkmate()
        for reply in replies:
            board.push(reply)
            mated = bool(mates_in_one(board))
            board.pop()
            if not mated:
                ok = False
                break
        board.pop()
        if ok:
            return move
    return None


# ── Mating patterns ───────────────────────────────────────────────────────────────────────────────────────────


def _behind_cover(board, color, square, mated_king):
    """Attackers of `square` with the mated king lifted off the board (x-ray along the check line)."""
    b = board.copy(stack=False)
    b.remove_piece_at(mated_king)
    return b.attackers(color, square)


def _behind_cover_from(board, piece_square, target, mated_king) -> bool:
    b = board.copy(stack=False)
    b.remove_piece_at(mated_king)
    return target in b.attacks(piece_square)


def _adjacent(a, b) -> bool:
    return a != b and chess.square_distance(a, b) == 1


def _defended_by(board, color, square, piece_type) -> bool:
    return any(board.piece_type_at(sq) == piece_type for sq in board.attackers(color, square))


SUPPRESSES = {
    "scholars-mate": {"max-lange-mate", "kiss-of-death", "damiano-mate", "lolli-mate", "triangle-mate"},
    "legal-mate": {"corner-mate"},
    "arabian-mate": {"corner-mate", "kill-box-mate"},
    "anastasia-mate": {"greco-mate"},
    "boden-mate": {"double-bishop-mate"},
    "mayet-mate": {"opera-mate", "back-rank-mate"},
    "opera-mate": {"back-rank-mate"},
    "pillsbury-mate": {"back-rank-mate"},
    "blind-swine-mate": {"ladder-mate"},
    "smothered-mate": {"corner-mate"},
}


def mate_patterns(board) -> list[str]:  # noqa: C901 (a catalogue of patterns, kept in one place)
    """Named mating patterns of a checkmate position (the side to move is mated)."""
    if not board.is_checkmate():
        return []
    mated, att = board.turn, not board.turn
    k = board.king(mated)
    kf, kr = chess.square_file(k), chess.square_rank(k)
    back = 0 if mated == chess.WHITE else 7
    second = 1 if mated == chess.WHITE else 6
    checkers = list(board.checkers())
    neighbours = list(chess.SquareSet(chess.BB_KING_ATTACKS[k]))
    own = [sq for sq in neighbours if board.color_at(sq) == mated]
    free = [sq for sq in neighbours if board.color_at(sq) != mated]
    corner = (kf in (0, 7)) and (kr in (0, 7))
    edge_file, edge_rank = kf in (0, 7), kr in (0, 7)
    cover = {sq: _behind_cover(board, att, sq, k) for sq in free}
    participants = set(checkers)
    for squares in cover.values():
        participants |= set(squares)
    ptypes = sorted(board.piece_type_at(sq) for sq in participants)
    out = []
    if len(checkers) != 1:
        return out
    c = checkers[0]
    ct = board.piece_type_at(c)
    cf, cr = chess.square_file(c), chess.square_rank(c)
    adjacent = _adjacent(c, k)
    orth = cf == kf or cr == kr
    diag = not orth

    if ct == chess.KNIGHT and len(own) == len(neighbours):
        out.append("smothered-mate")
    if ct == chess.PAWN:
        out.append("david-goliath-mate")
    if ct == chess.QUEEN and adjacent:
        if _defended_by(board, att, c, chess.KING):
            out.append("kiss-of-death")
        if _defended_by(board, att, c, chess.PAWN) and kr == back:
            out.append("damiano-mate" if diag else "lolli-mate")
        if orth:
            dx, dy = kf - cf, kr - cr
            behind = [chess.square(kf + dx + dy, kr + dy + dx) if 0 <= kf + dx + dy < 8 and 0 <= kr + dy + dx < 8 else None,
                      chess.square(kf + dx - dy, kr + dy - dx) if 0 <= kf + dx - dy < 8 and 0 <= kr + dy - dx < 8 else None]
            if all(sq is not None and board.color_at(sq) == mated for sq in behind):
                out.append("swallows-tail-mate")
        else:
            uncovered = [sq for sq in neighbours if sq != c and not _behind_cover_from(board, c, sq, k)]
            if len(uncovered) == 2 and all(board.color_at(sq) == mated for sq in uncovered):
                out.append("dovetail-mate")
        if not _defended_by(board, att, c, chess.PAWN) and not _defended_by(board, att, c, chess.KING):
            if any(board.piece_type_at(sq) == chess.BISHOP and not _adjacent(sq, c) for sq in board.attackers(att, c)):
                out.append("max-lange-mate")
            elif _defended_by(board, att, c, chess.ROOK):
                out.append("triangle-mate")
    if ct in (chess.ROOK, chess.QUEEN) and orth and not adjacent:
        dx, dy = (kf > cf) - (kf < cf), (kr > cr) - (kr < cr)
        lateral = [(kf + dy, kr + dx), (kf - dy, kr - dx)]
        lat_sq = [chess.square(f, r) for f, r in lateral if 0 <= f < 8 and 0 <= r < 8]
        if len(lat_sq) == 2 and all(board.color_at(sq) == mated for sq in lat_sq) and (edge_file or edge_rank):
            out.append("epaulette-mate")
    if ct in (chess.ROOK, chess.QUEEN) and kr == back and cr == back:
        forward = [sq for sq in neighbours if chess.square_rank(sq) == second]
        if forward and sum(1 for sq in forward if board.color_at(sq) == mated) >= 2 \
                and all(board.color_at(sq) == mated or cover.get(sq) for sq in forward):
            out.append("back-rank-mate")
    if ct == chess.ROOK and adjacent and orth:
        knights = [sq for sq in board.attackers(att, c) if board.piece_type_at(sq) == chess.KNIGHT]
        if corner and knights:
            out.append("arabian-mate")
        elif knights and any(_defended_by(board, att, n, chess.PAWN) for n in knights):
            out.append("hook-mate")
        if _defended_by(board, att, c, chess.QUEEN):
            out.append("kill-box-mate")
        if _defended_by(board, att, c, chess.KING) and chess.KNIGHT in ptypes and (edge_file or edge_rank):
            out.append("vukovic-mate")
        bishops = [sq for sq in board.attackers(att, c) if board.piece_type_at(sq) == chess.BISHOP and not _adjacent(sq, c)]
        if bishops and kr == back:
            long_diag = any(chess.square_file(b) - chess.square_rank(b) == 0 or chess.square_file(b) + chess.square_rank(b) == 7 for b in bishops)
            out.append("mayet-mate" if long_diag and c in (chess.A1, chess.H1, chess.A8, chess.H8) else "opera-mate")
    if ct in (chess.ROOK, chess.QUEEN) and edge_file and cf == kf and not adjacent:
        side = [sq for sq in neighbours if chess.square_file(sq) != kf]
        if any(board.color_at(sq) == mated for sq in side):
            if any(board.piece_type_at(a) == chess.KNIGHT for sq in side for a in cover.get(sq, [])):
                out.append("anastasia-mate")
            elif any(board.piece_type_at(a) == chess.BISHOP for sq in side for a in cover.get(sq, [])):
                out.append("greco-mate")
    if ct == chess.KNIGHT and corner and any(board.piece_type_at(a) in (chess.ROOK, chess.QUEEN) for a in participants if a != c):
        out.append("corner-mate")
    if ct == chess.BISHOP:
        bishops = [sq for sq in participants if board.piece_type_at(sq) == chess.BISHOP]
        others = [sq for sq in participants if board.piece_type_at(sq) not in (chess.BISHOP,)]
        if len(bishops) == 2 and not others:
            other = bishops[0] if bishops[1] == c else bishops[1]
            check_dir = ((kf > cf) - (kf < cf)) * ((kr > cr) - (kr < cr))
            covered = [sq for sq in free if other in cover[sq]]
            other_dirs = {((chess.square_file(sq) > chess.square_file(other)) - (chess.square_file(sq) < chess.square_file(other)))
                          * ((chess.square_rank(sq) > chess.square_rank(other)) - (chess.square_rank(sq) < chess.square_rank(other))) for sq in covered}
            out.append("boden-mate" if other_dirs and check_dir not in other_dirs else "double-bishop-mate")
        if corner and any(board.piece_type_at(a) == chess.ROOK for a in participants):
            out.append("morphy-mate")
        if not adjacent and chess.QUEEN in ptypes and set(ptypes) <= {chess.BISHOP, chess.QUEEN}:
            out.append("balestra-mate")
    if ct in (chess.BISHOP, chess.KNIGHT) and ptypes.count(chess.BISHOP) == 2 and chess.KNIGHT in ptypes \
            and not set(ptypes) & {chess.QUEEN, chess.ROOK}:
        out.append("blackburne-mate")
    if ct == chess.ROOK and cf == kf and kr == back and kf in (1, 6):
        corner_sq = chess.square(0 if kf == 1 else 7, back)
        if any(board.piece_type_at(a) == chess.BISHOP for a in board.attackers(att, corner_sq)):
            out.append("pillsbury-mate")
    rooks = [sq for sq in board.pieces(chess.ROOK, att) if chess.square_rank(sq) == second]
    if len(rooks) >= 2 and c in rooks:
        out.append("blind-swine-mate")
    heavy = [sq for sq in participants if board.piece_type_at(sq) in (chess.ROOK, chess.QUEEN)]
    if ct in (chess.ROOK, chess.QUEEN) and not own and (edge_rank or edge_file) and len(heavy) >= 2 and not adjacent \
            and set(ptypes) <= {chess.ROOK, chess.QUEEN, chess.KING}:
        out.append("ladder-mate")
    if ct == chess.QUEEN and adjacent and k in (chess.E8, chess.E1) and c in (chess.F7, chess.F2) and _defended_by(board, att, c, chess.BISHOP) \
            and board.fullmove_number <= 8:
        out.append("scholars-mate")
    if ct == chess.QUEEN and k in (chess.E1, chess.E8) and c in (chess.H4, chess.H5) and board.fullmove_number <= 3:
        out.append("fools-mate")
    if ct == chess.KNIGHT and board.fullmove_number <= 10 and any(
            board.piece_type_at(sq) == chess.BISHOP and _adjacent(sq, k) for sq in participants):
        out.append("legal-mate")
    if not own and not out:
        out.append("mirror-mate")
    hidden = set()
    for key in out:
        hidden |= SUPPRESSES.get(key, set())
    return [x for x in dict.fromkeys(out) if x not in hidden]


# ── The solution ──────────────────────────────────────────────────────────────────────────────────────────────


def _slider_rays(board, square):
    """For a slider on `square`: lists of the first two pieces seen along each ray."""
    piece = board.piece_at(square)
    dirs = []
    if piece.piece_type in (chess.BISHOP, chess.QUEEN):
        dirs += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    if piece.piece_type in (chess.ROOK, chess.QUEEN):
        dirs += [(1, 0), (-1, 0), (0, 1), (0, -1)]
    f0, r0 = chess.square_file(square), chess.square_rank(square)
    for df, dr in dirs:
        seen, f, r = [], f0 + df, r0 + dr
        while 0 <= f < 8 and 0 <= r < 8 and len(seen) < 2:
            sq = chess.square(f, r)
            if board.piece_at(sq):
                seen.append(sq)
            f, r = f + df, r + dr
        yield seen


def _later_captures(boards, moves, start, plies=4) -> dict:
    """Squares captured on by the mover in the next `plies` half-moves after index `start`."""
    out = {}
    for j in range(start + 2, min(len(moves), start + 1 + plies), 2):
        if boards[j].is_capture(moves[j]):
            out[moves[j].to_square] = j
    return out


def solution_features(board, moves, first_only=False) -> list[Finding]:  # noqa: C901
    """Motifs and objective from a main line. `board` is the start, `moves` the line. `first_only`: the motifs of the
    first move only (the rest of the line confirms them): move tags."""
    out = []
    mover = board.turn
    boards, b = [], board.copy(stack=False)
    for m in moves:
        boards.append(b.copy())
        b.push(m)
    final = b
    start_balance = balance(board, mover)

    if first_only:
        pass
    elif len(moves) <= MAX_PLIES and final.is_checkmate() and len(moves) % 2 == 1:
        n = (len(moves) + 1) // 2
        last = label(boards[-1], moves[-1])
        out.append(Finding({1: "mate-in-1", 2: "mate-in-2", 3: "mate-in-3"}.get(n, "mate-in-4-plus"), _("The solution ends with {last}").format(last=last), True))
        for key in mate_patterns(final):
            out.append(Finding(key, _("Mating pattern after {last}").format(last=last), True))
    elif final.is_stalemate() and len(moves) <= MAX_PLIES:
        out.append(Finding("stalemate-trick", _("The solution ends in stalemate after {value}").format(value=label(boards[-1], moves[-1])), True))
    elif len(moves) <= MAX_PLIES and len(moves) >= 4 and final.is_repetition(2) and all(boards[i].gives_check(moves[i]) for i in range(0, len(moves), 2)):
        out.append(Finding("perpetual-check", _('Checks until the position repeats'), True))
    elif len(moves) <= MAX_PLIES and balance(final, mover) >= start_balance + 3:
        out.append(Finding("win-material", _("Wins material by {value}").format(value=label(boards[-1], moves[-1])), False))

    checks_given, discovered = 0, 0
    lowest, lowest_at = start_balance, None
    queen_lost_at = None
    for i, m in enumerate(moves[:1 if first_only else MOTIF_PLIES]):
        before = boards[i]
        after = boards[i + 1] if i + 1 < len(boards) else final
        if i % 2 == 1:  # the opponent's reply: material bookkeeping only
            bal = balance(after, mover)
            if bal < lowest:
                lowest, lowest_at = bal, i
            if before.is_capture(m) and before.piece_type_at(m.to_square) == chess.QUEEN and before.color_at(m.to_square) == mover:
                queen_lost_at = queen_lost_at if queen_lost_at is not None else i
            continue
        text = label(before, m)
        piece = before.piece_at(m.from_square)
        checkers = after.checkers()
        if checkers:
            checks_given += 1
        if len(checkers) >= 2:
            out.append(Finding("double-check", _("Double check with {text}").format(text=text), True))
        elif checkers and m.to_square not in checkers:
            out.append(Finding("discovered-check", _("Discovered check with {text}").format(text=text), True))
            discovered += 1
        if m.promotion:
            out.append(Finding("promotion" if m.promotion == chess.QUEEN else "underpromotion", f"Promotion {text}", True))
        if before.is_en_passant(m):
            out.append(Finding("en-passant", _("En passant {text}").format(text=text), True))
        if i == 0 and piece.piece_type == chess.BISHOP and before.is_capture(m) and checkers \
                and m.to_square in (chess.H7, chess.H2, chess.A7, chess.A2) and before.piece_type_at(m.to_square) == chess.PAWN:
            out.append(Finding("greek-gift", _("Bishop sacrifice {text}").format(text=text), True))
        later = _later_captures(boards + [final], moves, i)

        mover_piece = after.piece_at(m.to_square)
        if mover_piece:
            # fork: the moved piece attacks two valuable targets; confirmed when one of them is taken later
            targets = [sq for sq in after.attacks(m.to_square)
                       if after.color_at(sq) == (not mover)
                       and (after.piece_type_at(sq) == chess.KING or VALUE[after.piece_type_at(sq)] > VALUE[mover_piece.piece_type]
                            or not after.is_attacked_by(not mover, sq))
                       and after.piece_type_at(sq) != chess.PAWN]
            if len(targets) >= 2 and any(t in later for t in targets):
                kinds = {after.piece_type_at(t) for t in targets}
                key = {chess.KNIGHT: "knight-fork", chess.PAWN: "pawn-fork", chess.QUEEN: "queen-fork"}.get(mover_piece.piece_type, "fork")
                if key == "knight-fork" and {chess.KING, chess.QUEEN} <= kinds:
                    key = "family-fork"
                out.append(Finding(key, _("Fork with {text}").format(text=text), True))
            # pins and skewers made by the moved slider
            if mover_piece.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN):
                for ray in _slider_rays(after, m.to_square):
                    if len(ray) < 2 or after.color_at(ray[0]) == mover or after.color_at(ray[1]) == mover:
                        continue
                    front, back = after.piece_type_at(ray[0]), after.piece_type_at(ray[1])
                    if back == chess.KING and front != chess.KING:
                        out.append(Finding("absolute-pin", _("{text} pins the {value} on {value2}").format(text=text, value=_(NAMES[front]), value2=chess.square_name(ray[0])), ray[0] in later))
                    elif front != chess.KING and VALUE[back] > VALUE[front] and back != chess.PAWN and ray[0] in later:
                        out.append(Finding("relative-pin", _("{text} pins to {value}").format(text=text, value=chess.square_name(ray[1])), False))
                    elif (front == chess.KING or VALUE[front] > VALUE[back]) and back != chess.PAWN and ray[1] in later:
                        out.append(Finding("skewer", _("Skewer with {text}").format(text=text), True))
        # discovered attack (no check): another slider now attacks something valuable, taken later
        if not checkers:
            for sq in before.pieces(chess.BISHOP, mover) | before.pieces(chess.ROOK, mover) | before.pieces(chess.QUEEN, mover):
                if sq == m.from_square or after.piece_at(sq) is None:
                    continue
                for t in after.attacks(sq) & ~before.attacks(sq):
                    if after.color_at(t) == (not mover) and after.piece_type_at(t) not in (chess.PAWN, chess.KING) \
                            and later.get(t) is not None and moves[later[t]].from_square == sq:
                        out.append(Finding("discovered-attack", _("Discovered attack with {text}").format(text=text), True))
        if i == 0 and before.is_capture(m) and not before.is_en_passant(m):
            victim = before.piece_type_at(m.to_square)
            if victim and VALUE[victim] >= 3 and not before.is_attacked_by(not mover, m.to_square):
                out.append(Finding("hanging-piece", _("{text} takes an undefended piece").format(text=text), False))
        if i == 0 and not checkers and not before.is_capture(m) and not m.promotion and len(moves) >= 3 \
                and (final.is_checkmate() or balance(final, mover) >= start_balance + 3):
            out.append(Finding("quiet-move", _("{text}: no check, no capture").format(text=text), False))
        if i + 1 < len(moves):
            reply, rb = moves[i + 1], boards[i + 1]
            if reply.to_square == m.to_square and rb.is_capture(reply):
                if rb.piece_type_at(reply.from_square) == chess.KING and i + 2 < len(moves) and boards[i + 2].gives_check(moves[i + 2]):
                    out.append(Finding("decoy", _("{text} lures the king to {value}").format(text=text, value=chess.square_name(m.to_square)), False))
            if i + 2 < len(moves):
                nxt = moves[i + 2]
                guard_before = rb.attacks(reply.from_square)
                after_reply = boards[i + 2]
                if nxt.to_square in guard_before and nxt.to_square not in after_reply.attacks(reply.to_square) \
                        and reply.to_square != m.to_square and rb.piece_type_at(reply.from_square) != chess.KING \
                        and (after_reply.is_capture(nxt) or after_reply.gives_check(nxt)):
                    out.append(Finding("deflection", _("{text} deflects the defender").format(text=text), False))
                if before.is_capture(m) and before.piece_type_at(m.to_square) not in (chess.PAWN, None):
                    if nxt.to_square in before.attacks(m.to_square) and nxt.to_square != m.to_square \
                            and (after_reply.is_capture(nxt) or after_reply.gives_check(nxt)):
                        out.append(Finding("removal-of-guard", _("{text} removes the defender").format(text=text), False))
                if nxt.from_square != m.to_square:
                    path = chess.SquareSet(chess.between(nxt.from_square, nxt.to_square))
                    if nxt.to_square == m.from_square:
                        out.append(Finding("square-clearance", f"{text} clears {chess.square_name(m.from_square)}", False))
                    elif m.from_square in path:
                        out.append(Finding("line-clearance", _("{text} clears the line").format(text=text), False))

    if first_only:
        return out
    if discovered >= 2:
        out.append(Finding("windmill", _('Discovered checks one after the other'), False))
    if lowest_at is not None and lowest <= start_balance - 2 and (final.is_checkmate() or balance(final, mover) >= start_balance - 1):
        if queen_lost_at is not None:
            out.append(Finding("queen-sacrifice", _("Queen sacrifice (after {value})").format(value=label(boards[queen_lost_at], moves[queen_lost_at])), True))
        else:
            out.append(Finding("sacrifice", _("Sacrifice: down {value} points on the way").format(value=start_balance - lowest), True))
    king_start = board.king(not mover)
    king_moves = sum(1 for i in range(1, min(len(moves), MAX_PLIES), 2) if boards[i].piece_type_at(moves[i].from_square) == chess.KING)
    if checks_given >= 4 and king_moves >= 4 and king_start is not None and final.king(not mover) is not None \
            and chess.square_distance(king_start, final.king(not mover)) >= 3:
        out.append(Finding("king-hunt", _("{checks_given} checks, the king walks {value}–{value2}").format(checks_given=checks_given, value=chess.square_name(king_start), value2=chess.square_name(final.king(not mover))), False))
    return out


# ── Positions and moves ───────────────────────────────────────────────────────────────────────────────────────


def mainline(position) -> list[chess.Move]:
    """The legal main line of the position's analysis."""
    from spaced_positions.analysis import tree

    kids = tree.kids_map(tree.nodes(position))
    root = tree.root(position)
    board, out, node = chess.Board(position.fen), [], root
    while kids.get(node.id):
        node = kids[node.id][0]
        try:
            move = chess.Move.from_uci(node.uci)
        except ValueError:
            break
        if move not in board.legal_moves:
            break
        out.append(move)
        board.push(move)
    return out


def detect(position, search: bool = True) -> list[Finding]:
    """All findings for a position (the first finding of a tag wins; an applied one beats a suggestion)."""
    if position.diagram:
        return []
    try:
        board = chess.Board(position.fen)
    except ValueError:
        return []
    if not board.is_valid():
        return []
    from .structure import static_features

    found = []
    ph, desc = phase(board)
    found.append(Finding(ph, desc, True))
    found += static_features(board, ph)  # structure: suggestions (the wrong rook pawn is applied)
    if ph == "endgame":
        kind = endgame_type(board)
        if kind:
            found.append(Finding(kind, f"Material {material_key(board)}", True))
        mate = basic_mate(board)
        if mate:
            found.append(Finding(mate, f"Material {material_key(board)}", True))
    moves = mainline(position)
    if moves:
        from .sequences import APPLIED, line_features

        found += solution_features(board, moves)
        found += [Finding(key, text, key in APPLIED) for _i, key, text in line_features(board, moves)]
    elif search and not board.is_game_over():  # no solution yet: a short mate?
        mates = mates_in_one(board)
        if mates:
            found.append(Finding("mate-in-1", "Found: " + ", ".join(label(board, m) for m in mates[:3]), True))
            if len(mates) == 1:
                b = board.copy(stack=False)
                b.push(mates[0])
                found += [Finding(key, _("Mating pattern after {value}").format(value=label(board, mates[0])), True) for key in mate_patterns(b)]
        else:
            first = mate_in_two(board.copy(), time.monotonic() + SEARCH_SECONDS)
            if first is not None:
                found.append(Finding("mate-in-2", f"Found: {label(board, first)}", True))
    merged: dict[str, Finding] = {}
    for f in found:
        old = merged.get(f.tag)
        if old is None or (f.apply and not old.apply):
            merged[f.tag] = f
    return list(merged.values())


def move_findings(node) -> list[Finding]:
    """The motifs of one move of an analysis, judged with the line that follows it; the mating pattern when the move
    mates; a sacrifice by this move when the line wins the material back or mates."""
    if node.parent_id is None:
        return []
    board = chess.Board(node.parent.fen)
    line, cur = [chess.Move.from_uci(node.uci)], node
    while len(line) < MOTIF_PLIES:
        kid = cur.kids.order_by("order", "id").first()
        if kid is None:
            break
        line.append(chess.Move.from_uci(kid.uci))
        cur = kid
    try:
        out = [f for f in solution_features(board, line, first_only=True) if f.tag != "quiet-move"]
    except (ValueError, AssertionError):
        return []
    after = board.copy(stack=False)
    after.push(line[0])
    if after.is_checkmate():
        out += [Finding(key, _("Mating pattern after {value}").format(value=label(board, line[0])), True) for key in mate_patterns(after)]
    if len(line) >= 3:
        mover, start = board.turn, balance(board, board.turn)
        b = board.copy(stack=False)
        b.push(line[0])
        moved = b.piece_type_at(line[0].to_square)
        reply_takes = b.is_capture(line[1]) and line[1].to_square == line[0].to_square
        b.push(line[1])
        if reply_takes and balance(b, mover) <= start - 2:
            for m in line[2:]:
                b.push(m)
            if b.is_checkmate() or balance(b, mover) >= start - 1:
                out.append(Finding("queen-sacrifice" if moved == chess.QUEEN else "sacrifice", _("{value} sacrifices material").format(value=label(board, line[0])), True))
    seen, unique = set(), []
    for f in out:
        if f.tag not in seen:
            seen.add(f.tag)
            unique.append(f)
    return unique


# ── Storing ───────────────────────────────────────────────────────────────────────────────────────────────────


def store(position, findings: list[Finding]) -> dict:
    """Save the findings of a position. Applied → tags with origin auto; the rest → suggestions. Dismissed tags and
    the user's own tags are left alone; detected tags that are no longer found are withdrawn (only those)."""
    from .models import PositionTag, Tag, TagDismissal

    tags = {t.key: t for t in Tag.objects.filter(key__in=[f.tag for f in findings]).select_related("field")}
    dismissed = set(TagDismissal.objects.filter(position=position, node=None).values_list("tag_id", flat=True))
    links = {link.tag_id: link for link in position.tag_links.select_related("tag__field")}
    added, suggested = [], []
    for f in findings:
        tag = tags.get(f.tag)
        if tag is None or not tag.field.on_positions or tag.pk in dismissed:
            continue
        link = links.get(tag.pk)
        if link is not None:
            if link.origin == PositionTag.Origin.MANUAL:
                continue
            origin = PositionTag.Origin.AUTO if f.apply else link.origin
            if (link.evidence, link.origin) != (f.evidence[:200], origin):
                link.evidence, link.origin, link.detector = f.evidence[:200], origin, DETECTOR
                link.save(update_fields=["evidence", "origin", "detector"])
            continue
        taken = tag.field.selection == "single" and any(
            l.tag.field_id == tag.field_id and l.origin != PositionTag.Origin.SUGGESTED for l in links.values())
        origin = PositionTag.Origin.AUTO if f.apply and not taken else PositionTag.Origin.SUGGESTED
        links[tag.pk] = PositionTag.objects.create(position=position, tag=tag, origin=origin, detector=DETECTOR, evidence=f.evidence[:200])
        (added if origin == PositionTag.Origin.AUTO else suggested).append(tag.label)
    found = {tags[f.tag].pk for f in findings if f.tag in tags}
    withdrawn = position.tag_links.filter(detector=DETECTOR).exclude(origin=PositionTag.Origin.MANUAL).exclude(tag_id__in=found)
    gone = [link.tag.label for link in withdrawn.select_related("tag")]
    withdrawn.delete()
    refresh_difficulty(position)
    return {"added": added, "suggested": suggested, "withdrawn": gone}


def store_moves(position) -> int:
    """Move tags of the main line's first moves (the solution's motifs), as auto tags; returns how many were added."""
    from spaced_positions.analysis import tree

    from .models import NodeTag, Tag, TagDismissal

    kids = tree.kids_map(tree.nodes(position))
    node, nodes = tree.root(position), []
    while kids.get(node.id) and len(nodes) < MOTIF_PLIES:
        node = kids[node.id][0]
        nodes.append(node)
    tags = {t.key: t for t in Tag.objects.filter(field__on_moves=True)}
    dismissed = set(TagDismissal.objects.filter(node__in=nodes).values_list("node_id", "tag_id"))
    added = 0
    for n in nodes:
        for f in move_findings(n):
            tag = tags.get(f.tag)
            if tag is None or not f.apply or (n.id, tag.pk) in dismissed:
                continue
            _, made = NodeTag.objects.get_or_create(node=n, tag=tag, defaults={"origin": "auto", "detector": DETECTOR, "evidence": f.evidence[:200]})
            added += made
    if added:
        refresh_difficulty(position)
    return added


def run(position, search: bool = True) -> dict:
    """Detect and store for one position (position tags and the solution's move tags)."""
    result = store(position, detect(position, search=search))
    result["moves"] = store_moves(position) if not position.diagram else 0
    return result


# ── Difficulty ────────────────────────────────────────────────────────────────────────────────────────────────

ANALYSIS_CAP = 1.0  # the most the analysis can add (difficulty steps)
TRUST = {"manual": 1.0, "auto": 0.8}


def auto_difficulty(position) -> int | None:
    """The weighted base difficulty of the position's tags, plus a capped bonus from
    the move tags of its analysis (each tag once; a move tag that repeats a position tag adds nothing)."""
    from .models import NodeTag

    links = [l for l in position.tag_links.select_related("tag") if l.origin != "suggested"]
    total = weights = 0.0
    on_position = set()
    for link in links:
        on_position.add(link.tag_id)
        if link.tag.weight > 0:
            total += link.tag.base_difficulty * link.tag.weight
            weights += link.tag.weight
    best = {}
    for link in NodeTag.objects.filter(node__position=position).exclude(origin="suggested").select_related("tag"):
        if link.tag_id in on_position:
            continue
        trust = TRUST.get(link.origin, 0.8)
        if link.tag_id not in best or trust > best[link.tag_id][1]:
            best[link.tag_id] = (link.tag, trust)
    a_total = ab_total = bonus = 0.0
    for tag, trust in best.values():
        a = max(0.0, tag.analysis_weight) * trust
        if a > 0:
            bonus += a * tag.base_difficulty / 5
            a_total += a
            ab_total += a * tag.base_difficulty
    if weights:
        raw = total / weights + min(ANALYSIS_CAP, bonus)
    elif a_total:
        raw = ab_total / a_total
    else:
        return None
    return max(1, min(5, int(raw + 0.5)))


def refresh_difficulty(position) -> None:
    value = auto_difficulty(position)
    if value != position.difficulty_auto:
        position.difficulty_auto = value
        position.save(update_fields=["difficulty_auto"])
