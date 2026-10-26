"""What the first testers asked for: the silhouette look as poker chips, typed-move hints and completion that can be
switched off for puzzles, the key intro on Home, and the pane menu that makes everything reachable with the mouse."""

import pytest

from spaced_positions.core.models import Preferences
from spaced_positions.training import puzzles
from tests.browser import keys, open_mode
from tests.factories import back_rank
from tests.test_analyse_browser import analyse, ruy  # noqa: F401

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]


def settings(**values):
    Preferences.objects.update_or_create(pk=Preferences.current().pk, defaults={"settings": values})


@pytest.fixture
def mate():
    puzzles.create_from_line(back_rank(0), ["d1d8"], title="Back rank")  # 1.Rd8#: the rook moves along the d-file


def solving(page):
    open_mode(page, "train")
    page.wait_for_function("window.SPOS.train && document.querySelector('[data-train-launcher]:not([hidden])')")
    keys(page, "r")
    page.wait_for_function("window.SPOS.train.state().state === 'solving'")


def test_the_silhouette_look_shows_poker_chips(page, mate):
    open_mode(page, "train")
    page.wait_for_function("window.SPOS.train && document.querySelector('[data-train-launcher]:not([hidden])')")
    keys(page, "w", "Enter")  # look: silhouette, then the custom session
    page.wait_for_function("window.SPOS.train.state().state === 'solving'")
    chip = page.evaluate("""(() => { const p = document.querySelector('#ws-train .is-silhouette piece.white')
      const s = getComputedStyle(p, '::before'); return [getComputedStyle(p).backgroundImage, s.content, s.backgroundImage] })()""")
    assert chip[0] == "none" and chip[1] != "none" and "conic-gradient" in chip[2]  # no piece picture, a chip instead


def test_typed_moves_in_a_puzzle_without_hints_or_completion(page, mate):
    settings(**{"training.move-hints": False, "training.move-complete": False})
    solving(page)
    keys(page, "i", "R")  # one rook move fits (and checkmates), but completion is off and no arrows show
    assert page.evaluate("document.querySelectorAll('#ws-train .cg-shapes line').length") == 0
    keys(page, "Enter")
    page.wait_for_function("document.getElementById('status-message').textContent.includes('Type the whole move')")
    assert page.evaluate("window.SPOS.train.state().solved") == 0
    for key in ("d", "8", "Enter"):
        keys(page, key)
    page.wait_for_function("window.SPOS.train.state().solved === 1")


def test_typed_moves_in_a_puzzle_with_hints(page, mate):
    solving(page)
    keys(page, "i", "R")
    page.wait_for_function("document.querySelectorAll('#ws-train .cg-shapes line').length > 0")  # arrows for the rook moves


def test_the_key_intro_ticks_off_what_was_tried(page):
    open_mode(page, "home")
    page.wait_for_selector("[data-intro] [data-step]")
    page.evaluate("localStorage.removeItem('spos.intro')")
    page.click("[data-view=today] .pane__title")
    keys(page, "Tab")  # next pane
    page.wait_for_selector("[data-intro] [data-step=pane].is-done")
    keys(page, "Space", "l")
    page.wait_for_function("window.SPOS.ctx.mode === 'library'")
    keys(page, "Space", "h")
    page.wait_for_selector("[data-intro] [data-step=modes].is-done")
    assert "2 of 7" in page.inner_text("[data-intro-count]")
    page.click("[data-intro] [data-cmd='pref.set']")  # Hide this
    page.wait_for_function("window.SPOS.settings['keys.intro'] === false")


def test_the_pane_menu_reaches_everything_with_the_mouse(page, ruy):
    analyse(page, ruy)
    keys(page, "G")  # the end of the line
    page.click("#ws-analyse [data-view=moves] .pane__menu")
    page.wait_for_selector(".menu >> text=To the start position")
    assert page.locator(".menu .menu__heading").all_inner_texts()[:2] == ["MOVES", "PANE"] or \
        page.locator(".menu .menu__heading").count() == 2
    page.click(".menu >> text=To the start position")
    page.wait_for_function("!document.querySelector('#ws-analyse .mt-move.is-cursor')")  # the cursor at the start
    # a right click on a header opens the same menu there; "Split horizontally" puts a new pane below
    before = page.locator("#ws-analyse [data-pane]").count()
    page.click("#ws-analyse [data-view=board] .pane__title", button="right")
    page.wait_for_selector(".menu >> text=Split horizontally")
    page.click(".menu >> text=Split horizontally")
    page.wait_for_selector(".menu")  # the view picker for the new pane
    keys(page, "p")
    page.wait_for_function(f"document.querySelectorAll('#ws-analyse [data-pane]').length === {before + 1}")
    # and with the keyboard: ␣ w w, j to an entry, ↵
    page.click("#ws-analyse [data-view=moves] .pane__title")
    keys(page, "Space", "w", "w")
    page.wait_for_selector(".menu >> text=To the end of the line")
    keys(page, "Escape")
    page.wait_for_selector(".menu", state="detached")
