"""Training: scheduler, solution trees, selection, the API and the import of old puzzles."""

import json
import sqlite3
from datetime import timedelta

import pytest
from django.utils import timezone

from spaced_positions.training import puzzles, selection, srs
from spaced_positions.training.models import Attempt, Card, Puzzle, Session
from tests.factories import back_rank, opening_line

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
MATE_IN_2 = "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1"  # 1.Rd8#


def post(client, url, body):
    return client.post(url, json.dumps(body), content_type="application/json")


# ── Scheduler ─────────────────────────────────────────────────────────────────────────────────────────────────


class FakeCard:
    def __init__(self, **kw):
        self.pk, self.state, self.due, self.interval_days, self.ease = 7, "new", timezone.now(), 0.0, 2.5
        self.step = self.reps = self.lapses = self.success_streak = 0
        self.attempts = self.successes = self.total_ms = 0
        self.best_ms = self.last_result = self.last_seen = self.introduced_at = None
        self.__dict__.update(kw)


def test_new_card_learns_then_graduates():
    card, now = FakeCard(), timezone.now()
    srs.review(card, True, now)
    assert card.state == "learning" and card.due == now + timedelta(days=1)
    srs.review(card, True, card.due)
    assert card.state == "review" and 2.8 < card.interval_days < 3.2


def test_lapse_and_relearn():
    now = timezone.now()
    card = FakeCard(state="review", interval_days=20.0, due=now, ease=2.5)
    out = srs.review(card, False, now)
    assert out.counted and card.state == "relearning" and card.lapses == 1
    assert card.ease == pytest.approx(2.3) and card.interval_days == pytest.approx(6.0)
    srs.review(card, True, card.due)
    assert card.state == "review" and card.interval_days == pytest.approx(6.0)


def test_early_solve_is_logged_but_not_counted():
    now = timezone.now()
    card = FakeCard(state="review", interval_days=10.0, due=now + timedelta(days=5))
    out = srs.record(card, True, 4000, now)
    assert not out.counted and card.interval_days == 10.0 and card.attempts == 1 and card.best_ms == 4000


def test_describe_due():
    now = timezone.now()
    assert srs.describe_due(now + timedelta(minutes=10), now) == "in 10 minutes"
    assert srs.describe_due(now + timedelta(days=1), now) == "tomorrow"
    assert srs.describe_due(now + timedelta(days=9), now) == "in 9 days"


# ── Solution trees ────────────────────────────────────────────────────────────────────────────────────────────


def test_tree_from_a_line_and_its_lines():
    tree = puzzles.from_line(["e2e4", "e7e5", "g1f3", "b8c6"])  # the trailing answer is dropped
    assert puzzles.lines(tree) == [["e2e4", "e7e5", "g1f3"]]
    puzzles.validate(START, tree)


def test_branching_answers_make_one_line_each():
    tree = {"moves": [{"uci": "e2e4", "replies": [
        {"uci": "e7e5", "next": {"moves": [{"uci": "g1f3", "replies": []}]}},
        {"uci": "c7c5", "next": {"moves": [{"uci": "g1f3", "replies": []}, {"uci": "b1c3", "replies": []}]}},
    ]}]}
    assert puzzles.lines(tree) == [["e2e4", "e7e5", "g1f3"], ["e2e4", "c7c5", "g1f3"]]


def test_validate_rejects_illegal_moves():
    with pytest.raises(ValueError):
        puzzles.validate(START, {"moves": [{"uci": "e2e5", "replies": []}]})


def test_mirror_and_first_move_only():
    tree = puzzles.from_line(["e2e4", "e7e5", "g1f3"])
    assert puzzles.lines(puzzles.mirror(tree)) == [["e7e5", "e2e4", "g8f6"]]
    assert puzzles.lines(puzzles.first_move_only(tree)) == [["e2e4"]]


@pytest.mark.django_db
def test_sync_cards_keeps_history_of_removed_lines():
    puzzle = puzzles.create_from_line(START, ["e2e4", "e7e5", "g1f3"])
    old = puzzle.cards.get()
    puzzle.solution = puzzles.from_line(["d2d4"])
    puzzle.save()
    puzzles.sync_cards(puzzle)
    old.refresh_from_db()
    assert not old.in_solution and puzzle.cards.filter(in_solution=True).count() == 1


@pytest.mark.django_db
def test_create_from_line_goes_through_the_analysis():
    a = puzzles.create_from_line(START, ["e2e4", "e7e5", "g1f3"])
    assert a.start_node == a.position.nodes.get(parent=None) and a.active
    assert [n.san for n in a.position.nodes.exclude(parent=None).order_by("ply")] == ["e4", "e5", "Nf3"]
    assert puzzles.create_from_line(START, ["e2e4", "e7e5", "g1f3"]).pk == a.pk  # the same puzzle again
    with pytest.raises(ValueError, match="already has a puzzle"):
        puzzles.create_from_line(START, ["d2d4"])
    with pytest.raises(ValueError):
        puzzles.create_from_line("8/8/8/8/8/8/8/8 w - - 0 1", ["a1a2"])


