"""The library on the server (spec 11): the starter vocabulary, positions' derived fields, bulk commands and their
undo, Collect's saving with duplicates, PGN import and export, and upgrading untouched default layouts."""

import json

import pytest

from spaced_positions.analysis import puzzles as analysis_puzzles
from spaced_positions.analysis import pgn as pgn_io
from spaced_positions.analysis import tree
from spaced_positions.core import layouts
from spaced_positions.library import importer, vocabulary
from spaced_positions.library.models import Game, Player, PositionTag, SavedQuery, Tag, TagField, TagPreset
from spaced_positions.training.models import Attempt, Position, Puzzle
from tests.factories import back_rank

pytestmark = pytest.mark.django_db

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def post(client, url, body=None):
    return client.post(url, json.dumps(body or {}), content_type="application/json")


def cmd(client, cid, args=(), **body):
    return post(client, f"/cmd/{cid}/", {"args": list(args), "context": {}, **body})


# ── Vocabulary and positions ──────────────────────────────────────────────────────────────────────────────────


def test_starter_vocabulary_is_loaded_once():
    assert TagField.objects.count() == 10 and Tag.objects.count() == 205
    fork = Tag.objects.get(key="knight-fork")
    assert (fork.name, fork.parent.name, fork.parent.parent.name) == ("Springergabel", "Gabel", "Doppelangriff")
    assert vocabulary.load(TagField, Tag) == 0  # nothing new the second time


def test_position_derives_side_material_difficulty_and_task():
    p = Position.objects.create(fen="8/8/4k3/8/8/4K3/4R3/4r3 b - - 0 1", canonical="x")
    assert (p.side, p.material, p.pieces) == ("b", "KRvKR", 4)
    p.difficulty_auto = 2
    p.save(update_fields=["difficulty_auto"])
    p.refresh_from_db()
    assert p.difficulty == 2
    p.difficulty_override = 5
    p.save()
    assert p.difficulty == 5
    PositionTag.objects.create(position=p, tag=Tag.objects.get(key="mate-in-2"))
    assert p.task == "Black to play and mate in 2" and p.task_for("w") == "White to play and mate in 2"
    p.objective = "Hold the draw"
    assert p.task == "Hold the draw"


# ── Bulk commands ─────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def two():
    return [tree.create_position(back_rank(i), ["d1d8"], title=f"Mate {i}") for i in range(2)]


def test_tag_single_field_replaces_and_undo_restores_exactly(client, two):
    a, b = two
    opening, middlegame = Tag.objects.get(key="opening"), Tag.objects.get(key="middlegame")
    PositionTag.objects.create(position=a, tag=opening, origin="auto")
    result = cmd(client, "library.tag", ["mittelspiel"], c="positions", ids=[a.short_id, b.short_id]).json()
    assert result["ok"] and result["message"] == "Tagged 2 items Mittelspiel"
    assert set(a.tags.all()) == {middlegame}  # phase is a single field: Opening went
    undo = result["undo"]
    assert cmd(client, undo["command"], undo["args"]).json()["ok"]
    assert list(a.tag_links.values_list("tag__key", "origin")) == [("opening", "auto")] and not b.tags.exists()
    redo = result["redo"]
    cmd(client, redo["command"], redo["args"])
    assert set(b.tags.all()) == {middlegame}
    untag = cmd(client, "library.untag", ["middlegame"], c="positions", ids=[b.short_id]).json()
    assert untag["message"] == "Removed Mittelspiel from 1 item" and not b.tags.exists()
    assert not cmd(client, "library.tag", ["nonsense"], c="positions", ids=[a.short_id]).json()["ok"]


def test_move_tags_and_puzzles_as_targets(client, two):
    a = two[0]
    node = a.nodes.get(san="Rd8#")
    assert cmd(client, "library.tag", ["zwischenzug"], c="nodes", ids=[f"n{node.id}"]).json()["ok"]
    assert node.tags.get().key == "zwischenzug"
    analysis_puzzles.act(tree.root(a), "start")
    puzzle = a.puzzles.get()
    assert cmd(client, "library.tag", ["opfer"], c="puzzles", ids=[f"z{puzzle.pk}"]).json()["ok"]
    assert a.tags.get().key == "sacrifice"  # a puzzle's tags are its position's


