"""The first GitHub issues: Train's Session pane after its workspace was unloaded (#1), the start position in the
moves pane (#2), the Puzzle pane (#3), and one rule for sections in every pane (#4)."""

import pytest

from spaced_positions.analysis import tree
from spaced_positions.training import puzzles
from spaced_positions.training.models import Puzzle
from tests.browser import board_state, keys, open_mode
from tests.factories import back_rank
from tests.test_analyse_browser import START, analyse, ruy  # noqa: F401

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]


def leave_train_for_long(page):
    """Four other modes: more than are kept loaded, so Train's workspace may be unloaded meanwhile."""
    for key, mode in (("h", "home"), ("l", "library"), ("s", "stats"), ("c", "collect")):
        keys(page, "Space", key)
        page.wait_for_function(f"window.SPOS.ctx.mode === '{mode}'")
    keys(page, "Space", "t")
    page.wait_for_function("window.SPOS.ctx.mode === 'train'")


def test_the_session_pane_shows_the_result_after_train_was_unloaded(page):
    for i in range(2):
        puzzles.create_from_line(back_rank(i), ["d1d8"], title=f"Back rank {i}")
    open_mode(page, "train")
    page.wait_for_function("window.SPOS.train && document.querySelector('[data-train-launcher]:not([hidden])')")
    keys(page, "r")
    page.wait_for_function("window.SPOS.train.state().state === 'solving'")
    keys(page, "s")  # give up
    page.wait_for_function("window.SPOS.train.state().state === 'feedback'")
    keys(page, "Escape", "q")
    page.wait_for_function("window.SPOS.train.state().state === 'result'")
    assert page.evaluate("document.getElementById('ws-train').dataset.keep") is None  # the session is over: unloadable
    page.evaluate("document.getElementById('ws-train').dataset.before = '1'")
    leave_train_for_long(page)
    assert page.evaluate("!document.getElementById('ws-train').dataset.before")  # rebuilt: it was unloaded
    page.wait_for_selector("#ws-train [data-train-result]:not([hidden]) .list__row")


def test_a_running_session_is_never_unloaded(page):
    puzzles.create_from_line(back_rank(0), ["d1d8"], title="Back rank")
    open_mode(page, "train")
    page.wait_for_function("window.SPOS.train && document.querySelector('[data-train-launcher]:not([hidden])')")
    keys(page, "r")
    page.wait_for_function("window.SPOS.train.state().state === 'solving'")
    page.evaluate("document.getElementById('ws-train').dataset.before = '1'")
    leave_train_for_long(page)
    assert page.evaluate("document.getElementById('ws-train').dataset.before") == "1"
    assert page.inner_text("#ws-train [data-hud-label]")


def test_the_start_position_in_the_moves_pane(page, ruy):
    analyse(page, ruy)
    keys(page, "G")
    assert board_state(page)["ply"] > 0
    page.click("#ws-analyse .mt-start")
    page.wait_for_selector("#ws-analyse .mt-start.is-cursor")
    assert board_state(page)["ply"] == 0
    keys(page, "l")
    page.wait_for_selector("#ws-analyse .mt-start:not(.is-cursor)")


def test_the_puzzle_pane_walks_through_the_setup(page, ruy):
    analyse(page, ruy)
    pane = "#ws-analyse [data-island=puzzle]"
    page.wait_for_selector(f"{pane} .pzpane__where--none")
    page.click(f"{pane} [data-cmd='analysis.puzzle'][data-args=start]")
    page.wait_for_selector(f"{pane} .pzpane__where--start")
    assert "White to move" in page.inner_text(f"{pane} .pzpane__step:first-child")
    also = f"{pane} [data-cmd='analysis.puzzle'][data-args=also]"
    assert page.get_attribute(also, "aria-disabled") == "true"  # at the start: no solver move yet, and it says why
    assert "go to a move of the solution" in page.inner_text(f"{pane} .pzpane__why")
    page.click(f"{pane} .pzpane__line .pzpane__move >> nth=0")  # a click on a line's move goes there
    page.wait_for_selector(f"{pane} .pzpane__where--solver")
    assert page.get_attribute(also, "aria-disabled") is None
    assert page.locator(f"{pane} .pzpane__line").count() == 1
    page.click(f"{pane} [data-cmd='analysis.puzzle'][data-args=ready]")
    page.wait_for_function("document.querySelector('#ws-analyse [data-island=puzzle]').textContent.includes('in training')")
    assert Puzzle.objects.get(position=ruy).active


