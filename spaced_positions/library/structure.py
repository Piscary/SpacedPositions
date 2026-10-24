"""Static features of a position (python-chess, no search), ported from chess-study-manager's `structure` detector:
pawn structure, rooks and files, batteries, material imbalances, king safety and threats, typical endgame set-ups.

Positional themes are *suggestions* (`apply = False`): the structure is a fact, whether it matters is a judgement.
A fact that decides the character of an endgame (the wrong rook pawn) is applied."""

from __future__ import annotations

import chess

from .detect import VALUE, Finding, mates_in_one, pieces

SIDE = {chess.WHITE: "White", chess.BLACK: "Black"}
FILES = "abcdefgh"
NAME = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop", chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king"}
LETTER = {chess.KNIGHT: "N", chess.BISHOP: "B", chess.ROOK: "R", chess.QUEEN: "Q", chess.KING: "K"}


def rel_rank(square, color) -> int:
    r = chess.square_rank(square)
    return r if color == chess.WHITE else 7 - r


def square_colour(square) -> int:
    return (chess.square_file(square) + chess.square_rank(square)) % 2


def pawn_files(board, color) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for sq in board.pieces(chess.PAWN, color):
        out.setdefault(chess.square_file(sq), []).append(sq)
    return out


def is_passed(board, square, color) -> bool:
    f = chess.square_file(square)
    return not any(abs(chess.square_file(sq) - f) <= 1 and rel_rank(sq, color) > rel_rank(square, color)
                   for sq in board.pieces(chess.PAWN, not color))


def passers(board, color) -> list[int]:
    return [sq for sq in board.pieces(chess.PAWN, color) if is_passed(board, sq, color)]


def islands(files) -> int:
    count, prev = 0, None
    for f in sorted(files):
        if prev is None or f != prev + 1:
            count += 1
        prev = f
    return count


def only_kings_and_pawns(board) -> bool:
    return not any(board.pieces(t, c) for t in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN) for c in chess.COLORS)


def pieces_value(board, color) -> int:
    return sum(VALUE[t] for t in pieces(board, color))


# ── Pawn structure ────────────────────────────────────────────────────────────────────────────────────────────


def pawn_structure(board, endgame: bool) -> list[Finding]:  # noqa: C901 (one catalogue, kept together)
    out = []
    for color in chess.COLORS:
        side = SIDE[color]
        files = pawn_files(board, color)
        enemy = pawn_files(board, not color)
        n = len(board.pieces(chess.PAWN, color))
        for f, sqs in files.items():
            if len(sqs) >= 2:
                out.append(Finding("doubled-pawns", f"Doubled pawns on the {FILES[f]}-file ({side})", False))
                break
        if 3 in files and 2 not in files and 4 not in files and len(pieces(board, color)) >= 3:
            out.append(Finding("isolated-pawn", f"Isolated queen's pawn ({side})", False))
        elif not endgame and n >= 4:
            iso = [f for f in files if f - 1 not in files and f + 1 not in files]
            if iso:
                out.append(Finding("isolated-pawn", f"Isolated pawn on the {FILES[iso[0]]}-file ({side})", False))
        if 2 in files and 3 in files and 1 not in files and 4 not in files:  # hanging pawns: c and d side by side, no b or e pawn
            c, d = files[2][0], files[3][0]
            if rel_rank(c, color) == rel_rank(d, color) >= 3 and len(files[2]) == len(files[3]) == 1:
                out.append(Finding("hanging-pawns", f"Hanging pawns {chess.square_name(c)}/{chess.square_name(d)} ({side})", False))
        if not endgame and n >= 4:  # backward: no neighbour pawn can support it, an enemy pawn hits its stop square
            for sq in board.pieces(chess.PAWN, color):
                f, r = chess.square_file(sq), rel_rank(sq, color)
                helpers = [s for ff in (f - 1, f + 1) for s in files.get(ff, []) if rel_rank(s, color) <= r]
                stop = sq + (8 if color == chess.WHITE else -8)
                if helpers or not 0 <= stop < 64 or f in enemy or not any(ff in files for ff in (f - 1, f + 1)):
                    continue
                if any(board.piece_type_at(a) == chess.PAWN for a in board.attackers(not color, stop)):
                    out.append(Finding("backward-pawn", f"Backward pawn {chess.square_name(sq)} ({side})", False))
                    break
        mine = passers(board, color)
        far = [sq for sq in mine if rel_rank(sq, color) >= 4]
        if far:
            out.append(Finding("passed-pawn", f"Passed pawn {chess.square_name(far[0])} ({side})", False))
        for sq in mine:
            if any(board.piece_type_at(a) == chess.PAWN for a in board.attackers(color, sq)):
                out.append(Finding("protected-passed-pawn", f"Protected passed pawn {chess.square_name(sq)} ({side})", False))
                break
        mine_files = sorted(chess.square_file(sq) for sq in mine)
        if any(b - a == 1 for a, b in zip(mine_files, mine_files[1:])):
            out.append(Finding("connected-passed-pawns", f"Connected passed pawns ({side})", False))
        if endgame and enemy:
            for sq in mine:
                f = chess.square_file(sq)
                if all(abs(f - ef) >= 3 for ef in enemy) and all(abs(f - of) >= 2 for of in files if of != f):
                    out.append(Finding("outside-passed-pawn", f"Outside passed pawn {chess.square_name(sq)} ({side})", False))
                    break
        if files and enemy and islands(files) >= 3 and islands(files) > islands(enemy):
            out.append(Finding("pawn-islands", f"{side}: {islands(files)} pawn islands, the opponent {islands(enemy)}", False))
        if endgame and n == len(board.pieces(chess.PAWN, not color)):
            for wing, rng in (("queenside", range(0, 3)), ("kingside", range(5, 8))):
                a = sum(len(files.get(f, [])) for f in rng)
                b = sum(len(enemy.get(f, [])) for f in rng)
                if a > b >= 0 and a >= 2:
                    out.append(Finding("pawn-majority", f"{side}: a pawn majority on the {wing} ({a} against {b})", False))
                    break
    return out


