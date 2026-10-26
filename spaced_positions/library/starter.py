"""The starter pack (spec 10 · decision 16): a small public-domain pack by motif, from the lichess puzzle database
(CC0, https://database.lichess.org/#puzzles), shipped with the app (`library/data/starter.sppack`) and offered on the
first-run screen. `manage.py starter <lichess_db_puzzle.csv>` builds it again from a newer database file.

Each motif gets the same number of well-tested puzzles (played often, liked, with a settled rating), spread over four
rating bands, so the pack has something for a beginner and something for a club player in every motif. A lichess
puzzle starts with the opponent's move: the position is the one before it, the puzzle starts after it (as in lichess).
The selection is deterministic: the same database file gives the same pack."""

from __future__ import annotations

import csv
import heapq
import io
import json
import uuid
import zipfile
from pathlib import Path

import chess
import chess.pgn

from . import packs

PACK_ID = uuid.uuid5(uuid.NAMESPACE_URL, "https://spaced-positions/starter-pack")
PATH = Path(__file__).resolve().parent / "data" / "starter.sppack"

# lichess themes → our tags (library/data/tags.json); themes without a counterpart (short, long, master …) stay out
THEMES = {
    "opening": "opening", "middlegame": "middlegame", "endgame": "endgame",
    "mateIn1": "mate-in-1", "mateIn2": "mate-in-2", "mateIn3": "mate-in-3", "mateIn4": "mate-in-4-plus", "mateIn5": "mate-in-4-plus",
    "defensiveMove": "defend", "equality": "draw",
    "fork": "fork", "pin": "pin", "skewer": "skewer", "discoveredAttack": "discovered-attack", "discoveredCheck": "discovered-check",
    "doubleCheck": "double-check", "deflection": "deflection", "attraction": "decoy", "capturingDefender": "removal-of-guard",
    "clearance": "clearance", "interference": "interference", "intermezzo": "zwischenzug", "xRayAttack": "x-ray",
    "trappedPiece": "trapped-piece", "hangingPiece": "hanging-piece", "quietMove": "quiet-move", "sacrifice": "sacrifice",
    "promotion": "promotion", "underPromotion": "underpromotion", "enPassant": "en-passant", "zugzwang": "zugzwang",
    "kingsideAttack": "king-attack", "queensideAttack": "king-attack", "advancedPawn": "passed-pawn",
    "backRankMate": "back-rank-mate", "smotheredMate": "smothered-mate", "arabianMate": "arabian-mate", "anastasiaMate": "anastasia-mate",
    "hookMate": "hook-mate", "operaMate": "opera-mate", "pillsburysMate": "pillsbury-mate", "epauletteMate": "epaulette-mate",
    "cornerMate": "corner-mate", "triangleMate": "triangle-mate", "morphysMate": "morphy-mate", "blindSwineMate": "blind-swine-mate",
    "killBoxMate": "kill-box-mate", "swallowstailMate": "swallows-tail-mate", "dovetailMate": "dovetail-mate", "bodenMate": "boden-mate",
    "vukovicMate": "vukovic-mate", "balestraMate": "balestra-mate", "doubleBishopMate": "double-bishop-mate",
    "pawnEndgame": "pawn-endgame", "rookEndgame": "rook-endgame", "bishopEndgame": "bishop-endgame", "knightEndgame": "knight-endgame",
    "queenEndgame": "queen-endgame", "queenRookEndgame": "heavy-piece-endgame",
}

# The motifs the pack is made of, in the order they are filled (a puzzle is used once, by the first motif that takes it)
MOTIFS = [
    "mate-in-1", "mate-in-2", "mate-in-3",
    "fork", "pin", "skewer", "discovered-attack", "discovered-check", "double-check", "deflection", "decoy", "removal-of-guard",
    "clearance", "interference", "zwischenzug", "x-ray", "trapped-piece", "hanging-piece", "quiet-move", "sacrifice",
    "promotion", "underpromotion", "en-passant", "zugzwang",
    "back-rank-mate", "smothered-mate", "arabian-mate", "anastasia-mate", "hook-mate", "opera-mate", "pillsbury-mate",
    "epaulette-mate", "corner-mate", "triangle-mate", "morphy-mate", "blind-swine-mate", "kill-box-mate", "swallows-tail-mate",
    "dovetail-mate", "boden-mate", "vukovic-mate", "balestra-mate",
    "pawn-endgame", "rook-endgame", "bishop-endgame", "knight-endgame", "queen-endgame",
]
BANDS = [(800, 1100), (1100, 1400), (1400, 1700), (1700, 2000)]
SPARE = 40  # candidates kept per motif and band, so motifs that share puzzles still fill up


