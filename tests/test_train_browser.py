"""Train journeys in a real browser (spec 04 · Train): Review with feedback, Storm with the clock, Streak with lives,
the blind look, hints, pausing, the result, and making a puzzle from a board line."""

import pytest

from spaced_positions.training import puzzles
from spaced_positions.training.models import Attempt, Puzzle, Session
from tests.browser import keys, layer, open_mode
from tests.factories import back_rank, opening_line

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]

MATE = "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1"  # 1.Rd8#
OPEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


@pytest.fixture
def train(page):
    for i in range(3):
        puzzles.create_from_line(back_rank(i), ["d1d8"], title=f"Back rank {i}")
        fen, line = opening_line(i)
        puzzles.create_from_line(fen, line, title=f"Opening {i}")
    open_mode(page, "train")
    page.wait_for_function("window.SPOS.train && document.querySelector('[data-train-launcher]:not([hidden])')")
    return page


def state(page):
    return page.evaluate("window.SPOS.train.state()")


def wait_state(page, name):
    page.wait_for_function(f"window.SPOS.train.state().state === '{name}'", timeout=5000)


def solve_typed(page):
    """Type the card's line (solver moves in UCI), waiting for each answer."""
    line = page.evaluate("window.SPOS.train.puzzle().line")
    keys(page, "i")
    for i in range(0, len(line), 2):
        for ch in line[i]:
            page.keyboard.press(ch)
        keys(page, "Enter")
        if i + 1 < len(line):
            page.wait_for_function(f"window.SPOS.train.puzzle() === null || window.SPOS.train.puzzle().at >= {i + 2}")
            page.wait_for_timeout(350)  # the answer is played after a short pause


def test_review_solve_miss_and_result(train):
    keys(train, "r")
    wait_state(train, "solving")
    assert train.is_hidden(".appbar")  # solving is fullscreen
    solve_typed(train)
    wait_state(train, "feedback")
    train.wait_for_function("document.querySelector('[data-fb-verdict]').textContent.startsWith('✓ Solved')")
    train.wait_for_function("document.querySelector('[data-fb-schedule]').textContent.startsWith('next')")
    keys(train, "Escape")  # leave the move entry
    keys(train, "Enter")
    wait_state(train, "solving")
    keys(train, "s")  # give up
    wait_state(train, "feedback")
    assert train.inner_text("[data-fb-verdict]") == "✗ Solution shown"
    keys(train, "Escape")
    assert "q end the session" in train.inner_text("#status-message")
    keys(train, "q")
    wait_state(train, "result")
    assert train.locator("[data-train-result] .list__row").count() == 2
    assert Attempt.objects.filter(success=True).count() == 1 and Attempt.objects.filter(gave_up=True).count() == 1
    keys(train, "m")  # review the missed one
    wait_state(train, "solving")
    assert train.evaluate("window.SPOS.train.puzzle().card") == str(Attempt.objects.get(gave_up=True).card.uuid)


def test_storm_clock_bonus_and_penalty(train):
    keys(train, "1")
    wait_state(train, "solving")
    assert train.inner_text("[data-hud-label]") == "Storm 3′"
    line = train.evaluate("window.SPOS.train.puzzle().line")
    train.evaluate(
        """async (line) => { const b = document.querySelector('#ws-train [data-island=board]').board
          const { Chess } = await import('/static/vendor/chess.js'); const c = new Chess(b.line.start)
          for (let i = 0; i < line.length; i += 2) {
            b.submit(c.move({from: line[i].slice(0,2), to: line[i].slice(2,4)}))
            await new Promise(r => setTimeout(r, 400))
            if (line[i+1]) c.move({from: line[i+1].slice(0,2), to: line[i+1].slice(2,4)}) } }""",
        line,
    )
    train.wait_for_function("window.SPOS.train.state().solved === 1")
    assert train.inner_text("[data-hud-delta]") == "+6.0s"
    train.evaluate(
        """async () => { const b = document.querySelector('#ws-train [data-island=board]').board
          const { Chess } = await import('/static/vendor/chess.js'); const c = new Chess(b.line.start)
          const p = window.SPOS.train.puzzle(); const wrong = c.moves({verbose: true}).find(m => m.from + m.to !== p.line[0])
          b.submit(wrong) }"""
    )
    train.wait_for_function("window.SPOS.train.state().failed === 1")
    assert train.inner_text("[data-hud-delta]") == "−10.0s" and state(train)["combo"] == 0
    keys(train, "Escape", "y")
    wait_state(train, "result")
    session = Session.objects.get()
    assert (session.solved, session.failed, session.options["minutes"]) == (1, 1, 3)


