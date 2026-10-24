"""Motifs that only show over a sequence of moves (python-chess): exchange and double-bishop sacrifices, intermezzo,
trapped pieces, interference, self-block, batteries put to use, liquidation, breakthrough, triangulation, mate
threats, windmills, perpetual check and the mad rook. chess-study-manager's detection/sequences.py, kept.

`line_features(board, moves, only=None)` walks a line from `board` and returns [(index, tag key, evidence)] for the
moves of the side that plays moves[only] (default: the side to move at the start, the solver of a puzzle).
"""

import chess

from .detect import NAMES, VALUE, balance, label, mates_in_one

BACK_SQUARES = {chess.WHITE: (chess.H7, chess.G7), chess.BLACK: (chess.H2, chess.G2)}
APPLIED = {"exchange-sacrifice", "double-bishop-sacrifice", "zwischenzug", "trapped-piece", "queen-trap", "breakthrough",
           "triangulation", "windmill", "perpetual-check", "mad-rook"}


def only_kings_and_pawns(board) -> bool:
    return not any(board.pieces(t, c) for t in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN) for c in chess.COLORS)


def batteries(board, color) -> list:
    """Queen and bishop on a diagonal, or queen and rook on a file or rank, next to each other and aimed at the
    king's surroundings."""
    king = board.king(not color)
    if king is None:
        return []
    zone = chess.SquareSet(chess.BB_KING_ATTACKS[king]) | chess.SquareSet.from_square(king)
    sliders = board.pieces(chess.QUEEN, color) | board.pieces(chess.BISHOP, color) | board.pieces(chess.ROOK, color)
    for front in sliders:
        for back in sliders:
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
                continue
            beyond = [s for s in chess.SquareSet(chess.ray(back, front)) if chess.square_distance(s, back) > chess.square_distance(front, back)
                      and chess.square_distance(s, front) < chess.square_distance(s, back)]
            if any(s in zone and not (chess.SquareSet(chess.between(front, s)) & board.occupied) for s in beyond):
                return [(back, front)]
    return []


def _taking_stalemates(board, rook_square) -> bool:
    takes = [mv for mv in board.legal_moves if mv.to_square == rook_square]
    if not takes:
        return False
    for mv in takes:
        b = board.copy(stack=False)
        b.push(mv)
        if not b.is_stalemate():
            return False
    return True