# ── Selection ─────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_review_queue_order_and_new_limit():
    now = timezone.now()
    p = puzzles.create_from_line(MATE_IN_2, ["d1d8"])
    learning = p.cards.get()
    Card.objects.filter(pk=learning.pk).update(state="learning", due=now - timedelta(minutes=1))
    for i in range(25):
        puzzles.create_from_line(back_rank(i + 1), ["d1d8"], title=f"n{i}")
    queue = selection.review_queue(now)
    assert queue[0].pk == learning.pk
    assert len([c for c in queue if c.state == "new"]) == srs.NEW_PER_DAY


@pytest.mark.django_db
def test_run_queue_is_one_card_per_puzzle_easy_to_hard():
    import random

    for moves in (["d1d8"], ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"]):
        puzzles.create_from_line(MATE_IN_2 if moves == ["d1d8"] else START, moves)
    queue = selection.run_queue(random.Random(1))
    assert len({c.puzzle_id for c in queue}) == len(queue) == 2
    assert puzzles.solver_moves(queue[0].line) <= puzzles.solver_moves(queue[-1].line)


# ── API ───────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestApi:
    def test_nothing_to_train(self, client):
        data = post(client, "/train/start/", {"mode": "review"}).json()
        assert data == {"ok": False, "empty": True, "message": "Nothing due right now."}

    def test_puzzle_from_a_board_line(self, client):
        data = post(client, "/puzzles/from-line/", {"start": MATE_IN_2, "moves": ["d1d8"], "title": "Back rank"}).json()
        assert data["ok"] and data["cards"] == 1
        assert Puzzle.objects.get().position.title == "Back rank"
        bad = post(client, "/puzzles/from-line/", {"start": MATE_IN_2, "moves": ["d1d9"]})
        assert bad.status_code == 422 or not bad.json()["ok"]

    def test_a_whole_session(self, client):
        for i in range(12):
            fen, line = (back_rank(i), ["d1d8"]) if i % 2 else opening_line(i)
            puzzles.create_from_line(fen, line, title=f"p{i}")
        start = post(client, "/train/start/", {"mode": "storm", "minutes": 5, "pace": "fast"}).json()
        assert start["ok"] and start["total"] == 12 and len(start["puzzles"]) == 10
        assert start["clock"]["factor"] == 0.5 and start["clock"]["typical"] == 8000
        sid = start["session"]
        more = client.get(f"/train/r/{sid}/batch/", {"offset": 10}).json()["puzzles"]
        assert len(more) == 2
        first = start["puzzles"][0]
        assert set(first) >= {"card", "fen", "solver", "tree", "line", "title"}
        ok = post(client, f"/train/r/{sid}/attempt/", {"card": first["card"], "success": True, "ms": 3000}).json()
        assert ok["ok"] and ok["stage"] == "learning" and ok["due"] == "tomorrow"  # solved new card: the 1-day step
        hinted = post(client, f"/train/r/{sid}/attempt/", {"card": start["puzzles"][1]["card"], "success": True, "hinted": True, "ms": 9000}).json()
        assert hinted["ok"]
        assert Attempt.objects.filter(success=False, hinted=True).count() == 1  # a hint counts as missed
        post(client, f"/train/r/{sid}/end/", {"best_combo": 1, "duration_s": 300})
        session = Session.objects.get()
        assert (session.solved, session.failed, session.best_combo) == (1, 1, 1) and session.ended_at
        html = client.get(f"/train/r/{sid}/result/").content.decode()
        assert "Storm 5′" in html and "▲ new best Storm 5′: 1" in html and html.count('data-row="') == 2

    def test_mirrored_side_and_given_cards(self, client):
        p = puzzles.create_from_line(MATE_IN_2, ["d1d8"])
        data = post(client, "/train/start/", {"mode": "streak", "side": "black"}).json()
        assert data["puzzles"][0]["solver"] == "b" and data["puzzles"][0]["line"] == ["d8d1"] and data["puzzles"][0]["mirrored"]
        card = str(p.cards.get().uuid)
        again = post(client, "/train/start/", {"mode": "review", "cards": [card]}).json()
        assert [x["card"] for x in again["puzzles"]] == [card]

    def test_launcher_and_flag(self, client):
        p = puzzles.create_from_line(MATE_IN_2, ["d1d8"])
        html = client.get("/train/launcher/").content.decode()
        assert "1 cards in 1 puzzles" in html and 'data-cmd="train.storm"' in html
        assert post(client, "/train/flag/", {"puzzle": str(p.uuid)}).json()["ok"]
        assert Puzzle.objects.get().flagged