def test_streak_with_lives(train):
    keys(train, "5")  # Streak ♥3
    wait_state(train, "solving")
    assert train.inner_text("[data-hud-lives]") == "♥♥♥"
    keys(train, "s")
    wait_state(train, "feedback")
    assert state(train)["lives"] == 2 and train.inner_text("[data-hud-lives]") == "♥♥♡"


def test_blind_look_types_moves_and_lists_pieces(train):
    keys(train, "6")
    wait_state(train, "solving")
    assert layer(train) == "entry"
    assert train.eval_on_selector("#ws-train .board", "e => e.classList.contains('is-blind')")
    assert train.inner_text("[data-hud-pieces]").startswith("White: K")


def test_hint_counts_as_missed(train):
    keys(train, "r")
    wait_state(train, "solving")
    keys(train, "h", "h")
    assert "counts as missed" in train.inner_text("#status-message")
    shapes = train.evaluate("document.querySelector('#ws-train [data-island=board]').board.cg.state.drawable.autoShapes.length")
    assert shapes == 2
    keys(train, "Escape")  # pause
    assert "Paused" in train.inner_text("#status-message")
    keys(train, "Enter")  # resume
    solve_typed(train)
    wait_state(train, "feedback")
    assert "hint" in train.inner_text("[data-fb-verdict]")
    train.wait_for_function("document.querySelector('[data-fb-schedule]').textContent.startsWith('next')")
    assert Attempt.objects.get().hinted and not Attempt.objects.get().success


def test_custom_session_options(train):
    keys(train, "m", "d", "c", "o")  # Streak, as Black, 3 lives, first move only
    assert train.get_attribute("[data-cmd='train.set'][data-args='side black']", "aria-checked") == "true"
    assert train.get_attribute("[data-cmd='train.set'][data-args='first']", "aria-pressed") == "true"
    keys(train, "Enter")
    wait_state(train, "solving")
    p = train.evaluate("window.SPOS.train.puzzle()")
    assert p["solver"] == "b" and p["firstOnly"] and len(p["line"]) == 1


def test_make_a_puzzle_from_a_board_line(page):
    keys(page, "Space", "3")  # the style guide's board
    page.evaluate(
        """async () => { const b = document.querySelector('[data-island=board]').board
          const { Chess } = await import('/static/vendor/chess.js'); const c = new Chess(b.line.start)
          b.submit(c.move('e4')); b.submit(c.move('e5')); b.submit(c.move('Nf3')) }"""
    )
    keys(page, ":")
    page.keyboard.type("puzzle")
    keys(page, "Enter")
    page.wait_for_function("document.getElementById('status-message').textContent.startsWith('Puzzle saved')")
    assert Puzzle.objects.get().cards.get().line == ["e2e4", "e7e5", "g1f3"]


def test_stop_a_review_after_a_few_cards(train):
    """Q (or the Stop button) ends a session at once: what was done counts, the rest stays due."""
    from spaced_positions.training.models import Card

    keys(train, "r")
    wait_state(train, "solving")
    solve_typed(train)
    wait_state(train, "feedback")
    keys(train, "Shift+Q")  # on the feedback screen
    wait_state(train, "result")
    train.wait_for_function("document.getElementById('status-message').textContent.startsWith('Stopped after 1 puzzle')")
    assert "not reached stay due" in train.inner_text("#status-message")
    assert Attempt.objects.count() == 1 and Session.objects.get().ended_at is not None
    # again, stopping while solving, with the button
    keys(train, "l")
    wait_state(train, "launcher")
    keys(train, "r")
    wait_state(train, "solving")
    train.click("[data-train-hud] [data-cmd='train.quit']")
    wait_state(train, "result")
    assert Attempt.objects.count() == 1  # the card on the board was not counted
    assert Card.objects.filter(attempt_log__isnull=True).exists()  # the rest stays as it was