def test_the_puzzle_pane_steps_through_a_list(page, ruy):
    other = tree.create_position(START, ["d2d4"], title="Queen's pawn")
    analyse(page, ruy)
    page.evaluate("([a, b]) => window.SPOS.analysis.open(a, {list: {ids: [a, b], index: 0}})", [str(ruy.uuid), str(other.uuid)])
    pane = "#ws-analyse [data-island=puzzle]"
    page.wait_for_selector(f"{pane} .pzpane__list >> text=Position 1 of 2")
    page.click(f"{pane} [data-cmd='analysis.subject'][data-args=next]")
    page.wait_for_selector(f"{pane} .pzpane__list >> text=Position 2 of 2")
    # Wait for the puzzle pane fetch to complete so the position title is available
    page.wait_for_function(
        "(title) => window.SPOS.analysis.current()?.position.title === title",
        arg="Queen's pawn",
        timeout=10000,
    )
    assert page.evaluate("window.SPOS.analysis.current().position.title") == "Queen's pawn"


def cursor_row(page, view):
    return page.evaluate(f"document.querySelector('.workspace:not([hidden]) [data-view={view}] [data-row].is-cursor')?.dataset.row ?? null")


def test_sections_put_the_cursor_on_their_first_row(page):
    for i in range(3):
        tree.create_position(START, ["e2e4"], title=f"Recent {i}")
    open_mode(page, "home")
    page.click("[data-view=continue] .pane__title")
    rows = page.eval_on_selector_all("[data-view=continue] [data-row]", "els => els.map(e => e.dataset.row)")
    keys(page, "j", "j")
    assert cursor_row(page, "continue") == rows[1]
    keys(page, "g", "r")  # the Recent section by its letter: its first row
    assert cursor_row(page, "continue") == rows[0]
    keys(page, "j")
    assert cursor_row(page, "continue") == rows[1]
    keys(page, "[")  # inside a section: its first row first
    assert cursor_row(page, "continue") == rows[0]
    keys(page, "[")  # then the section above (Paste: no rows, the cursor waits)
    page.wait_for_selector("[data-view=continue] [data-section-key=p].is-cursor")
    keys(page, "]")  # back down: the first row again, and j goes on from there
    assert cursor_row(page, "continue") == rows[0]
    keys(page, "j")
    assert cursor_row(page, "continue") == rows[1]


def test_the_keymap_has_groups_to_jump_between(page):
    open_mode(page, "settings")
    page.click("[data-view=keymap] .pane__title")
    page.wait_for_selector("[data-view=keymap] [data-group-head]")
    heads = page.eval_on_selector_all("[data-view=keymap] [data-group-head]", "els => els.map(e => e.dataset.groupHead)")
    assert len(heads) > 3
    keys(page, "]")
    first = cursor_row(page, "keymap")
    keys(page, "]")
    second = cursor_row(page, "keymap")
    group = "(id) => document.querySelector(`[data-view=keymap] [data-row='${id}']`).dataset.group"
    assert page.evaluate(group, first) != page.evaluate(group, second)
    keys(page, "j", "[")
    assert cursor_row(page, "keymap") == second


def test_a_right_click_on_a_pane_header_opens_one_menu(page, ruy):
    analyse(page, ruy)
    page.click("#ws-analyse [data-view=moves] .pane__title", button="right")
    page.wait_for_selector(".menu >> text=To the start position")
    assert page.locator(".menu").count() == 1
