"""Keyboard journeys and screenshots in a real browser (spec 07 §8: tests 3–5).

Run with `pytest -m browser` after `python -m playwright install chromium`. Screenshots go to
tests/screenshots/current/; with SPOS_UPDATE_SCREENSHOTS=1 (or when no baseline exists yet) they become the
baseline in tests/screenshots/baseline/<platform>/, and later runs fail if a screenshot differs by more than 0.5 %.
"""

import os
import sys
from pathlib import Path

import pytest

from tests.browser import keys, layer, open_mode, panes

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]

SHOTS = Path(__file__).parent / "screenshots"
# spec 01 · P5: key → reaction within a frame. Tolerance × 1.5 on a computer, × 4 on CI (shared, slow machines)
LATENCY_BUDGET_MS = 16 * (4 if os.environ.get("CI") else 1.5)


def test_which_key_lists_the_window_commands(page):
    keys(page, "Space", "w")
    assert layer(page) == "pending"
    text = page.inner_text(".whichkey")
    assert "Split vertically" in text and "Close pane" in text
    keys(page, "Escape")
    assert layer(page) == "normal" and page.is_hidden(".whichkey")


def test_split_pick_close_undo_redo(page):
    keys(page, "Space", "w", "v")
    page.wait_for_selector(".menu")
    keys(page, "p")  # view picker: PGN / FEN
    page.wait_for_selector('.workspace:not([hidden]) [data-view="pgn"] form')
    assert panes(page) == ["components", "pgn", "library", "board"]
    assert page.inner_text("#status-pane").startswith("2")  # the new pane has focus
    keys(page, "Space", "w", "q")
    assert panes(page) == ["components", "library", "board"]
    keys(page, "u")
    assert panes(page) == ["components", "pgn", "library", "board"]
    assert "Undone" in page.inner_text("#status-message")
    keys(page, "U")
    assert panes(page) == ["components", "library", "board"]


def test_focus_and_resize_by_keys(page):
    keys(page, "Tab")
    assert page.inner_text("#status-pane").startswith("2")
    keys(page, "Space", "1")
    assert page.inner_text("#status-pane").startswith("1")
    before = page.eval_on_selector(".workspace:not([hidden]) > .split > .split__child", "e => e.style.flex")
    keys(page, "Space", "w", ">", ">")  # sticky: the second > needs no prefix
    after = page.eval_on_selector(".workspace:not([hidden]) > .split > .split__child", "e => e.style.flex")
    assert float(after.split()[0]) == pytest.approx(float(before.split()[0]) + 10, abs=0.01)
    keys(page, "Escape")
    assert layer(page) == "normal"


def test_list_selection_and_linked_board(page):
    from spaced_positions.analysis import tree
    from tests.factories import back_rank

    for i in range(6):
        tree.create_position(back_rank(i % 3), [], title=f"Position {i}")
    open_mode(page, "ui")  # the style guide's Library, linked to its board
    page.wait_for_selector(".workspace:not([hidden]) [data-library-results] [data-row]")
    keys(page, "Space", "2", "j", "j", "j", "x", "v", "j", "j")
    assert layer(page) == "visual"
    assert page.inner_text("#status-subject") == "3 selected"
    cursor = page.eval_on_selector(".workspace:not([hidden]) [data-row].is-cursor", "e => [e.dataset.title, e.dataset.fen]")
    board = page.evaluate("(() => { const b = document.querySelector('[data-island=board]').board; return [b.line.title, b.line.start] })()")
    assert board == cursor  # the board in the same link group shows the row under the cursor
    keys(page, "Escape", "Escape")
    assert layer(page) == "normal" and page.inner_text("#status-subject") != "3 selected"


def test_command_line_theme_and_tokens(page):
    keys(page, ":")
    page.keyboard.type("theme ink")
    keys(page, "Enter")
    page.wait_for_function("document.getElementById('theme').textContent.includes('#16181d')")
    keys(page, ":")
    page.keyboard.type("set main=#ff0000")
    keys(page, "Enter")
    page.wait_for_function("document.getElementById('theme').textContent.includes('--main: #ff0000')")
    keys(page, "u")
    page.wait_for_function("!document.getElementById('theme').textContent.includes('--main: #ff0000')")


def test_modes_switch_and_stay_alive(page):
    keys(page, "Space", "t")
    page.wait_for_url("**/train/")
    keys(page, "Space", "Space")
    page.wait_for_url("**/ui/")
    keys(page, "Space", "h", "Space", "s", "Space", "l")  # fast: the last key wins, whatever loads first
    page.wait_for_function("location.pathname === '/library/' && document.getElementById('ws-library')?.hidden === false")
    assert page.locator(".workspace:not([hidden])").count() == 1
    assert page.locator(".workspace").count() == 3  # at most three modes stay in the DOM
    assert page.locator("#ws-library").count() == 1
    page.go_back()  # only completed switches enter the history: back from library is the mode shown before it
    page.wait_for_function("""(() => {
      const mode = location.pathname.replaceAll('/', '')
      return mode !== 'library' && document.getElementById(`ws-${mode}`)?.hidden === false
    })()""")