# ── Pieces: bishops, rooks, batteries, material ───────────────────────────────────────────────────────────────


def bishops_and_rooks(board, endgame: bool) -> list[Finding]:
    out = []
    for color in chess.COLORS:
        side = SIDE[color]
        bishops = list(board.pieces(chess.BISHOP, color))
        if len(bishops) == 2 and square_colour(bishops[0]) != square_colour(bishops[1]) and len(board.pieces(chess.BISHOP, not color)) < 2:
            out.append(Finding("bishop-pair", f"{side} has the bishop pair", False))
        rooks = list(board.pieces(chess.ROOK, color))
        own_files, enemy_files = pawn_files(board, color), pawn_files(board, not color)
        for sq in rooks:
            f = chess.square_file(sq)
            if endgame:
                pass  # in endings nearly every file is open: not a theme
            elif f not in own_files and f not in enemy_files:
                out.append(Finding("open-file", f"Rook {chess.square_name(sq)} on the open {FILES[f]}-file ({side})", False))
            elif f not in own_files:
                out.append(Finding("half-open-file", f"Rook {chess.square_name(sq)} on the half-open {FILES[f]}-file ({side})", False))
            if rel_rank(sq, color) == 6:
                king = board.king(not color)
                if (king is not None and rel_rank(king, color) == 7) or any(rel_rank(p, color) == 6 for p in board.pieces(chess.PAWN, not color)):
                    out.append(Finding("seventh-rank", f"Rook on the seventh rank: {chess.square_name(sq)} ({side})", False))
        if len(rooks) >= 2:
            a, b = rooks[:2]
            between = chess.SquareSet(chess.between(a, b))
            on_seventh = rel_rank(a, color) == rel_rank(b, color) == 6
            if (chess.square_file(a) == chess.square_file(b) or on_seventh) and not (between & board.occupied):
                line = f"{FILES[chess.square_file(a)]}-file" if chess.square_file(a) == chess.square_file(b) else "seventh rank"
                out.append(Finding("doubled-rooks", f"Rooks doubled on the {line} ({side})", False))
        out += batteries(board, color)
    return out


