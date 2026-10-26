"""Journeys in a real browser: the Settings mode by keyboard (live theme preview, stepping a value, reset),
binding a key in the keymap editor and using it, and importing settings."""

import sys
from pathlib import Path

import pytest

from spaced_positions.core.models import KeymapOverride, Preferences
from tests.browser import keys, open_mode

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]

AXE = Path(__file__).parent / "vendor" / "axe.min.js"


def settings(page):
    open_mode(page, "settings")
    page.wait_for_selector("#ws-settings [data-settings-list] [data-row]")
    page.click("#ws-settings [data-view=settings] .pane__title")
    return page


def cursor(page):
    return page.get_attribute("#ws-settings [data-settings-list] .is-cursor", "data-row")


def test_theme_preview_and_choice(page):
    settings(page)
    before = page.evaluate("document.getElementById('theme').textContent")
    while cursor(page) != "theme:forest":
        keys(page, "j")
    page.wait_for_function("document.getElementById('theme').textContent.includes('#5bd6c5')")  # Forest, previewed
    keys(page, "j")
    if cursor(page).startswith("theme:"):
        keys(page, "G")
    page.wait_for_function("(b) => document.getElementById('theme').textContent === b", arg=before)  # off the themes: back
    keys(page, "g", "g")
    while cursor(page) != "theme:forest":
        keys(page, "j")
    keys(page, "Enter")
    page.wait_for_function("document.querySelector('#ws-settings [data-theme=forest]')?.classList.contains('is-on')")
    assert Preferences.current().theme == "forest"


def test_step_a_value_and_reset_it(page):
    settings(page)
    page.fill("#ws-settings [data-settings-filter]", "storm pace")
    keys(page, "Escape")
    page.click("#ws-settings [data-row='training.storm-pace']")
    keys(page, "l")
    page.wait_for_selector("#ws-settings [data-row='training.storm-pace'][data-value='slow'].is-changed")
    assert Preferences.current().settings == {"training.storm-pace": "slow"}
    keys(page, "u")
    page.wait_for_selector("#ws-settings [data-row='training.storm-pace'][data-value='medium']")
    keys(page, "l", "l")
    page.wait_for_selector("#ws-settings [data-row='training.storm-pace'][data-value='fast']")
    keys(page, "Backspace")
    page.wait_for_selector("#ws-settings [data-row='training.storm-pace']:not(.is-changed)")
    assert Preferences.current().settings == {}


def test_bind_a_key_in_the_keymap_editor_and_use_it(page):
    settings(page)
    page.click("#ws-settings [data-view=keymap] .pane__title")
    page.fill("#ws-settings [data-keymap-filter]", "style guide")
    keys(page, "Escape")
    page.click("#ws-settings [data-keymap-list] [data-row='mode.ui']")
    keys(page, "Enter", "Control+y", "Enter")
    page.wait_for_selector("#ws-settings [data-row='mode.ui'] .keymap__binding.is-mine")
    override = KeymapOverride.objects.get()
    # Ctrl is the main modifier off the Mac: there the app stores it as mod (⌘ on a Mac, Ctrl elsewhere)
    expected = "ctrl+y" if sys.platform == "darwin" else "mod+y"
    assert (override.keys, override.command) == (expected, "mode.ui")
    keys(page, "Control+y")
    page.wait_for_function("window.SPOS.ctx.mode === 'ui'")


def test_import_settings_from_the_data_section(page):
    settings(page)
    page.fill("#ws-settings [data-settings-import] textarea", '[settings]\n"keys.keycaps" = "off"\n')
    page.focus("#ws-settings [data-settings-import] textarea")
    keys(page, "ControlOrMeta+Enter")
    page.wait_for_function("document.getElementById('status-message').textContent.startsWith('Imported 1 setting')")
    page.wait_for_selector("html[data-keycaps='off']")


def test_settings_accessibility(page):
    settings(page)
    page.add_script_tag(path=str(AXE))
    result = page.evaluate(
        """async () => {
          const r = await axe.run(document, {resultTypes: ['violations'], preload: false})
          return r.violations.filter(v => ['serious', 'critical'].includes(v.impact))
            .map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.slice(0, 3).map(n => n.target.join(' '))}))
        }"""
    )
    assert result == [], result


