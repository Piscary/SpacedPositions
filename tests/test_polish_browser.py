"""Polish in a real browser: figurines and folded variations in the move tree, the Storm pace in the launcher,
German letters in the setup palette, coordinates outside the board, sounds and counting numbers."""

import pytest

from spaced_positions.analysis import tree
from spaced_positions.core.models import Preferences
from tests.browser import keys, open_mode

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def analyse(page, p):
    open_mode(page, "analyse")
    page.evaluate("(pid) => window.SPOS.analysis.open(pid)", str(p.uuid))
    page.wait_for_selector("#ws-analyse [data-movetree]")
    page.click("#ws-analyse [data-view=moves] .pane__title")


def run(page, text):
    keys(page, ":")
    page.keyboard.type(text)
    keys(page, "Enter")


def test_figurines_and_folded_variations(page):
    p = tree.create_position(START, ["e2e4", "e7e5", "g1f3", "b8c6"], title="Open game")
    tree.play(p.nodes.get(san="e5"), "b1c3")  # 2.Nc3 instead of 2.Nf3
    tree.play(p.nodes.get(san="Nc3"), "g8f6")
    analyse(page, p)
    nf3 = "#ws-analyse .mt-move >> text=Nf3"
    drawn = "(sel) => getComputedStyle(document.querySelector(sel), '::before').content"
    piece = "#ws-analyse .mt-move .san-p"
    assert page.evaluate(drawn, piece) == "none"
    run(page, "set figurines=on")
    page.wait_for_selector("html[data-figurines]")
    assert page.evaluate(drawn, piece) == '"♘"' and page.is_visible(nf3)  # drawn as a figurine, still found as Nf3
    # z on the main line folds the alternatives to the next move (2.Nc3 to 2.Nf3)
    keys(page, "l", "l")  # 1…e5
    keys(page, "z")
    page.wait_for_selector("#ws-analyse .mt-variation.is-folded")
    assert not page.is_visible(f"#ws-analyse [data-node='{p.nodes.get(san='Nf6').id}']")
    # its first move stays visible; moving further in opens it again
    keys(page, "l", "j")  # 2.Nc3
    assert page.is_visible("#ws-analyse .mt-variation.is-folded")
    keys(page, "l")  # 2…Nf6
    page.wait_for_selector("#ws-analyse .mt-variation:not(.is-folded)")
    keys(page, "Z")  # all folded, except the one the cursor is in
    page.wait_for_function("document.getElementById('status-message').textContent.startsWith('All variations folded')")
    assert page.get_attribute("#ws-analyse .mt-caret", "aria-expanded") == "true"
    page.click("#ws-analyse .mt-caret")  # the mouse folds it
    page.wait_for_selector("#ws-analyse .mt-caret[aria-expanded='false']")


def test_storm_pace_in_the_launcher(page):
    open_mode(page, "train")
    page.wait_for_selector("#ws-train [aria-label='Storm pace']")
    page.click("#ws-train [aria-label='Storm pace'] >> text=slow")
    page.wait_for_function("window.SPOS.settings['training.storm-pace'] === 'slow'")
    assert Preferences.current().settings == {"training.storm-pace": "slow"}


def test_german_letters_in_setup_and_in_the_move_tree(page):
    p = tree.create_position(START, ["e2e4", "e7e5", "g1f3"], title="Open game")
    analyse(page, p)
    run(page, "set board.letters=de")
    page.wait_for_selector("html[data-letters='de']")
    assert page.evaluate("getComputedStyle(document.querySelector('#ws-analyse .mt-move .san-p'), '::before').content") == '"S"'
    open_mode(page, "collect")
    page.wait_for_function("document.querySelector('#ws-collect [data-island=board]')?.board?.layer === 'setup'")
    page.click("#ws-collect [data-view=board] .pane__title")
    for key, role in (("s", "knight"), ("l", "bishop"), ("t", "rook"), ("d", "queen"), ("b", "pawn")):
        keys(page, key)
        page.wait_for_function(f"document.querySelector('#ws-collect [data-island=board]').board.setup.role === '{role}'")


def test_coordinates_outside_the_board(page):
    p = tree.create_position(START, [], title="Start")
    analyse(page, p)
    run(page, "set board-coords=outside")
    page.wait_for_selector("html[data-coords='outside']")
    page.wait_for_timeout(400)  # the board shrinks by the margin and is drawn again
    board = page.locator("#ws-analyse cg-board").bounding_box()
    ranks = page.locator("#ws-analyse coords.ranks").bounding_box()
    files = page.locator("#ws-analyse coords.files").bounding_box()
    assert ranks["x"] + ranks["width"] <= board["x"] + 1 and files["y"] >= board["y"] + board["height"] - 1
    run(page, "set board-coords=off")
    page.wait_for_selector("#ws-analyse coords", state="detached")


def test_sounds_when_on_and_numbers_that_count(page):
    page.add_init_script("""
      window.__tones = []
      window.AudioContext = class {
        constructor() { this.currentTime = 0; this.state = "running"; this.destination = {} }
        createOscillator() { const o = { type: "", frequency: {}, connect: (g) => g, start: () => window.__tones.push(o.frequency.value), stop() {} }; return o }
        createGain() { return { gain: { setValueAtTime() {}, linearRampToValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect: (d) => d } }
        resume() {}
      }
    """)
    p = tree.create_position(START, [], title="Start")
    analyse(page, p)
    page.click("#ws-analyse [data-view=board] .pane__title")
    keys(page, "i", "e", "4", "Enter", "Escape")  # typed move entry
    page.wait_for_function("document.querySelector('#ws-analyse .mt-move')")
    assert page.evaluate("window.__tones.length") == 0  # off by default
    run(page, "set sound.on=on")
    page.wait_for_function("window.SPOS.settings['sound.on'] === true")
    page.click("#ws-analyse [data-view=board] .pane__title")
    keys(page, "i", "e", "5", "Enter", "Escape")
    page.wait_for_function("window.__tones.length === 1")
    # Home's numbers count up to their value
    open_mode(page, "home")
    page.wait_for_selector("#ws-home [data-ticker][data-ticker-value]", state="attached")
    page.wait_for_timeout(400)
    for value, shown in page.eval_on_selector_all("#ws-home [data-ticker]", "els => els.map(e => [e.dataset.tickerValue, e.textContent])"):
        assert value == shown


def test_the_local_engine_in_analyse(page, tmp_path):
    import sys

    from spaced_positions.core import engine_local
    from tests.test_settings import FAKE_ENGINE

    fake = tmp_path / "fakefish"
    fake.write_text(FAKE_ENGINE.format(python=sys.executable), encoding="utf-8")
    fake.chmod(0o755)
    Preferences.objects.update_or_create(pk=Preferences.current().pk, defaults={"settings": {"engine.source": "local", "engine.path": str(fake)}})
    try:
        p = tree.create_position(START, [], title="Start")
        analyse(page, p)
        keys(page, ":")
        page.keyboard.type("vsplit engine")
        keys(page, "Enter")
        page.click("#ws-analyse [data-view=moves] .pane__title")
        keys(page, "e")
        page.wait_for_selector("#ws-analyse .engine__line >> text=+0.33")
        assert "fakefish · depth 5" in page.inner_text("#ws-analyse [data-island=engine]")
    finally:
        if engine_local._engine is not None:
            engine_local._engine.close()
            engine_local._engine = None
