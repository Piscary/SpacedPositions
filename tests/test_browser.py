"""Keyboard journeys and screenshots in a real browser (spec 07 §8: tests 3–5).

Run with `pytest -m browser` after `python -m playwright install chromium`. Screenshots go to
tests/screenshots/current/; with SPOS_UPDATE_SCREENSHOTS=1 (or when no baseline exists yet) they become the
baseline in tests/screenshots/baseline/<platform>/, and later runs fail if a screenshot differs by more than 0.5 %.
"""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")  # Playwright's sync API runs an event loop

playwright = pytest.importorskip("playwright.sync_api")

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]

SHOTS = Path(__file__).parent / "screenshots"
LATENCY_BUDGET_MS = 16 * 1.5  # spec 01 · P5: key → reaction within a frame, CI tolerance × 1.5


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Chromium not installed: {e}")
        yield browser
        browser.close()


@pytest.fixture
def page(browser, live_server):
    context = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
    page = context.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.base = live_server.url
    open_mode(page, "ui")
    yield page
    context.close()
    assert errors == [], errors


def open_mode(page, mode):
    page.goto(f"{page.base}/{mode}/")
    page.wait_for_function("window.SPOS && window.SPOS.ctx && window.SPOS.ctx.pane")


def keys(page, *sequence):
    for key in sequence:
        page.keyboard.press(key)


def panes(page):
    return page.eval_on_selector_all(".workspace:not([hidden]) [data-pane]", "els => els.map(e => e.dataset.view)")


def layer(page):
    return page.get_attribute("#shell", "data-layer")


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
    keys(page, "n")  # view picker: notes
    page.wait_for_selector('.workspace:not([hidden]) [data-view="notes"] form')
    assert panes(page) == ["components", "notes", "demo", "preview"]
    assert page.inner_text("#status-pane").startswith("2")  # the new pane has focus
    keys(page, "Space", "w", "q")
    assert panes(page) == ["components", "demo", "preview"]
    keys(page, "u")
    assert panes(page) == ["components", "notes", "demo", "preview"]
    assert "Undone" in page.inner_text("#status-message")
    keys(page, "U")
    assert panes(page) == ["components", "demo", "preview"]


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


def test_list_selection_and_linked_preview(page):
    keys(page, "Space", "2", "j", "j", "j", "x", "v", "j", "j")
    assert layer(page) == "visual"
    assert page.inner_text("#status-subject") == "3 selected"
    cursor_title = page.get_attribute(".workspace:not([hidden]) [data-row].is-cursor", "data-title")
    assert page.inner_text("[data-preview-title]") == cursor_title
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
    page.wait_for_function("location.pathname === '/library/' && !document.getElementById('ws-library').hidden")
    assert page.locator(".workspace:not([hidden])").count() == 1
    assert page.locator(".workspace").count() == 3  # at most three modes stay in the DOM
    assert page.locator("#ws-library").count() == 1
    page.go_back()  # only completed switches enter the history: back from library is the style guide
    page.wait_for_function("location.pathname === '/ui/' && !document.getElementById('ws-ui').hidden")


def test_insert_layer(page):
    open_mode(page, "collect")
    page.click('[name="title"]')
    assert layer(page) == "insert"
    page.keyboard.type("jk u")
    assert page.input_value('[name="title"]') == "jk u"
    keys(page, "Escape")
    assert layer(page) == "normal"
    assert page.input_value('[name="title"]') == "jk u"


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
