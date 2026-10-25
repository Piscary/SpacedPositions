"""Phase 7: the migration from chess-study-manager (spaced_positions/csm.py), on a small database with the old
schema (tests/data/csm_schema.sql): everything arrives, a second run adds only what is new, and what the user did
here (training, removed tags, edits of an analysis) is never undone."""

import json
import sqlite3
from datetime import timedelta
from pathlib import Path

import chess
import pytest
from django.utils import timezone

from spaced_positions import csm
from spaced_positions.library.models import Game, NodeTag, Player, PositionTag, Source, Tag, TagDismissal
from spaced_positions.stats.models import ActivityLog
from spaced_positions.training.models import Attempt, Card, Position, Session
from tests.factories import back_rank

pytestmark = pytest.mark.django_db

SCHEMA = Path(__file__).parent / "data" / "csm_schema.sql"
START = chess.STARTING_FEN


JSON_COLUMNS = {"aliases": "[]", "nags": "[]", "options": "{}", "shapes": "{}", "extra_headers": "{}", "solution": "{}"}


class Old:
    """A chess-study-manager database to fill row by row (NOT NULL columns get empty values)."""

    def __init__(self, path):
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA.read_text())

    def add(self, table, **values):
        for _, name, kind, notnull, _, _ in self.db.execute(f'pragma table_info("{table}")'):
            if name in JSON_COLUMNS and name not in values:
                values[name] = JSON_COLUMNS[name]
            elif notnull and name not in values and name != "id":
                values[name] = 0 if any(t in kind.lower() for t in ("int", "bool", "real", "smallint")) else ""
        cols = ", ".join(f'"{c}"' for c in values)
        self.db.execute(f'insert into "{table}" ({cols}) values ({", ".join("?" * len(values))})', list(values.values()))
        self.db.commit()

    def move(self, nid, parent, fen, uci, **owner):
        board = chess.Board(fen)
        move = chess.Move.from_uci(uci)
        san = board.san(move)
        board.push(move)
        self.add("positions_variationnode", id=nid, parent_id=parent, uci=uci, san=san, ply=board.ply(), fen_before=fen,
                 fen_after=board.fen(), nags="[]", shapes='{"arrows": [{"from": "d1", "to": "d8", "color": "G"}]}', sort_order=0, **owner)
        return board.fen()


@pytest.fixture
def old(tmp_path):
    o = Old(tmp_path / "db.sqlite3")
    o.add("sources_book", id=1, title="Test Book", authors="A. Author", year=1999, created_at="2026-01-01 10:00:00", updated_at="2026-01-01 10:00:00")
    o.add("positions_player", id=1, name="Mikhail Tal", aliases='["Tal, M."]', role="model", created_at="2026-01-01 10:00:00")
    o.add("positions_tagfield", id=1, key="mate", name="Matt")
    for tid, slug in ((1, "back-rank-mate"), (2, "mate-in-1"), (3, "fork"), (4, "an-old-tag")):
        o.add("positions_tag", id=tid, slug=slug, name=slug, field_id=1)
    # a game with two moves
    o.add("positions_game", id=1, white="Mikhail Tal", black="Someone", white_player_id=1, date="1960.??.??", result="1-0",
          start_fen=START, extra_headers="{}", created_at="2026-02-01 10:00:00", updated_at="2026-02-01 10:00:00")
    o.add("positions_variationnode", id=100, game_id=1, parent_id=None, ply=0, fen_before=START, fen_after=START, nags="[]", shapes="{}", sort_order=0)
    after = o.move(101, 100, START, "e2e4", game_id=1)
    o.move(102, 101, after, "e7e5", game_id=1)
    # a puzzle position with its solution, and a diagram from the game
    fen = back_rank(0)
    o.add("positions_position", id=1, fen=fen, canonical_fen=fen, title="Back rank", book_id=1, source_page="12", source_ref="7", description="White to move",
          created_at="2026-03-01 10:00:00", updated_at="2026-03-01 10:00:00", has_solution=1, diagram=0)
    o.add("positions_variationnode", id=200, position_id=1, parent_id=None, ply=0, fen_before=fen, fen_after=fen, nags="[]", shapes="{}", sort_order=0)
    o.move(201, 200, fen, "d1d8", position_id=1)
    o.add("positions_position", id=2, fen=after, canonical_fen=after, title="From the game", game_id=1, game_ply=1, diagram=1,
          created_at="2026-03-02 10:00:00", updated_at="2026-03-02 10:00:00", has_solution=0)
    o.add("positions_variationnode", id=300, position_id=2, parent_id=None, ply=0, fen_before=after, fen_after=after, nags="[]", shapes="{}", sort_order=0)
    # tags: detected, unknown, suggested, dismissed, a move tag
    o.add("positions_positiontag", position_id=1, tag_id=1, source="auto", detector="pychess.mates", evidence="Rd8#", created_at="2026-03-01 10:00:00")
    o.add("positions_positiontag", position_id=1, tag_id=4, source="manual", created_at="2026-03-01 10:00:00")
    o.add("positions_tagsuggestion", position_id=1, tag_id=3, status="open", evidence="maybe", created_at="2026-03-01 10:00:00")
    o.add("positions_tagsuggestion", position_id=2, tag_id=2, status="dismissed", created_at="2026-03-01 10:00:00")
    o.add("positions_nodetag", node_id=201, tag_id=2, source="auto", detector="pychess", evidence="mates", created_at="2026-03-01 10:00:00")
    # a board with a column: not migrated (the filters do that job here)
    o.add("boards_board", id=1, name="My Board", created_at="2026-03-01 10:00:00", updated_at="2026-03-01 10:00:00")
    o.add("boards_column", id=1, name="Inbox", board_id=1)
    o.add("boards_positioninboard", position_id=1, board_id=1, column_id=1, added_at="2026-03-01 10:00:00")
    # training: the puzzle, its card, a Storm with two attempts
    o.add("training_trainingpuzzle", id=1, node_id=200, active=1, solution=json.dumps({"ends": [201], "also": [], "replies": []}),
          created_at="2026-03-01 10:00:00")
    o.add("training_trainingcard", id=1, puzzle_id=1, line="", in_solution=1, state="review", due="2026-04-01 10:00:00", interval_days=10,
          ease=2.5, reps=2, attempts=2, successes=2, last_seen="2026-03-20 10:00:00", created_at="2026-03-01 10:00:00")
    o.add("training_trainingsession", id=1, mode="storm", minutes=3, options="{}", started_at="2026-03-20 09:55:00",
          ended_at="2026-03-20 10:00:00", solved=2, failed=0)
    for aid, at in ((1, "2026-03-10 10:00:00"), (2, "2026-03-20 10:00:00")):
        o.add("training_trainingattempt", id=aid, card_id=1, session_id=1, at=at, success=1, ms=4000 + aid, mode="storm", visual="normal",
              counted=1, state_before="review", interval_after=10)
    o.add("core_activityevent", kind="analysis", points=1, created_at="2026-03-01 11:00:00", label="Rd8#")
    o.add("core_activityevent", kind="publish", points=3, created_at="2026-03-01 11:00:00")  # out of scope
    return o