def line_features(board, moves, only=None) -> list[tuple[int, str, str]]:  # noqa: C901
    if not moves:
        return []
    boards, b = [], board.copy(stack=False)
    for m in moves:
        boards.append(b.copy())
        b.push(m)
    boards.append(b)
    final = boards[-1]
    side = boards[only if only is not None else 0].turn
    start_balance = balance(boards[only or 0], side)
    ends_well = final.is_checkmate() and final.turn != side or balance(final, side) >= start_balance - 1
    out = []
    idx = [only] if only is not None else [i for i in range(len(moves)) if boards[i].turn == side]

    def nxt(i, k=1):
        j = i + 2 * k
        return j if j < len(moves) else None

    first = idx[0]
    if ends_well and len(moves) - first >= 3:
        bishop_sacs = [i for i in range(first, len(moves) - 1)
                       if boards[i].turn == side and boards[i].piece_type_at(moves[i].from_square) == chess.BISHOP
                       and moves[i].to_square in BACK_SQUARES[side] and boards[i + 1].is_capture(moves[i + 1])
                       and moves[i + 1].to_square == moves[i].to_square]
        if len(bishop_sacs) >= 2:
            out.append((bishop_sacs[0], "double-bishop-sacrifice", f"Two bishop sacrifices: {label(boards[bishop_sacs[0]], moves[bishop_sacs[0]])} …"))
    start_pieces = [p for p in boards[first].piece_map().values() if p.piece_type not in (chess.KING, chess.PAWN)]
    if start_pieces and only_kings_and_pawns(final) and not final.is_checkmate() and len(moves) - first >= 2 \
            and balance(final, side) >= start_balance:
        out.append((first, "liquidation", "Liquidation into a pawn ending"))

    for i in idx:
        before, after, m = boards[i], boards[i + 1], moves[i]
        text = label(before, m)
        piece = before.piece_type_at(m.from_square)
        reply = moves[i + 1] if i + 1 < len(moves) else None

        if piece == chess.ROOK and reply is not None and after.is_capture(reply) and reply.to_square == m.to_square \
                and after.piece_type_at(reply.from_square) in (chess.KNIGHT, chess.BISHOP, chess.PAWN) and ends_well:
            out.append((i, "exchange-sacrifice", f"Exchange sacrifice {text}"))

        if i >= 1:  # intermezzo: the opponent just took something; a check or capture first, then the recapture
            prev, pb = moves[i - 1], boards[i - 1]
            j = nxt(i)
            if pb.is_capture(prev) and pb.color_at(prev.to_square) == side and m.to_square != prev.to_square \
                    and (after.is_check() or before.is_capture(m)) and j is not None \
                    and moves[j].to_square == prev.to_square and boards[j].is_capture(moves[j]):
                out.append((i, "zwischenzug", f"Intermezzo {text} before taking back"))

        for sq, p in after.piece_map().items():  # trapped piece: en prise, no safe square, falls within 4 plies
            if p.color == side or p.piece_type in (chess.KING, chess.PAWN) or VALUE[p.piece_type] < 3:
                continue
            attackers = after.attackers(side, sq)
            if not attackers:
                continue
            cheapest = min(VALUE[after.piece_type_at(a)] for a in attackers)
            if after.is_attacked_by(not side, sq) and cheapest >= VALUE[p.piece_type]:
                continue
            if before.piece_at(sq) == p and before.is_attacked_by(side, sq):
                continue
            escapes = [mv for mv in after.legal_moves if mv.from_square == sq]
            if any(not after.is_attacked_by(side, mv.to_square)
                   or (after.piece_type_at(mv.to_square) and VALUE[after.piece_type_at(mv.to_square)] >= VALUE[p.piece_type])
                   for mv in escapes):
                continue
            where, falls = sq, False
            for k in range(i + 1, min(len(moves), i + 5)):
                if boards[k].turn != side and moves[k].from_square == where:
                    where = moves[k].to_square
                elif boards[k].turn == side and moves[k].to_square == where and boards[k].is_capture(moves[k]):
                    falls = True
                    break
            if falls:
                key = "queen-trap" if p.piece_type == chess.QUEEN else "trapped-piece"
                out.append((i, key, f"{text} traps the {NAMES[p.piece_type]} on {chess.square_name(sq)}"))
                break

        j = nxt(i)
        if j is not None and boards[j].turn == side:  # interference
            target = moves[j].to_square
            if target != m.to_square and (boards[j].is_capture(moves[j]) or boards[j].gives_check(moves[j]) or moves[j].promotion):
                for s in before.attackers(not side, target):
                    kind = before.piece_type_at(s)
                    if kind in (chess.BISHOP, chess.ROOK, chess.QUEEN) and m.to_square in chess.SquareSet(chess.between(s, target)) \
                            and boards[j].piece_type_at(s) == kind and s not in boards[j].attackers(not side, target) and s != m.to_square:
                        out.append((i, "interference", f"{text} blocks the {NAMES[kind]} on {chess.square_name(s)}"))
                        break

        if piece in (chess.QUEEN, chess.BISHOP, chess.ROOK) and j is not None:  # a battery put to use
            if batteries(after, side) and boards[j].piece_type_at(moves[j].from_square) in (chess.QUEEN, chess.BISHOP, chess.ROOK) \
                    and (boards[j].gives_check(moves[j]) or boards[j].is_capture(moves[j])) and not batteries(before, side):
                out.append((i, "battery", f"{text} builds a battery"))

        if not after.is_check() and not before.is_capture(m) and not after.is_game_over():  # mate threat
            probe = after.copy(stack=False)
            probe.push(chess.Move.null())
            if not probe.is_check():
                mates = mates_in_one(probe)
                if mates and not mates_in_one(before):
                    out.append((i, "mate-threat", f"{text} threatens {probe.san(mates[0])}"))

        if piece == chess.PAWN and only_kings_and_pawns(before) and reply is not None and after.is_capture(reply) \
                and reply.to_square == m.to_square and any(boards[k].turn == side and moves[k].promotion for k in range(i + 2, len(moves))):
            out.append((i, "breakthrough", f"Breakthrough with {text}"))

        js = [i, nxt(i), nxt(i, 2)]  # triangulation
        if all(k is not None for k in js) and all(boards[k].piece_type_at(moves[k].from_square) == chess.KING for k in js) \
                and moves[js[2]].to_square == m.from_square:
            a, b_, c = m.from_square, m.to_square, moves[js[1]].to_square
            if len({a, b_, c}) == 3 and all(chess.square_distance(x, y) == 1 for x, y in ((a, b_), (b_, c), (c, a))):
                out.append((i, "triangulation", f"Triangulation {chess.square_name(a)}–{chess.square_name(b_)}–{chess.square_name(c)}"))

        if after.is_check() and m.to_square not in after.checkers():  # windmill
            checker = next(iter(after.checkers()))
            again = [k for k in (nxt(i), nxt(i, 2)) if k is not None and boards[k + 1].is_check()
                     and checker in boards[k + 1].checkers() and moves[k].to_square not in boards[k + 1].checkers()]
            if again:
                out.append((i, "windmill", f"Windmill: discovered check {text} and again"))

        if len(moves) - i >= 4 and final.is_repetition(2) and all(boards[k + 1].is_check() for k in range(i, len(moves)) if boards[k].turn == side):
            out.append((i, "perpetual-check", f"Perpetual check from {text}"))

        if piece == chess.ROOK and after.is_check() and _taking_stalemates(after, m.to_square):  # mad rook
            more = [k for k in (nxt(i), nxt(i, 2)) if k is not None and boards[k].piece_type_at(moves[k].from_square) == chess.ROOK
                    and boards[k + 1].is_check() and _taking_stalemates(boards[k + 1], moves[k].to_square)]
            if more or final.is_stalemate():
                out.append((i, "mad-rook", f"Mad rook: {text}, taking it stalemates"))

    if final.is_checkmate() and final.turn != side:  # self-block
        king = final.king(final.turn)
        arrived = {moves[k].to_square for k in range(len(moves)) if boards[k].turn != side}
        blockers = [sq for sq in chess.SquareSet(chess.BB_KING_ATTACKS[king]) if final.color_at(sq) == final.turn and sq in arrived]
        if blockers:
            out.append((idx[-1] if only is None else only, "self-block", f"Self-block on {chess.square_name(blockers[0])}"))

    seen, unique = set(), []
    for i, key, text in out:
        if (i, key) not in seen:
            seen.add((i, key))
            unique.append((i, key, text))
    return unique
