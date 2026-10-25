"""On the server: metrics (stages, mastery, streaks, records, milestones), achievements, the Stats sections and
Home, tag detection with its storage rules, automatic difficulty, engine evaluations and the weakest-motifs session."""

import json
from datetime import date, timedelta

import chess
import pytest
from django.utils import timezone

from spaced_positions.analysis import puzzles as analysis_puzzles
from spaced_positions.analysis import tree
from spaced_positions.library import detect
from spaced_positions.library.models import PositionTag, Tag, TagDismissal
from spaced_positions.stats import metrics
from spaced_positions.stats.models import Achievement
from spaced_positions.training.models import Attempt, Session
from tests.factories import back_rank

pytestmark = pytest.mark.django_db

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def post(client, url, body=None):
    return client.post(url, json.dumps(body or {}), content_type="application/json")


def trained(i=0, tag="back-rank-mate"):
    """A back-rank puzzle in training, tagged."""
    p = tree.create_position(back_rank(i), ["d1d8"], title=f"Mate {i}")
    PositionTag.objects.create(position=p, tag=Tag.objects.get(key=tag))
    root = tree.root(p)
    analysis_puzzles.act(root, "start")
    analysis_puzzles.act(root, "ready")
    analysis_puzzles.rebuild_all(p)
    return p.puzzles.get().cards.get()


# ── Metrics ───────────────────────────────────────────────────────────────────────────────────────────────────


def test_mastery_ladder_and_streaks():
    assert metrics.mastery(0, None)["name"] == "Learning"
    assert metrics.mastery(1, None)["name"] == "Familiar"
    assert metrics.mastery(5, 0.8, proven=False)["name"] == "Familiar"  # retention not proven yet
    assert metrics.mastery(5, 0.8)["name"] == "Solid"
    assert metrics.mastery(16, 0.82)["name"] == "Strong" and metrics.mastery(16, 0.82)["next"] == "Expert: 24 more established cards and retention 85%"
    today = date(2026, 10, 24)
    days = {today - timedelta(days=i) for i in (1, 2, 3, 7, 8)}
    assert metrics.streaks(days, today) == (3, 3)  # yesterday counts while today is still open
    assert metrics.streaks(days | {today}, today) == (4, 4)


def test_library_stages_retention_tags_and_weak_spots():
    card = trained(0)
    other = trained(1, tag="smothered-mate")
    now = timezone.now()
    card.state, card.interval_days = "review", 30
    card.save()
    for i, ok in enumerate([True, False, False, False]):
        Attempt.objects.create(card=other, success=ok, at=now - timedelta(days=i), counted=True, state_before="review", interval_before=5)
    d = metrics.load()
    lib = metrics.library(d)
    assert lib["size"] == 1 and lib["counts"] == {"mature": 1, "new": 1} and lib["next"] == 25
    ret = metrics.retention(d)
    assert ret["all"] == {"n": 4, "ok": 1, "rate": 0.25}
    rows = {r["tag"].key: r for r in metrics.tag_rows(d)}
    assert rows["back-rank-mate"]["established"] == 1.0 and rows["back-rank-mate"]["mastery"] == metrics.not_started()
    assert [r["tag"].key for r in metrics.weakest(list(rows.values()))] == ["smothered-mate"]
    assert metrics.consistency(d)["current"] == 4


def test_achievements_first_run_records_and_session(client):
    for i in range(2):
        trained(i)
    sessions = []
    for solved in (12, 25):
        s = Session.objects.create(mode="storm", options={"minutes": 3}, solved=solved, ended_at=timezone.now())
        sessions.append(s)
    made = metrics.sync_achievements()
    labels = {a.label: a.seen for a in made}
    # the first run logs the history as seen, except the latest (the higher value of one session): announced
    assert labels == {"▲ new best Storm 3′: 12": True, "▲ new best Storm 3′: 25": False, "20 puzzles in one Storm": True}
    assert metrics.sync_achievements() == []  # logged once
    # a session that ends: what it reached belongs to it and shows on its result
    s = Session.objects.create(mode="storm", options={"minutes": 3}, solved=31, ended_at=None)
    post(client, f"/train/r/{s.uuid}/end/", {"best_combo": 3})
    s.refresh_from_db()
    assert sorted(a.label for a in s.achievements.all()) == ["30 puzzles in one Storm", "▲ new best Storm 3′: 31"]
    html = client.get(f"/train/r/{s.uuid}/result/").content.decode()
    assert "▲ new best Storm 3′: 31" in html
    seen = post(client, "/stats/seen/").json()["achievements"]
    assert [a["label"] for a in seen] == ["▲ new best Storm 3′: 25"]  # the one not announced yet
    assert not Achievement.objects.filter(seen=False).exists()


