"""The key moments of a game or an analysis as move tags (`:moments`, spec 11 §1 · Detection; the old app's
`engine`, `moments` and `annotations` detectors).

- Engine, Lichess style, in winning chances (−1 … +1 for the mover, wc = 2 / (1 + e^(−0.00368208·cp)) − 1):
  drop = wc(best) − wc(played): ≥ 0.3 blunder · ≥ 0.2 mistake · ≥ 0.1 inaccuracy; a missed win (from ≥ 0.6 to
  ≤ 0.2); a turning point (from ≥ +0.3 to ≤ −0.3). With the local engine (two lines a move) also the only move (the
  best move, ≥ 0.3 ahead of the second, was played), the critical moment (it was missed) and the brilliant move (an
  only move that sacrifices material while the game isn't won yet). Without a local engine the evaluations
  `:evaluate` stored are used (no second line: no only moves).
- python-chess: a missed mate in one, a move that allows mate in one when a move would have avoided it, a tactical
  explosion (three captures within four plies).
- The annotator's symbols: !! brilliant, ! good, !? interesting, ?! inaccuracy, ? mistake, ?? blunder, □ only move.

Stored like the other detected tags: a tag the user removed stays removed, manual tags are untouched, and a new run
withdraws only the moments it set itself."""

from __future__ import annotations

import math

import chess
import chess.engine

from .detect import Finding, label, mates_in_one, move_findings

DETECTOR = "moments"
MAX_PLIES = 300
ENGINE_LIMIT = {"time": 0.15, "depth": 18}
THRESHOLDS = (("blunder", 0.3), ("mistake", 0.2), ("inaccuracy", 0.1))
ONLY_MOVE_GAP = 0.3
MIN_CHOICES = 4  # fewer legal moves: the move is forced, not found
EXPLOSION_PLIES, EXPLOSION_CAPTURES = 4, 3
NAG_MOMENTS = {3: "brilliant", 1: "good-move", 5: "interesting-move", 6: "inaccuracy", 2: "mistake", 4: "blunder", 7: "only-move"}
SYMBOL = {1: "!", 2: "?", 3: "!!", 4: "??", 5: "!?", 6: "?!", 7: "□"}
SACRIFICES = ("sacrifice", "queen-sacrifice", "exchange-sacrifice")


def winning_chances(cp: int | None = None, mate: int | None = None) -> float:
    """For the side the score is from: −1 … +1."""
    if mate is not None:
        cp = 100000 if mate > 0 else -100000
    cp = max(-3000, min(3000, cp or 0))
    return 2 / (1 + math.exp(-0.00368208 * cp)) - 1


def _white_wc(node) -> float | None:
    """A node's stored evaluation (after its move, from white's side) as white's winning chances."""
    board = chess.Board(node.fen)
    if board.is_checkmate():
        return -1.0 if board.turn == chess.WHITE else 1.0
    if board.is_game_over():
        return 0.0
    if node.eval_cp is None and node.eval_mate is None:
        return None
    return winning_chances(node.eval_cp, node.eval_mate)


def mainline(owner) -> list:
    """The main line's moves (nodes), at most MAX_PLIES."""
    from spaced_positions.analysis import tree

    all_nodes = tree.nodes(owner)
    by_id = {n.id: n for n in all_nodes}
    kids = tree.kids_map(all_nodes)
    node, out = tree.root(owner), []
    while kids.get(node.id) and len(out) < MAX_PLIES:
        node = kids[node.id][0]
        node.parent = by_id[node.parent_id]  # loaded once
        out.append(node)
    return out


def _judge(node, mover: chess.Color, best: float, played: float, second: float | None, best_move, sacrifice: bool) -> list[Finding]:
    """The engine's findings for one move, all in the mover's winning chances."""
    out = []
    board = chess.Board(node.parent.fen)
    is_best = best_move is not None and best_move.uci() == node.uci
    drop = best - played
    for key, threshold in THRESHOLDS:
        if drop >= threshold and not is_best:
            out.append(Finding(key, f"Winning chances {best:+.2f} → {played:+.2f}", True))
            break
    if best >= 0.6 and played <= 0.2:
        out.append(Finding("missed-win", f"A won position given away ({best:+.2f} → {played:+.2f})", True))
    if best >= 0.3 and played <= -0.3:
        out.append(Finding("turning-point", "The advantage changes sides", True))
    if second is not None and best - second >= ONLY_MOVE_GAP and board.legal_moves.count() >= MIN_CHOICES:
        if is_best:
            out.append(Finding("only-move", f"The only good move (the next best is {best - second:.2f} behind)", True))
            if sacrifice and best < 0.9:
                out.append(Finding("brilliant", "The only move, and a sacrifice", True))
        else:
            out.append(Finding("critical-moment", f"One good move, not found: {label(board, best_move)}", True))
    return out