def batteries(board, color) -> list[Finding]:
    """Queen and bishop on a diagonal, or queen and rook on a file or rank, one behind the other, aimed at the
    squares around the enemy king."""
    king = board.king(not color)
    if king is None:
        return []
    zone = chess.SquareSet(chess.BB_KING_ATTACKS[king]) | chess.SquareSet.from_square(king)
    long_range = board.pieces(chess.QUEEN, color) | board.pieces(chess.BISHOP, color) | board.pieces(chess.ROOK, color)
    for front in long_range:
        for back in long_range:
            if front == back or not chess.SquareSet(chess.ray(front, back)):
                continue
            if chess.SquareSet(chess.between(front, back)) & board.occupied:
                continue
            diagonal = chess.square_file(front) != chess.square_file(back) and chess.square_rank(front) != chess.square_rank(back)
            kinds = {board.piece_type_at(front), board.piece_type_at(back)}
            if diagonal and kinds != {chess.QUEEN, chess.BISHOP}:
                continue
            if not diagonal and not kinds <= {chess.QUEEN, chess.ROOK}:
                continue
            if kinds == {chess.ROOK}:
                continue  # two rooks: doubled rooks
            beyond = [s for s in chess.SquareSet(chess.ray(back, front))
                      if chess.square_distance(s, back) > chess.square_distance(front, back) and chess.square_distance(s, front) < chess.square_distance(s, back)]
            hits = [s for s in beyond if s in zone and not (chess.SquareSet(chess.between(front, s)) & board.occupied)]
            if hits:
                names = " and ".join(NAME[board.piece_type_at(x)] for x in (back, front))
                return [Finding("battery", f"Battery of {names} against {chess.square_name(hits[0])} ({SIDE[color]})", False)]
    return []


def material_imbalance(board) -> list[Finding]:
    w, b = pieces(board, chess.WHITE), pieces(board, chess.BLACK)
    if not w or not b or sorted(w) == sorted(b):
        return []
    diff = pieces_value(board, chess.WHITE) - pieces_value(board, chess.BLACK)
    diff += len(board.pieces(chess.PAWN, chess.WHITE)) - len(board.pieces(chess.PAWN, chess.BLACK))
    if abs(diff) > 2:
        return []
    common, rest_b = list(w), list(b)
    for t in list(common):
        if t in rest_b:
            rest_b.remove(t)
            common.remove(t)
    if not common or not rest_b:
        return []

    def names(types):
        return "+".join(LETTER[t] for t in sorted(types, reverse=True))

    return [Finding("imbalance", f"Material imbalance: {names(common)} against {names(rest_b)}", False)]


# ── King safety, threats, loose pieces ────────────────────────────────────────────────────────────────────────


def king_safety_and_threats(board) -> list[Finding]:
    out = []
    for color in chess.COLORS:
        king = board.king(color)
        if king is None or rel_rank(king, color) != 0:
            continue
        if not (board.pieces(chess.ROOK, not color) | board.pieces(chess.QUEEN, not color)):
            continue
        f = chess.square_file(king)
        if (board.pieces(chess.ROOK, color) | board.pieces(chess.QUEEN, color)) & chess.SquareSet(chess.BB_RANKS[chess.square_rank(king)]):
            continue  # a rook or the queen guards the back rank
        front = [chess.square(ff, chess.square_rank(king) + (1 if color == chess.WHITE else -1)) for ff in (f - 1, f, f + 1) if 0 <= ff < 8]
        if all(board.color_at(s) == color or board.is_attacked_by(not color, s) for s in front) \
                and any(board.piece_type_at(s) == chess.PAWN and board.color_at(s) == color for s in front):
            out.append(Finding("back-rank-weakness", f"King {chess.square_name(king)} without an escape square ({SIDE[color]})", False))
    if not board.is_check() and not board.is_game_over():
        b = board.copy(stack=False)
        b.push(chess.Move.null())
        if not b.is_check():
            mates = mates_in_one(b)
            if mates:
                out.append(Finding("mate-threat", f"{SIDE[b.turn]} threatens {b.san(mates[0])}", False))
    if board.has_legal_en_passant():
        out.append(Finding("en-passant", "En passant is possible", False))
    for move in board.legal_moves:
        if board.is_capture(move) and not board.is_en_passant(move):
            victim = board.piece_type_at(move.to_square)
            if victim and victim != chess.KING and VALUE[victim] >= 3 and not board.is_attacked_by(not board.turn, move.to_square):
                out.append(Finding("hanging-piece", f"Undefended: {NAME[victim]} {chess.square_name(move.to_square)}", False))
                break
    return out


# ── Endgame set-ups ───────────────────────────────────────────────────────────────────────────────────────────