def test_stats_sections_and_home(client):
    trained(0)
    html = client.get("/stats/sections/", {"period": "30d"}).content.decode()
    for key in "olcrmwbakt":
        assert f'data-section-key="{key}"' in html
    assert 'data-chart="library"' in html and 'data-chart="calendar"' in html and 'aria-checked="true" data-cmd="stats.period" data-args="30d"' in html
    home = client.get("/m/home/").content.decode()
    assert 'data-view="today"' in home and 'data-view="continue"' in home and "Pattern library" in home


# ── Detection ─────────────────────────────────────────────────────────────────────────────────────────────────


def test_detect_mate_patterns_motifs_and_static_features():
    mate = tree.create_position(back_rank(0), ["d1d8"])
    found = {f.tag: f for f in detect.detect(mate)}
    assert found["mate-in-1"].apply and found["back-rank-mate"].evidence == "Mating pattern after 1.Rd8#"
    assert found["endgame"].apply and found["rook-vs-pawns"].apply
    search = tree.create_position(back_rank(1), [])
    assert {f.tag for f in detect.detect(search)} >= {"mate-in-1", "back-rank-mate"}  # no solution yet: the mate search


def test_knight_fork_is_found_and_confirmed():
    board = chess.Board("4k3/8/8/3q4/8/8/8/1N2K3 w - - 0 1")
    moves = [chess.Move.from_uci(u) for u in ("b1c3", "d5c4", "c3e2")]  # no fork
    assert "knight-fork" not in {f.tag for f in detect.solution_features(board, moves)}
    board = chess.Board("2q1k3/8/8/8/8/8/3N4/4K3 w - - 0 1")
    moves = [chess.Move.from_uci(u) for u in ("d2c4", "e8f7", "c4d6", "f7e7", "d6c8")]  # Nd6+ forks king and queen, Nxc8
    found = {f.tag: f for f in detect.solution_features(board, moves)}
    assert found["family-fork"].apply and found["family-fork"].evidence == "Fork with 2.Nd6+"


def test_store_respects_the_user_and_withdraws_its_own():
    p = tree.create_position(back_rank(0), ["d1d8"])
    result = detect.run(p)
    assert "Grundreihenmatt" in result["added"] and "Endspiel" in result["added"]
    assert p.tag_links.get(tag__key="back-rank-mate").detector == "pychess"
    # the user removes a detected tag: it is not detected again
    TagDismissal.objects.create(position=p, tag=Tag.objects.get(key="back-rank-mate"))
    p.tag_links.filter(tag__key="back-rank-mate").delete()
    detect.run(p)
    assert not p.tag_links.filter(tag__key="back-rank-mate").exists()
    # a manual tag is never touched; a detected tag that no longer applies is withdrawn
    link = p.tag_links.get(tag__key="mate-in-1")
    link.origin = "manual"
    link.save()
    tree.delete(p.nodes.get(san="Rd8#"))
    result = detect.run(p, search=False)
    assert p.tag_links.get(tag__key="mate-in-1").origin == "manual"
    assert "Matt in 1" not in result["withdrawn"]


def test_auto_difficulty_from_tag_weights():
    p = tree.create_position(back_rank(0), ["d1d8"])
    assert detect.auto_difficulty(p) is None
    PositionTag.objects.create(position=p, tag=Tag.objects.get(key="mate-in-1"))  # base 1
    assert detect.auto_difficulty(p) == 1
    PositionTag.objects.create(position=p, tag=Tag.objects.get(key="mate-in-3"))  # base 3: the weighted mean is 2
    detect.refresh_difficulty(p)
    p.refresh_from_db()
    assert (p.difficulty_auto, p.difficulty) == (2, 2)
    p.difficulty_override = 5
    p.save()
    assert p.difficulty == 5


