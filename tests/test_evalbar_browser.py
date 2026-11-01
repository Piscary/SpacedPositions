"""The eval bar with two sources (spec 15 §4): the game file's evaluation hatched and labelled, the engine's solid,
half a bar each when both are there; Settings → Board → Eval bar picks."""

from pathlib import Path

import pytest

from spaced_positions.library import importer
from tests.browser import keys, open_mode

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]

STUDY = (Path(__file__).parent / "fixtures" / "pgn" / "lichess-study-analysed.pgn").read_text(encoding="utf-8")


def fills(page):
    return page.evaluate("""[...document.querySelectorAll('#ws-analyse [data-evalbar] .evalbar__fill')]
        .map(f => [f.dataset.eval, !f.hidden, f.querySelector('.evalbar__text').textContent, f.querySelector('.evalbar__label')?.textContent ?? null])""")


def test_the_files_evaluation_and_the_engines_side_by_side(page):
    game = importer.run(STUDY, None, ready=True)["games"][0]
    open_mode(page, "analyse")
    page.evaluate("(id) => window.SPOS.analysis.openGame(id)", str(game.uuid))
    page.wait_for_selector("#ws-analyse [data-movetree] .mt-move")
    page.click("#ws-analyse [data-view=moves] .pane__title")
    keys(page, "l")  # 1.e4: lichess +0.18
    page.wait_for_selector("#ws-analyse [data-evalbar]:not([hidden]) [data-eval=file]:not([hidden])")
    assert fills(page) == [["engine", False, "", None], ["file", True, "+0.18", "L"]]
    assert "lichess +0.18" in page.get_attribute("#ws-analyse [data-evalbar]", "title")
    keys(page, "e")  # the engine too: half a bar each
    page.wait_for_selector("#ws-analyse [data-evalbar] [data-eval=engine]:not([hidden])", timeout=30000)
    assert [f[1] for f in fills(page)] == [True, True]
    keys(page, ":")
    page.keyboard.type("set board.evalbar=file")
    keys(page, "Enter")
    page.wait_for_selector("#ws-analyse [data-evalbar] [data-eval=engine][hidden]", state="attached")
    assert fills(page)[1][1]
    keys(page, "e")  # the engine off again