def endgame_setups(board) -> list[Finding]:  # noqa: C901 (one catalogue, kept together)
    out = []
    w, b = pieces(board, chess.WHITE), pieces(board, chess.BLACK)
    for color in chess.COLORS:  # wrong rook pawn: K+B+rook pawn(s) against a bare king, the bishop misses the corner
        if pieces(board, color) == [chess.BISHOP] and not pieces(board, not color) and not board.pieces(chess.PAWN, not color):
            pawns = board.pieces(chess.PAWN, color)
            files = {chess.square_file(s) for s in pawns}
            if pawns and len(files) == 1 and files <= {0, 7}:
                promo = chess.square(files.pop(), 7 if color == chess.WHITE else 0)
                bishop = next(iter(board.pieces(chess.BISHOP, color)))
                if square_colour(bishop) != square_colour(promo):
                    out.append(Finding("wrong-rook-pawn", f"Wrong rook pawn: the bishop doesn't control {chess.square_name(promo)}", True))
    if only_kings_and_pawns(board):
        wk, bk = board.king(chess.WHITE), board.king(chess.BLACK)
        if wk is not None and bk is not None:
            same_file, same_rank = chess.square_file(wk) == chess.square_file(bk), chess.square_rank(wk) == chess.square_rank(bk)
            if same_file or same_rank:
                gap = abs(chess.square_rank(wk) - chess.square_rank(bk)) if same_file else abs(chess.square_file(wk) - chess.square_file(bk))
                if gap == 2:
                    out.append(Finding("opposition", f"The kings in opposition ({chess.square_name(wk)}/{chess.square_name(bk)})", False))
                elif gap in (4, 6):
                    out.append(Finding("distant-opposition", f"Distant opposition ({chess.square_name(wk)}/{chess.square_name(bk)})", False))
            if passers(board, chess.WHITE) and passers(board, chess.BLACK):
                out.append(Finding("pawn-race", "Both sides have passed pawns", False))
            for color in chess.COLORS:
                for sq in passers(board, color):
                    promo = chess.square(chess.square_file(sq), 7 if color == chess.WHITE else 0)
                    pawn_dist = 7 - rel_rank(sq, color) - (1 if rel_rank(sq, color) == 1 else 0)
                    king = board.king(not color)
                    king_dist = chess.square_distance(king, promo) - (1 if board.turn != color else 0)
                    if abs(king_dist - pawn_dist) <= 1:
                        out.append(Finding("rule-of-square", f"Rule of the square: pawn {chess.square_name(sq)} against king {chess.square_name(king)}", False))
                        break
    if sorted(w + b) == [chess.ROOK, chess.ROOK] and len(w) == len(b) == 1:  # rook endings with one pawn
        pawns = [(c, s) for c in chess.COLORS for s in board.pieces(chess.PAWN, c)]
        if len(pawns) == 1:
            color, pawn = pawns[0]
            f = chess.square_file(pawn)
            att, deff = board.king(color), board.king(not color)
            rook_d = next(iter(board.pieces(chess.ROOK, not color)))
            if rel_rank(pawn, color) == 6 and chess.square_file(att) == f and rel_rank(att, color) == 7 and abs(chess.square_file(deff) - f) >= 2:
                out.append(Finding("lucena", f"Lucena position: king {chess.square_name(att)} in front of the pawn, the defender cut off", False))
            if rel_rank(pawn, color) <= 4 and abs(chess.square_file(deff) - f) <= 1 and rel_rank(deff, color) >= 6 and rel_rank(rook_d, color) == 5:
                out.append(Finding("philidor", f"Philidor position: rook {chess.square_name(rook_d)} on the defender's third rank", False))
    return out


def static_features(board, phase_key: str) -> list[Finding]:
    endgame = phase_key == "endgame"
    out = pawn_structure(board, endgame) + bishops_and_rooks(board, endgame) + material_imbalance(board) + king_safety_and_threats(board)
    out += endgame_setups(board)
    wb, bb = board.pieces(chess.BISHOP, chess.WHITE), board.pieces(chess.BISHOP, chess.BLACK)
    if len(wb) == 1 and len(bb) == 1 and square_colour(next(iter(wb))) != square_colour(next(iter(bb))) and len(pieces(board, chess.WHITE)) > 1:
        out.append(Finding("opposite-bishops", "Opposite-coloured bishops", False))
    return out