def test_everything_arrives(old):
    report = csm.run(old.path, make_backup=False)
    assert report.counts["positions"] == 2 and report.counts["games"] == 1 and report.counts["attempts"] == 2
    p = Position.objects.get(origin="csm-position:1")
    assert (p.title, p.description, p.source.title, p.source.authors, p.source_page, p.source_ref) == ("Back rank", "White to move", "Test Book", "A. Author", "12", "Nr. 7")
    assert p.created_at.date().isoformat() == "2026-03-01"
    rd8 = p.nodes.get(san="Rd8#")
    assert rd8.shapes == [{"orig": "d1", "dest": "d8", "brush": "green"}]
    assert {(link.tag.key, link.origin) for link in p.tag_links.all()} == {("back-rank-mate", "auto"), ("fork", "suggested")}
    assert p.tag_links.get(tag__key="back-rank-mate").evidence == "Rd8#"
    assert not Tag.objects.filter(key__startswith="board-").exists()
    assert NodeTag.objects.get(node=rd8).tag.key == "mate-in-1"
    assert TagDismissal.objects.filter(position__origin="csm-position:2", tag__key="mate-in-1").exists()
    assert "1 position tags with the unknown tag 'an-old-tag' left out" in report.problems
    game = Game.objects.get()
    assert (game.white, game.year, [n.san for n in game.nodes.exclude(parent=None).order_by("ply")]) == (Player.objects.get(key="mikhail-tal"), 1960, ["e4", "e5"])
    diagram = Position.objects.get(origin="csm-position:2")
    assert diagram.diagram and diagram.game == game and diagram.game_node.san == "e4"
    card = Card.objects.get(puzzle__origin="csm:1")
    assert (card.state, card.interval_days, card.attempts, card.successes, card.best_ms) == ("review", 10, 2, 2, 4001)
    session = Session.objects.get(origin="csm-session:1")
    assert session.options["minutes"] == 3 and session.attempts.count() == 2
    assert list(ActivityLog.objects.values_list("kind", "points")) == [("analyse", 1)]