def test_trash_restore_empty_keeps_trained(client, two):
    a, b = two
    result = cmd(client, "library.trash", c="positions", ids=[a.short_id, b.short_id]).json()
    assert result["message"].startswith("Moved 2 to the trash") and Position.alive.count() == 0
    cmd(client, result["undo"]["command"], result["undo"]["args"])
    assert Position.alive.count() == 2
    cmd(client, "library.trash", c="positions", ids=[a.short_id, b.short_id])
    analysis_puzzles.act(tree.root(a), "start")
    analysis_puzzles.act(tree.root(a), "ready")
    analysis_puzzles.rebuild_all(a)
    Attempt.objects.create(card=a.puzzles.get().cards.get(), success=True)
    message = cmd(client, "library.emptytrash").json()["message"]
    assert message == "Trash emptied: 1 positions and 0 games deleted for good; 1 with training history stay in the trash"
    assert list(Position.objects.values_list("pk", flat=True)) == [a.pk]


def test_saved_queries_cards_subject_fens_and_export(client, two):
    assert cmd(client, "library.savequery", ["Back", "rank"], q="mate", c="positions").json()["ok"]
    assert SavedQuery.objects.get().key == "back-rank"
    for p in two:
        analysis_puzzles.act(tree.root(p), "start")
        analysis_puzzles.act(tree.root(p), "ready")
        analysis_puzzles.rebuild_all(p)
    cards = post(client, "/lib/cards/", {"c": "positions", "q": "in:q:back-rank"}).json()["cards"]
    assert len(cards) == 2
    subject = client.get("/lib/subject/", {"c": "positions", "ids": two[1].short_id}).json()["ids"]
    assert subject == [str(two[1].uuid)]
    fens = client.get("/lib/fens/", {"c": "positions", "q": "sort:title"}).json()["fens"]
    assert fens == [back_rank(0), back_rank(1)]
    exported = client.get("/lib/export/", {"c": "positions", "ids": two[0].short_id})
    assert exported["Content-Disposition"].startswith("attachment") and "1. Rd8#" in exported.content.decode()


def test_results_completion_and_facets(client, two):
    html = client.get("/lib/results/", {"q": "mate sort:title", "c": "positions", "display": "list"}).content.decode()
    assert html.count('data-row="p') == 2 and "library__row--list" in html and "miniboard" in html
    comp = client.get("/lib/complete/", {"q": "motif:gab", "at": 9, "c": "positions"}).json()
    assert comp["items"][0]["value"] == "motif:fork" and comp["start"] == 0
    keys = client.get("/lib/complete/", {"q": "di", "c": "positions"}).json()["items"]
    assert keys[0]["value"] == "diff:"
    exact = client.get("/lib/complete/", {"kind": "tag", "q": "opfer"}).json()["items"]
    assert exact[0]["value"] == "sacrifice"  # the exact name before tags that only contain it
    PositionTag.objects.create(position=two[0], tag=Tag.objects.get(key="pin"))
    facets = client.get("/lib/facets/", {"q": ""}).content.decode()
    assert 'data-term="motif:pin"' in facets and "2 positions" in facets


# ── Collect ───────────────────────────────────────────────────────────────────────────────────────────────────


def test_collect_save_duplicate_merge_and_diagram(client):
    source = post(client, "/lib/sources/new/", {"title": "Polgár 5334"}).json()
    body = {"start": back_rank(0), "moves": [], "title": "Nr. 1", "source": source["id"], "page": "41", "ref": "1",
            "tags": ["back-rank-mate"], "ready": True}
    saved = post(client, "/lib/collect/save/", body).json()
    assert saved["ok"] and saved["message"].startswith("Saved p")
    p = Position.objects.get()
    assert (p.title, p.source.title, p.source_page, p.source_ref) == ("Nr. 1", "Polgár 5334", "41", "1")
    assert p.tag_links.get(tag__key="back-rank-mate").origin == "manual"
    assert p.tag_links.get(tag__key="endgame").origin == "auto"  # detected (library/detect.py)
    assert p.tag_links.get(tag__key="mate-in-1").origin == "auto"  # the mate search found Rd8#
    again = post(client, "/lib/collect/save/", body | {"moves": ["d1d8"]}).json()
    assert not again["ok"] and again["duplicate"]["short"] == p.short_id
    merged = post(client, "/lib/collect/save/", body | {"moves": ["d1d8"], "how": "merge"}).json()
    assert merged["message"] == f"Merged into {p.short_id} · puzzle in training"
    assert Position.objects.count() == 1 and Puzzle.objects.get(position=p).active
    assert not post(client, "/lib/collect/save/", {"start": "8/8/8/8/8/8/8/KK5k w - - 0 1"}).json()["ok"]  # D first
    illegal = {"start": "8/8/8/8/8/8/8/KK5k w - - 0 1", "diagram": True}
    assert post(client, "/lib/collect/save/", illegal).json()["ok"]
    assert Position.objects.get(diagram=True).fen.startswith("8/8/8/8/8/8/8/KK5k")