def test_insert_layer(page):
    open_mode(page, "collect")
    field = '.workspace:not([hidden]) [data-view="pgn"] textarea'
    page.click(field)
    assert layer(page) == "insert"
    page.keyboard.type("jk u")
    assert page.input_value(field) == "jk u"
    keys(page, "Escape")
    assert layer(page) == "normal"
    assert page.input_value(field) == "jk u"


def test_hint_labels_click_by_keyboard(page):
    keys(page, "F")
    assert layer(page) == "hint"
    label = page.evaluate(
        """() => {
          const tab = document.querySelector('[data-mode-tab="home"]').getBoundingClientRect()
          const hit = [...document.querySelectorAll('.hint-label')].find(l =>
            Math.abs(parseFloat(l.style.left) - Math.max(2, tab.left)) < 1 && Math.abs(parseFloat(l.style.top) - Math.max(2, tab.top)) < 1)
          return hit.textContent }"""
    )
    page.keyboard.type(label.lower())
    page.wait_for_url("**/home/")


def test_layout_survives_a_reload(page):
    keys(page, "Space", "w", "c")  # collapse pane 1
    page.wait_for_timeout(700)  # the layout is saved 500 ms after the last change
    open_mode(page, "ui")
    assert page.eval_on_selector('[data-pane="p1"]', "e => e.classList.contains('is-collapsed')")


def test_key_latency_budget(page):
    keys(page, "Space", "2", *["j"] * 10, *["k"] * 5, "Tab", "Tab")
    timings = page.evaluate("window.SPOS.keyPerf()")
    assert timings, "no key timings recorded"
    slow = [t for t in timings if t["ms"] > LATENCY_BUDGET_MS]
    assert slow == [], f"over {LATENCY_BUDGET_MS} ms: {slow}"


@pytest.mark.parametrize("theme", ["paper", "ink"])
@pytest.mark.parametrize("density", ["compact", "cozy"])
def test_style_guide_screenshots(page, theme, density):
    import os

    if os.environ.get("SPOS_TEST_JITTER"):
        pytest.skip("screenshot comparison is unreliable under jitter — page may show loading states")
    from PIL import Image, ImageChops

    page.evaluate(
        """async ([theme, density]) => {
          const headers = {"Content-Type": "application/json", "X-CSRFToken": document.querySelector('meta[name=csrf-token]').content}
          await fetch('/cmd/theme.set/', {method: 'POST', headers, body: JSON.stringify({args: [theme]})})
          await fetch('/cmd/pref.set/', {method: 'POST', headers, body: JSON.stringify({args: ['density=' + density]})})
        }""",
        [theme, density],
    )
    open_mode(page, "ui")
    page.add_style_tag(content="*, *::before, *::after { animation: none !important; transition: none !important; }")
    name = f"style-guide-{theme}-{density}.png"
    current = SHOTS / "current" / name
    current.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(current))
    baseline = SHOTS / "baseline" / sys.platform / name
    if os.environ.get("SPOS_UPDATE_SCREENSHOTS") == "1" or not baseline.exists():
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_bytes(current.read_bytes())
        return
    a, b = Image.open(baseline).convert("RGB"), Image.open(current).convert("RGB")
    assert a.size == b.size, f"{name}: size changed {a.size} → {b.size}"
    diff = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > 16 else 0)
    changed = sum(diff.histogram()[255:]) / (a.size[0] * a.size[1])
    assert changed < 0.005, f"{name}: {changed:.2%} of pixels changed (see tests/screenshots/current/)"


def test_scroll_and_sections_by_keyboard(page):
    keys(page, "Space", "1")
    body = ".workspace:not([hidden]) [data-view=components] .pane__body"
    top = lambda: page.eval_on_selector(body, "e => e.scrollTop")  # noqa: E731
    keys(page, "j", "j")
    assert top() > 0
    keys(page, "G")
    assert top() == page.eval_on_selector(body, "e => e.scrollHeight - e.clientHeight")
    keys(page, "g", "g")
    assert top() == 0
    keys(page, "J")
    assert top() == pytest.approx(page.eval_on_selector(body, "e => e.clientHeight / 2"), abs=2)
    keys(page, "g", "g", "]", "]")
    assert page.inner_text(".workspace:not([hidden]) .section.is-cursor .section__title") == "Piece sets"
    keys(page, "[")
    assert page.inner_text(".workspace:not([hidden]) .section.is-cursor .section__title") == "MiniBoard"


def test_i_edits_the_panes_field(page):
    keys(page, "Space", "1", "i")
    assert layer(page) == "insert" and page.evaluate("document.activeElement.id") == "gallery-field"
    page.keyboard.type("Réti")
    keys(page, "Escape")
    assert layer(page) == "normal"
    keys(page, "Space", "2", "i")  # the Library: its query bar
    assert layer(page) == "insert" and page.evaluate("document.activeElement.matches('[data-querybar]')")
    keys(page, "Escape")
    open_mode(page, "stats")
    page.click("#ws-stats [data-view=chart] .pane__title")
    keys(page, "i")  # the charts have no text field
    assert layer(page) == "normal" and "no text field" in page.inner_text("#status-message")