def test_again_adds_only_what_is_new(old):
    csm.run(old.path, make_backup=False)
    assert csm.run(old.path, make_backup=False).lines() == []
    old.add("training_trainingattempt", id=3, card_id=1, session_id=None, at="2026-03-25 10:00:00", success=0, ms=9000, mode="custom",
            visual="normal", counted=1, state_before="review", interval_after=1)
    old.db.execute("update training_trainingcard set state='relearning', interval_days=1, last_seen='2026-03-25 10:00:00' where id=1")
    old.db.commit()
    report = csm.run(old.path, make_backup=False)
    assert +report.counts == {"attempts": 1, "cards rescheduled": 1}  # + drops the zeros
    card = Card.objects.get(puzzle__origin="csm:1")
    assert (card.state, card.attempts, card.successes, card.last_result) == ("relearning", 3, 2, False)


def test_what_was_done_here_stays(old):
    csm.run(old.path, make_backup=False)
    card = Card.objects.get(puzzle__origin="csm:1")
    # trained here later than in the old app: this schedule stays, the counters add up
    Attempt.objects.create(card=card, at=timezone.now(), success=True, ms=2000)
    card.state, card.interval_days, card.last_seen = "review", 25, timezone.now()
    card.save()
    # a tag removed here stays removed
    p = Position.objects.get(origin="csm-position:1")
    PositionTag.objects.filter(position=p, tag__key="back-rank-mate").delete()
    TagDismissal.objects.create(position=p, tag=Tag.objects.get(key="back-rank-mate"))
    old.add("training_trainingattempt", id=3, card_id=1, at="2026-03-25 10:00:00", success=1, ms=3000, mode="custom",
            visual="normal", counted=1, state_before="review", interval_after=12)
    csm.run(old.path, make_backup=False)
    card.refresh_from_db()
    assert (card.interval_days, card.attempts, card.best_ms) == (25, 4, 2000)
    assert not p.tag_links.filter(tag__key="back-rank-mate").exists()


def test_analysis_changed_here_keeps_its_moves(old, client):
    csm.run(old.path, make_backup=False)
    p = Position.objects.get(origin="csm-position:1")
    deleted = client.post(f"/analysis/{p.uuid}/delete/", json.dumps({"node": p.nodes.get(san="Rd8#").id}), content_type="application/json")
    assert deleted.json()["ok"]  # journaled: the analysis is the user's now
    old.move(202, 200, back_rank(0), "d1d7", position_id=1)
    csm.run(old.path, make_backup=False)
    assert not p.nodes.exclude(parent=None).exists()
    other = Position.objects.get(origin="csm-position:2")
    old.move(301, 300, other.fen, "g8f6", position_id=2)
    report = csm.run(old.path, make_backup=False)
    assert report.counts["moves"] == 1 and other.nodes.filter(san="Nf6").exists()  # untouched here: new old moves arrive


def test_sources_cited_by_phase_four_are_matched(old):
    cited = Source.objects.create(title="A. Author, Test Book")
    csm.run(old.path, make_backup=False)
    cited.refresh_from_db()
    assert (cited.title, cited.authors, cited.origin) == ("Test Book", "A. Author", "csm-book:1")
    assert Source.objects.count() == 1


def test_dry_run_changes_nothing_and_the_endpoint(old, client, settings):
    report = csm.run(old.path, dry_run=True)
    assert report.counts["positions"] == 2 and not Position.objects.exists() and not report.backup
    data = client.post("/settings/csm/", json.dumps({"path": str(old.path), "dry_run": True}), content_type="application/json").json()
    assert data["ok"] and data["message"].startswith("Would add: 1 sources, 1 players, 1 games")
    data = client.post("/settings/csm/", json.dumps({"path": str(old.path)}), content_type="application/json").json()
    assert data["ok"] and "backup in" in data["message"] and Position.objects.count() == 2
    assert list((Path(settings.DATA_DIR) / "backups").glob("db-before-csm-*.sqlite3.xz"))
    bad = client.post("/settings/csm/", json.dumps({"path": "/nowhere/db.sqlite3"}), content_type="application/json")
    assert bad.status_code == 422


def test_the_board_tags_of_an_earlier_import_are_removed():
    """Migration library 0007: only the tags the phase 7 import made of the old boards (and their links) go."""
    import importlib

    from django.apps import apps

    from spaced_positions.analysis import tree

    custom = Tag.objects.get(key="mate-in-1").field  # any field will do
    board = Tag.objects.create(key="board-my-board", name="My Board", field=custom, description="A board of chess-study-manager")
    column = Tag.objects.create(key="board-my-board-inbox", name="My Board · Inbox", field=custom, parent=board)
    mine = Tag.objects.create(key="board-games", name="Board games", field=custom)  # the user's own: stays
    p = tree.create_position(back_rank(0), ["d1d8"])
    PositionTag.objects.create(position=p, tag=column)
    PositionTag.objects.create(position=p, tag=mine)
    importlib.import_module("spaced_positions.library.migrations.0007_remove_board_tags").remove(apps, None)
    assert list(Tag.objects.filter(key__startswith="board-").values_list("key", flat=True)) == ["board-games"]
    assert list(p.tag_links.values_list("tag__key", flat=True)) == ["board-games"]