def test_detect_command_untag_dismisses_and_undo_is_quiet(client):
    p = tree.create_position(back_rank(0), ["d1d8"])
    result = post(client, "/cmd/library.detect/", {"args": [], "context": {}, "c": "positions", "ids": [p.short_id]}).json()
    assert result["ok"] and result["message"].startswith("Detected on 1 position:")
    untag = post(client, "/cmd/library.untag/", {"args": ["back-rank-mate"], "context": {}, "c": "positions", "ids": [p.short_id]}).json()
    assert TagDismissal.objects.filter(position=p, tag__key="back-rank-mate").exists()
    undo = untag["undo"]
    post(client, f"/cmd/{undo['command']}/", {"args": undo["args"], "context": {}})
    assert p.tag_links.filter(tag__key="back-rank-mate").exists() and not TagDismissal.objects.exists()
    tagged = post(client, "/cmd/library.tag/", {"args": ["opfer"], "context": {}, "c": "positions", "ids": [p.short_id]}).json()
    post(client, f"/cmd/{tagged['undo']['command']}/", {"args": tagged["undo"]["args"], "context": {}})
    assert not TagDismissal.objects.exists()  # undoing a tag isn't dismissing it


# ── Evaluations, weakest motifs ───────────────────────────────────────────────────────────────────────────────


def test_evals_are_stored_and_sent_with_the_tree(client):
    p = tree.create_position(START, ["e2e4", "e7e5"])
    e4 = p.nodes.get(san="e4")
    data = post(client, f"/analysis/{p.uuid}/evals/", {"evals": {str(e4.id): {"cp": 34, "depth": 14}, "999999": {"cp": 1}}}).json()
    assert data["message"] == "Evaluated 1 move" and data["journal"] is None
    node = next(n for n in data["tree"]["nodes"] if n["id"] == e4.id)
    assert node["eval"] == {"cp": 34, "mate": None, "depth": 14}


def test_streak_on_the_weakest_motifs(client):
    assert not post(client, "/train/start/", {"mode": "streak", "weakest": True}).json()["ok"]
    weak = trained(0, tag="smothered-mate")
    trained(1, tag="back-rank-mate")
    for ok in (False, False, True):
        Attempt.objects.create(card=weak, success=ok)
    data = post(client, "/train/start/", {"mode": "streak", "weakest": True}).json()
    assert data["ok"] and data["total"] == 1 and data["label"] == "Streak · weakest motifs"
    assert data["options"]["filter"] == "tag:smothered-mate"


def test_structure_suggestions():
    """The structure detector (pawns, rooks, batteries, endgame set-ups) as suggestions."""
    from spaced_positions.library import structure

    def keys(fen, ph="middlegame"):
        return {f.tag: f for f in structure.static_features(chess.Board(fen), ph)}

    found = keys("r3k2r/pp3ppp/8/3p4/8/8/PP3PPP/R2Q1RK1 w kq - 0 1")
    assert found["isolated-pawn"].evidence == "Isolated pawn on the d-file (Black)" and not found["isolated-pawn"].apply
    assert keys("6k1/5ppp/8/8/8/3B4/2Q2PPP/6K1 w - - 0 1")["battery"].evidence == "Battery of queen and bishop against h7 (White)"
    wrong = keys("7k/8/8/8/8/8/P7/2B3K1 w - - 0 1", "endgame")["wrong-rook-pawn"]
    assert wrong.apply and "a8" in wrong.evidence
    assert "opposition" in keys("8/8/4k3/8/4K3/4P3/8/8 w - - 0 1", "endgame")
    p = tree.create_position("r3k2r/pp3ppp/8/3p4/8/8/PP3PPP/R2Q1RK1 w kq - 0 1", [])
    detect.run(p, search=False)
    assert p.tag_links.get(tag__key="isolated-pawn").origin == "suggested"