def difficulty(rating: int) -> int:
    """1–5 from the lichess rating."""
    return 1 if rating < 1000 else 2 if rating < 1300 else 3 if rating < 1600 else 4 if rating < 1900 else 5


def well_tested(row: dict) -> bool:
    return int(row["NbPlays"]) >= 1000 and int(row["Popularity"]) >= 85 and int(row["RatingDeviation"]) <= 80


def tags_of(themes: list[str]) -> list[str]:
    tags = list(dict.fromkeys(THEMES[t] for t in themes if t in THEMES))
    if not any(t.startswith("mate-in") or t in ("defend", "draw") for t in tags):
        tags.append("winning-continuation")  # lichess puzzles are about the winning line
    return tags


def movetext(fen: str, ucis: list[str]) -> str:
    board = chess.Board(fen)
    game = chess.pgn.Game()
    game.setup(board)
    node = game
    for uci in ucis:
        node = node.add_variation(chess.Move.from_uci(uci))
    return game.accept(chess.pgn.StringExporter(headers=False, columns=None)).strip().removesuffix(" *")


def record(row: dict) -> dict:
    ucis = row["Moves"].split()
    rating = int(row["Rating"])
    end = "0" + ".0" * (len(ucis) - 1)  # the last move of the main line
    return {"id": str(uuid.uuid5(PACK_ID, row["PuzzleId"])), "fen": row["FEN"], "title": f"Lichess {row['PuzzleId']}",
            "desc": f"https://lichess.org/training/{row['PuzzleId']}", "src": 0, "ref": row["PuzzleId"], "diff": difficulty(rating),
            "tags": tags_of(row["Themes"].split()), "moves": movetext(row["FEN"], ucis),
            "puzzles": [{"start": "0", "active": True, "ends": [end]}]}


def select(rows, per_band: int) -> list[dict]:
    """`per_band` puzzles for each motif and rating band: the most liked and most played first, each puzzle once."""
    known = packs.builtin_tags()
    missing = (set(THEMES.values()) | set(MOTIFS) | {"winning-continuation"}) - known
    if missing:
        raise ValueError(f"tags missing from the vocabulary: {sorted(missing)}")
    best: dict[tuple, list] = {}  # (motif, band) → a heap of (score, id, row), the best SPARE
    for row in rows:
        if not well_tested(row):
            continue
        rating = int(row["Rating"])
        band = next((i for i, (lo, hi) in enumerate(BANDS) if lo <= rating < hi), None)
        if band is None:
            continue
        score = (int(row["Popularity"]), int(row["NbPlays"]))
        for tag in set(tags_of(row["Themes"].split())) & set(MOTIFS):
            heap = best.setdefault((tag, band), [])
            item = (score, row["PuzzleId"], row)
            if len(heap) < SPARE:
                heapq.heappush(heap, item)
            elif item > heap[0]:
                heapq.heapreplace(heap, item)
    used, chosen = set(), []
    for tag in MOTIFS:
        for band in range(len(BANDS)):
            ranked = sorted(best.get((tag, band), []), key=lambda x: (-x[0][0], -x[0][1], x[1]))
            for _score, pid, row in [r for r in ranked if r[1] not in used][:per_band]:
                used.add(pid)
                chosen.append(row)
    return chosen


def build(csv_path: Path, out: Path = PATH, per_band: int = 4, version: int | None = None) -> dict:
    """Write the starter pack from a lichess puzzle database file (CSV); returns its manifest."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = select(csv.DictReader(f), per_band)
    records = [record(r) for r in rows]
    if version is None:  # the database file's date (20261026): a newer file, a newer version of the pack
        from datetime import date

        version = int(date.fromtimestamp(Path(csv_path).stat().st_mtime).strftime("%Y%m%d"))
    manifest = {
        "format": packs.FORMAT, "pack": str(PACK_ID), "version": version, "title": "Starter pack · lichess puzzles",
        "author": "Spaced Positions",
        "description": "Puzzles by motif from the lichess.org puzzle database: forks, pins, mating patterns, endgames and more, "
                       "from beginner to club level.",
        "licence": "Public domain (CC0): the lichess.org puzzle database, https://database.lichess.org/#puzzles",
        "positions": len(records), "puzzles": len(records), "games": 0,
    }
    sources = [{"title": "Lichess puzzle database", "short": "Lichess", "kind": "website", "url": "https://database.lichess.org/#puzzles"}]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        def put(name: str, text: str):  # a fixed time in the zip: the same database file gives the same bytes
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            z.writestr(info, text)

        put("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        put("positions.jsonl", "".join(packs._Writer.line(r) + "\n" for r in records))
        put("sources.json", json.dumps(sources, ensure_ascii=False, separators=(",", ":")))
        put("tags.json", "[]")
    out.write_bytes(buf.getvalue())
    return manifest