def engine_findings(nodes, engine=None) -> dict[int, list[Finding]]:
    """With `engine` (python-chess SimpleEngine): two lines for every position. Without: the stored evaluations."""
    out: dict[int, list[Finding]] = {}
    cache: dict[str, list] = {}

    def analyse(fen):
        if fen not in cache:
            board = chess.Board(fen)
            cache[fen] = [] if board.is_game_over() else engine.analyse(board, chess.engine.Limit(**ENGINE_LIMIT), multipv=2)
        return cache[fen]

    for node in nodes:
        board = chess.Board(node.parent.fen)
        mover = board.turn
        sign = 1 if mover == chess.WHITE else -1
        if engine is None:
            before, after = _white_wc(node.parent), _white_wc(node)
            if node.parent.parent_id is None and before is None:
                before = 0.0 if board.fen().startswith(chess.STARTING_BOARD_FEN) else None
            if before is None or after is None:
                continue
            best, played, second, best_move = sign * before, sign * after, None, None
        else:
            infos = analyse(node.parent.fen)
            if not infos:
                continue
            best = winning_chances(*_score(infos[0], mover))
            second = winning_chances(*_score(infos[1], mover)) if len(infos) > 1 else None
            best_move = infos[0].get("pv", [None])[0]
            after_board = chess.Board(node.fen)
            if after_board.is_checkmate():
                played = 1.0
            elif after_board.is_game_over():
                played = 0.0
            else:
                reply = analyse(node.fen)
                played = winning_chances(*_score(reply[0], mover)) if reply else 0.0
        sacrifice = engine is not None and any(f.tag in SACRIFICES for f in move_findings(node))
        found = _judge(node, mover, best, played, second, best_move, sacrifice)
        if found:
            out[node.id] = found
    return out


def _score(info, mover) -> tuple[int | None, int | None]:
    score = info["score"].pov(mover)
    return score.score(), score.mate()


def chess_findings(nodes) -> dict[int, list[Finding]]:
    """What python-chess sees without an engine: missed mates, allowed mates, tactical explosions."""
    out: dict[int, list[Finding]] = {}
    by_id = {n.id: n for n in nodes}
    for i, node in enumerate(nodes):
        before = chess.Board(node.parent.fen)
        move = chess.Move.from_uci(node.uci)
        after = before.copy(stack=False)
        after.push(move)
        found = []
        mates = mates_in_one(before)
        if mates and not after.is_checkmate():
            found.append(Finding("missed-mate", f"Mate in one was there: {label(before, mates[0])}", True))
        if not after.is_game_over() and mates_in_one(after):
            safe = next((m for m in before.legal_moves if not _allows_mate(before, m)), None)
            if safe is not None:
                found.append(Finding("allows-mate", f"Allows mate in one; {label(before, safe)} would have prevented it", True))
        prev = by_id.get(node.parent_id)
        prev_capture = prev is not None and chess.Board(prev.parent.fen).is_capture(chess.Move.from_uci(prev.uci))
        if before.is_capture(move) and not prev_capture:
            b, captures = before.copy(stack=False), 0
            for later in nodes[i : i + EXPLOSION_PLIES]:
                m = chess.Move.from_uci(later.uci)
                captures += b.is_capture(m)
                b.push(m)
            if captures >= EXPLOSION_CAPTURES:
                found.append(Finding("tactical-explosion", f"{captures} captures in {EXPLOSION_PLIES} plies", True))
        if found:
            out[node.id] = found
    return out


def _allows_mate(board, move) -> bool:
    b = board.copy(stack=False)
    b.push(move)
    return not b.is_game_over() and bool(mates_in_one(b))


def annotation_findings(nodes) -> dict[int, list[Finding]]:
    out: dict[int, list[Finding]] = {}
    for node in nodes:
        found = [Finding(NAG_MOMENTS[nag], f"Annotated {SYMBOL[nag]}", True) for nag in node.nags or [] if nag in NAG_MOMENTS]
        if found:
            out[node.id] = found
    return out


def local_engine():
    """A python-chess engine for the local engine program, or None (no program set up)."""
    from spaced_positions.core.engine_local import program

    path, _problem = program()
    if path is None:
        return None
    try:
        return chess.engine.SimpleEngine.popen_uci(path)
    except (OSError, chess.engine.EngineError):
        return None


def run(owner, use_engine: bool = True) -> dict:
    """Find and store the moments of the main line; returns {"tags": n, "moves": n, "engine": "local" | "stored" | ""}."""
    from .models import NodeTag, Tag, TagDismissal

    nodes = mainline(owner)
    engine = local_engine() if use_engine else None
    try:
        by_engine = engine_findings(nodes, engine)
    finally:
        if engine is not None:
            engine.quit()
    used = "local" if engine is not None else ("stored" if by_engine or any(n.eval_cp is not None or n.eval_mate is not None for n in nodes) else "")
    findings: dict[int, dict[str, Finding]] = {}
    for source in (annotation_findings(nodes), chess_findings(nodes), by_engine):
        for node_id, found in source.items():
            for f in found:
                findings.setdefault(node_id, {}).setdefault(f.tag, f)  # the annotator's word first
    tags = {t.key: t for t in Tag.objects.filter(field__on_moves=True)}
    dismissed = set(TagDismissal.objects.filter(node__in=nodes).values_list("node_id", "tag_id"))
    kept = set()
    added = 0
    for node in nodes:
        for key, f in findings.get(node.id, {}).items():
            tag = tags.get(key)
            if tag is None or (node.id, tag.pk) in dismissed:
                continue
            link, made = NodeTag.objects.get_or_create(node=node, tag=tag, defaults={"origin": "auto", "detector": DETECTOR, "evidence": f.evidence[:200]})
            if not made and link.detector == DETECTOR and link.evidence != f.evidence[:200]:
                link.evidence = f.evidence[:200]
                link.save(update_fields=["evidence"])
            kept.add(link.pk)
            added += made
    stale = NodeTag.objects.filter(node__in=nodes, detector=DETECTOR).exclude(origin="manual").exclude(pk__in=kept)
    withdrawn = stale.count()
    stale.delete()
    return {"tags": added, "withdrawn": withdrawn, "moves": len(findings), "engine": used}
