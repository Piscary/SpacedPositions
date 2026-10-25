"""Journeys in a real browser: the Settings mode by keyboard (live theme preview, stepping a value, reset),
binding a key in the keymap editor and using it, and importing settings."""

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
    assert (override.keys, override.command) == ("ctrl+y", "mode.ui")
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
