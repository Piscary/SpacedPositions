"""The starter pack (spec 09 §12, decision 16): built from the lichess puzzle database, shipped with the app."""

import csv
import io
import json
import zipfile

import pytest

from spaced_positions.library import packs, starter
from spaced_positions.training.models import Puzzle

HEADER = ["PuzzleId", "FEN", "Moves", "Rating", "RatingDeviation", "Popularity", "NbPlays", "Themes", "GameUrl", "OpeningTags"]
FORK = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"  # 4.Qxf7#: mate in 1


def sample(tmp_path, rows):
    path = tmp_path / "puzzles.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)
    return path


def row(pid, rating=1200, plays=5000, popularity=95, themes="mateIn1 mate short opening", fen=FORK, moves="a2a3 h5f7"):
    return [pid, fen, moves, rating, 75, popularity, plays, themes, "", ""]


def test_selection_is_by_motif_band_and_quality(tmp_path):
    fen = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPPKPPP/RNB3NR b kq - 5 4"  # the opponent moves first, then Qxf7#
    rows = [row(f"A{i:03}", fen=fen, moves="a7a6 h5f7", rating=900 + 100 * (i % 12), popularity=99 - i % 10) for i in range(60)]
    rows.append(row("LOWQ", fen=fen, moves="a7a6 h5f7", plays=10))  # too few plays: never chosen
    out = tmp_path / "starter.sppack"
    manifest = starter.build(sample(tmp_path, rows), out=out, per_band=2, version=1)
    records = [json.loads(line) for line in zipfile.ZipFile(out).read("positions.jsonl").decode().splitlines()]
    assert manifest["puzzles"] == len(records) == 8  # mate-in-1: 2 per band in 4 bands; each puzzle once
    assert all(r["ref"] != "LOWQ" for r in records)
    first = records[0]
    assert first["tags"][:3] == ["opening", "mate-in-1"] or "mate-in-1" in first["tags"]
    assert first["puzzles"] == [{"start": "0", "active": True, "ends": ["0.0"]}]
    assert first["moves"].startswith("4... a6 5. Qxf7#")
    import time

    time.sleep(1.1)  # another second: the zip's own times must not change the bytes
    assert starter.build(sample(tmp_path, rows), out=tmp_path / "again.sppack", per_band=2, version=1)["puzzles"] == 8
    assert (tmp_path / "again.sppack").read_bytes() == out.read_bytes()  # the same file gives the same pack


def test_themes_map_to_tags_we_have():
    assert not (set(starter.THEMES.values()) | set(starter.MOTIFS)) - packs.builtin_tags()
    assert starter.tags_of(["fork", "crushing", "middlegame"]) == ["fork", "middlegame", "winning-continuation"]
    assert starter.difficulty(950) == 1 and starter.difficulty(1950) == 5


@pytest.mark.django_db
def test_the_shipped_pack_imports_and_trains(client):
    data = starter.PATH.read_bytes()
    manifest = json.loads(zipfile.ZipFile(io.BytesIO(data)).read("manifest.json"))
    assert manifest["puzzles"] >= 500 and "CC0" in manifest["licence"]
    preview = client.post("/packs/starter/").json()
    assert preview["ok"] and preview["counts"]["new"] == manifest["positions"] and not preview["unknown_tags"]
    result = client.post("/packs/run/", data=json.dumps({"token": preview["token"], "ready": True}), content_type="application/json").json()
    assert result["ok"], result
    assert Puzzle.objects.filter(active=True).count() == manifest["puzzles"]
    assert all(z.cards.exists() for z in Puzzle.objects.all()[:50])
    again = packs.scan(data)  # loading it again changes nothing (the same version)
    assert again["counts"]["new"] == 0