def test_enter_lists_the_choices_and_finds_one_by_its_meaning(page):
    """↵ on a choice opens `:set name=` with every choice listed by name; typing what it means is enough."""
    settings(page)
    page.fill("#ws-settings [data-settings-filter]", "piece letters")
    keys(page, "Escape")
    page.click("#ws-settings [data-row='board.letters']")
    keys(page, "Enter")
    page.wait_for_selector(".cmdline__row >> text=Deutsch")
    rows = page.eval_on_selector_all(".cmdline__row", "els => els.map(e => e.textContent)")
    assert len(rows) == 4 and rows[0].startswith("en"), rows
    assert any("now" in r for r in rows), rows  # the current value is marked
    page.keyboard.type("ger")
    page.wait_for_function("document.querySelectorAll('.cmdline__row').length === 1")
    keys(page, "Enter")
    page.wait_for_selector("#ws-settings [data-row='board.letters'].is-changed")
    assert Preferences.current().settings == {"board.letters": "de"}


def test_the_cursor_stays_on_the_setting_you_change(page):
    """h / l keep the cursor on the row, also when the new language reloads the page (with the search kept)."""
    settings(page)
    page.click("#ws-settings [data-row='training.storm-pace']", position={"x": 4, "y": 4})  # the row, not one of its choices
    keys(page, "l")
    page.wait_for_selector("#ws-settings [data-row='training.storm-pace'].is-changed")
    page.wait_for_timeout(300)
    assert cursor(page) == "training.storm-pace"
    page.fill("#ws-settings [data-settings-filter]", "language")
    keys(page, "Escape")
    page.click("#ws-settings [data-row='ui.language']", position={"x": 4, "y": 4})
    keys(page, "l")  # auto → en
    page.wait_for_function("document.querySelector('#ws-settings [data-row=\\'ui.language\\']')?.dataset.value === 'en'")
    page.wait_for_timeout(1000)  # the page reloads for a new language
    page.wait_for_selector("#ws-settings [data-row='ui.language']")
    keys(page, "l")  # en → de
    page.wait_for_function("document.documentElement.lang === 'de'")
    page.wait_for_selector("#ws-settings [data-row='ui.language']")
    page.wait_for_function("document.querySelector('#ws-settings [data-settings-list] .is-cursor')?.dataset.row === 'ui.language'")
    assert page.input_value("#ws-settings [data-settings-filter]") == "language"
    assert page.evaluate("window.SPOS.ctx.pane.view") == "settings"
    keys(page, "h")  # back to English, the cursor still there
    page.wait_for_function("document.documentElement.lang === 'en'")
    page.wait_for_function("document.querySelector('#ws-settings [data-settings-list] .is-cursor')?.dataset.row === 'ui.language'")


def test_a_click_on_a_choice_keeps_the_cursor_there(page):
    """Clicking a setting's choice puts the cursor on that setting; after the new language reloads the page it is
    still there."""
    settings(page)
    page.wait_for_selector("#ws-settings [data-row='ui.language']")
    page.click("#ws-settings [data-row='ui.language'] [data-args='ui.language=de']")
    page.wait_for_function("document.documentElement.lang === 'de'")
    page.wait_for_selector("#ws-settings [data-row='ui.language']")
    page.wait_for_function("document.querySelector('#ws-settings [data-settings-list] .is-cursor')?.dataset.row === 'ui.language'")
    keys(page, "h")  # and the keys go on from there
    page.wait_for_function("document.documentElement.lang === 'en'")
    page.wait_for_function("document.querySelector('#ws-settings [data-settings-list] .is-cursor')?.dataset.row === 'ui.language'")


def test_h_and_l_step_a_number_with_a_unit(page):
    """board-border is in pixels: l steps the number, the setting takes it (no "px" in the value)."""
    settings(page)
    page.fill("#ws-settings [data-settings-filter]", "frame")
    keys(page, "Escape")
    page.click("#ws-settings [data-row='board-border']", position={"x": 4, "y": 4})
    before = float(page.get_attribute("#ws-settings [data-row='board-border']", "data-value"))
    keys(page, "l")
    page.wait_for_selector("#ws-settings [data-row='board-border'].is-changed")
    assert Preferences.current().tokens["board-border"] == before + 1
    keys(page, "h")
    page.wait_for_function(f"Number(document.querySelector(\"#ws-settings [data-row='board-border']\").dataset.value) === {before}")
    keys(page, "Backspace")  # ⌫: the theme's value again
    page.wait_for_selector("#ws-settings [data-row='board-border']:not(.is-changed)")