def test_collect_many_and_presets(client):
    many = post(client, "/lib/collect/many/", {"fens": [back_rank(0), back_rank(1), back_rank(0), "nonsense"], "tags": ["pin"]}).json()
    assert many["message"] == "Saved 2 positions · 1 already in the library · 1 not legal"
    assert PositionTag.objects.filter(tag__key="pin").count() == 2
    preset = post(client, "/lib/presets/", {"name": "Mates", "tags": ["mate-in-1", "back-rank-mate"]}).json()
    assert preset["ok"] and preset["presets"][0]["keys"] == "mate-in-1,back-rank-mate"
    assert TagPreset.objects.get().tags.count() == 2


# ── Import and export ─────────────────────────────────────────────────────────────────────────────────────────

PGN = """[Event "Club"]
[White "Tal, M."]
[Black "Smith"]
[Result "1-0"]
[Date "1960.05.01"]
[WhiteElo "2600"]
[Opening "Sicilian"]

1. e4 {Best by test} e5 (1... c5 2. Nf3 $1) 2. Nf3 { [%cal Gg1f3] } Nc6 1-0

[FEN "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1"]
[SetUp "1"]

1. Rd8# *
"""


def test_import_scan_run_players_and_duplicates():
    tal = Player.objects.create(key="tal", name="Tal, Mikhail")
    items = importer.scan(PGN)
    assert [(i["kind"], i["title"], i["plies"], i["duplicate"]) for i in items] == [
        ("game", "Tal, M. – Smith 1-0 1960", 4, None), ("puzzle", "Puzzle", 1, None)]
    result = importer.run(PGN, None, ready=True)
    game = result["games"][0]
    assert (game.white, game.black, game.white_elo, game.year, game.headers) == (tal, None, 2600, 1960, {"Opening": "Sicilian"})
    c5 = game.nodes.get(san="c5")
    assert c5.kids.get().nags == [1] and game.nodes.get(san="e4").comment == "Best by test"
    assert game.nodes.get(san="Nf3", parent__san="e5").shapes == [{"orig": "g1", "dest": "f3", "brush": "green"}]
    puzzle = Puzzle.objects.get()
    assert puzzle.active and puzzle.start_node.position.title == "Puzzle"
    assert [i["duplicate"] for i in importer.scan(PGN)] == [game.short_id, puzzle.position.short_id]


def test_import_endpoints_and_undo(client):
    scan = post(client, "/lib/import/scan/", {"text": PGN}).json()
    assert scan["ok"] and len(scan["items"]) == 2
    run = post(client, "/lib/import/run/", {"text": PGN, "selected": [0]}).json()
    assert run["message"] == "Imported 1 game" and run["added"]["positions"] == []
    undo = cmd(client, run["undo"]["command"], run["undo"]["args"]).json()
    assert undo["message"] == "Moved to the trash: 1 imported" and Game.objects.get().deleted_at
    assert not post(client, "/lib/import/scan/", {"text": "no games here"}).json()["ok"]


def test_export_keeps_variations_comments_and_drawings():
    p = tree.create_position(START, ["e2e4", "e7e5"], title="Open")
    e4 = p.nodes.get(san="e4")
    tree.play(e4, "c7c5")
    tree.edit(e4, {"comment": "Best", "nags": [1], "shapes": [{"orig": "e2", "dest": "e4", "brush": "red"}]})
    text = pgn_io.export_position(p)
    assert '[Event "Open"]' in text and "1. e4 $1 { [%cal Re2e4] Best } 1... e5 ( 1... c5 ) *" in text
    game = next(pgn_io.read_games(text))
    assert pgn_io.shapes_of(game.next()) == ([{"orig": "e2", "dest": "e4", "brush": "red"}], {})


# ── Layouts ───────────────────────────────────────────────────────────────────────────────────────────────────


def test_untouched_old_default_layouts_are_upgraded(client):
    from spaced_positions.core.models import UIState

    old = json.loads(json.dumps(layouts.OLD_DEFAULTS["library"][0]))
    layouts.number_panes(old, assign_ids=True)
    UIState.objects.create(mode="library", layout=old)
    html = client.get("/m/library/").content.decode()
    assert 'data-view="library"' in html and 'data-view="demo"' not in html
    changed = json.loads(json.dumps(old))
    changed["sizes"] = [30, 40, 30]
    UIState.objects.filter(mode="library").update(layout=changed)
    assert 'data-view="demo"' in client.get("/m/library/").content.decode()  # changed by the user: kept
