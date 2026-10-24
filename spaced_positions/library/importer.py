"""PGN import (spec 11 §4, decision 20): games with their variations, comments, NAGs and drawings; short lines from a
set-up position without players are puzzles. `scan` shows what a PGN holds (duplicates marked), `run` imports the
chosen items. Players are matched by name and aliases; names that match nobody stay text on the game."""

from __future__ import annotations

import hashlib
import json
import re

import chess
import chess.pgn
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from spaced_positions import chesslogic
from spaced_positions.analysis import pgn as pgn_io
from spaced_positions.analysis import puzzles as analysis_puzzles
from spaced_positions.analysis import tree
from spaced_positions.training.models import Position

from .collect import duplicate_of
from .detect import run as run_detection
from .models import Game, Player
from .text import fold

MAX_TEXT = 20_000_000
MAX_GAMES = 5000
PUZZLE_PLIES = 16
ROSTER = {"Event", "Site", "Date", "Round", "White", "Black", "Result", "WhiteElo", "BlackElo", "ECO", "Annotator", "FEN", "SetUp"}


def _empty(name) -> bool:
    return not name or name.strip() in ("?", "-", "")


def _mainline(game) -> list[str]:
    return [m.uci() for m in game.mainline_moves()]


def kind_of(game) -> str:
    h = game.headers
    if "FEN" in h and _empty(h.get("White")) and _empty(h.get("Black")) and 0 < len(_mainline(game)) <= PUZZLE_PLIES:
        return "puzzle"
    return "game"


def dedupe_of(game) -> str:
    h = game.headers
    key = "|".join([fold(h.get("White", "")), fold(h.get("Black", "")), h.get("Result", "*"), game.board().fen(), " ".join(_mainline(game)[:40])])
    return hashlib.sha1(key.encode()).hexdigest()


def title_of(game, kind) -> str:
    h = game.headers
    if kind == "puzzle":
        return h.get("Event", "") if not _empty(h.get("Event")) else "Puzzle"
    year = (h.get("Date", "") or "")[:4]
    players = f"{h.get('White', '?')} – {h.get('Black', '?')}"
    return " ".join(x for x in [players, h.get("Result", "") if h.get("Result") != "*" else "", year if year.isdigit() else ""] if x)


def _duplicate(game, kind) -> str | None:
    if kind == "game":
        found = Game.objects.filter(dedupe=dedupe_of(game), deleted_at=None).first()
        return found.short_id if found else None
    board = game.board()
    check = chesslogic.check_fen(board.fen())
    existing = duplicate_of(check.get("canonical") or "")
    if existing is None:
        return None
    first = _mainline(game)[:1]
    same = existing.puzzles.filter(solution__moves__0__uci=first[0]).exists() if first else False
    return existing.short_id if same or not first else None


def scan(text: str) -> list[dict]:
    items = []
    for i, game in enumerate(pgn_io.read_games(text, MAX_GAMES)):
        kind = kind_of(game)
        error = "; ".join(str(e) for e in game.errors[:2]) if game.errors else ""
        items.append({
            "i": i, "kind": kind, "title": title_of(game, kind), "plies": len(_mainline(game)),
            "duplicate": _duplicate(game, kind), "error": error,
        })
    return items


# ── Players ───────────────────────────────────────────────────────────────────────────────────────────────────


class Players:
    """Matches PGN names to players: by name or alias, or 'Tal, M.' to 'Tal, Mikhail' when the initial fits."""

    def __init__(self):
        self.players = list(Player.objects.all())

    def match(self, name: str) -> Player | None:
        if _empty(name):
            return None
        f = fold(name)
        for p in self.players:
            if any(fold(n) == f for n in [p.name, *p.aliases]):
                return p
        last, _, first = (x.strip() for x in f.partition(","))
        if not first:
            return None
        initial = first[0]
        for p in self.players:
            for n in [p.name, *p.aliases]:
                p_last, _, p_first = (x.strip() for x in fold(n).partition(","))
                if p_last == last and p_first.startswith(initial):
                    return p
        return None


# ── Importing ─────────────────────────────────────────────────────────────────────────────────────────────────


def _int(value) -> int | None:
    m = re.match(r"^\d{3,4}$", str(value or "").strip())
    return int(m.group()) if m else None


def import_game(game, players: Players, source=None) -> Game:
    h = game.headers
    g = Game.objects.create(
        white=players.match(h.get("White", "")), black=players.match(h.get("Black", "")),
        white_name=h.get("White", "") if not _empty(h.get("White")) else "",
        black_name=h.get("Black", "") if not _empty(h.get("Black")) else "",
        white_elo=_int(h.get("WhiteElo")), black_elo=_int(h.get("BlackElo")), result=h.get("Result", "*")[:8],
        date=h.get("Date", "")[:20], year=_int((h.get("Date", "") or "")[:4]), event=h.get("Event", "")[:200] if not _empty(h.get("Event")) else "",
        site=h.get("Site", "")[:200] if not _empty(h.get("Site")) else "", round=h.get("Round", "")[:20] if not _empty(h.get("Round")) else "",
        eco=h.get("ECO", "")[:6], annotator=h.get("Annotator", "")[:150],
        headers={k: v for k, v in h.items() if k not in ROSTER}, start_fen=game.board().fen(), pgn=str(game)[:200_000],
        dedupe=dedupe_of(game), source=source,
    )
    pgn_io.fill_tree(tree.root(g), game)
    return g


def import_puzzle(game, ready: bool, source=None) -> Position:
    board = game.board()
    position = tree.create_position(board.fen(), [], title=title_of(game, "puzzle")[:200], origin="import")
    if source:
        position.source = source
        position.save(update_fields=["source"])
    root = tree.root(position)
    pgn_io.fill_tree(root, game)
    analysis_puzzles.act(root, "start")
    if ready:
        position.puzzles.filter(start_node=root).update(active=True)
    analysis_puzzles.rebuild_all(position)
    run_detection(position, search=False)
    return position


def run(text: str, selected: set[int] | None, ready: bool) -> dict:
    players = Players()
    games, positions, failed = [], [], 0
    with transaction.atomic():
        for i, game in enumerate(pgn_io.read_games(text, MAX_GAMES)):
            if selected is not None and i not in selected:
                continue
            try:
                with transaction.atomic():
                    if kind_of(game) == "puzzle":
                        positions.append(import_puzzle(game, ready))
                    else:
                        games.append(import_game(game, players))
            except (ValueError, tree.TreeError, chess.IllegalMoveError):
                failed += 1
    return {"games": games, "positions": positions, "failed": failed}


def _body(request) -> dict:
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


@require_POST
def scan_view(request):
    text = str(_body(request).get("text", ""))
    if len(text) > MAX_TEXT:
        return JsonResponse({"ok": False, "message": "the file is larger than 20 MB: split it"}, status=422)
    items = scan(text)
    if not items:
        return JsonResponse({"ok": False, "message": "no games in this text"}, status=422)
    return JsonResponse({"ok": True, "items": items})


@require_POST
def run_view(request):
    data = _body(request)
    text = str(data.get("text", ""))
    if len(text) > MAX_TEXT:
        return JsonResponse({"ok": False, "message": "the file is larger than 20 MB"}, status=422)
    selected = {int(i) for i in data.get("selected", []) if str(i).isdigit()} if "selected" in data else None
    result = run(text, selected, bool(data.get("ready")))
    g, p = len(result["games"]), len(result["positions"])
    parts = [f"Imported {g} game{'s' if g != 1 else ''}"] if g else []
    if p:
        parts.append(f"{p} puzzle{'s' if p != 1 else ''}" + (" in training" if data.get("ready") else " as drafts"))
    if result["failed"]:
        parts.append(f"{result['failed']} could not be read")
    added = {"games": [x.short_id for x in result["games"]], "positions": [x.short_id for x in result["positions"]]}
    return JsonResponse({
        "ok": True, "message": " · ".join(parts) or "Nothing imported", "added": added,
        "first": str((result["games"] or result["positions"])[0].uuid) if (g or p) else None,
        "undo": {"command": "library.trashmany", "args": [json.dumps(added | {"restore": False})]},
        "redo": {"command": "library.trashmany", "args": [json.dumps(added | {"restore": True})]},
    })
