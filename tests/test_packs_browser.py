"""Journeys: making a pack in the Library (`:pack-export`) and importing one (the file chooser, the preview
with its licence, ↵), then training it."""

import json
import zipfile

import pytest

from spaced_positions.library import packs
from spaced_positions.library.models import Pack, PackExport
from spaced_positions.training.models import Position, Puzzle
from tests.browser import keys, open_mode
from tests.test_library_browser import library, positions  # noqa: F401
from tests.test_packs import coach, forget  # noqa: F401

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]


def test_make_a_pack_for_a_student(page, positions):
    library(page)
    with page.expect_download() as download:
        keys(page, ":")
        page.keyboard.type('pack-export "Forks and pins" for=Ben')
        keys(page, "Enter")
    assert download.value.suggested_filename == "forks-and-pins-v1-for-ben.sppack"
    page.wait_for_function("document.getElementById('status-message').textContent.startsWith('Pack Forks and pins v1 for Ben: 3 positions')")
    log = PackExport.objects.get()
    assert (log.student, log.positions, Pack.objects.get().query) == ("Ben", 3, "")


def test_import_a_pack_and_train_it(page, coach, tmp_path):
    pack = Pack.objects.create(title="Back ranks", description="Three classics")
    data, _ = packs.build(Position.objects.filter(pk__in=[p.pk for p in coach]), pack, author="Coach C", student="Ben")
    forget(coach)
    path = tmp_path / "back-ranks.sppack"
    path.write_bytes(data)
    open_mode(page, "library")
    with page.expect_file_chooser() as chooser:
        keys(page, ":")
        page.keyboard.type("pack-import")
        keys(page, "Enter")
    chooser.value.set_files(str(path))
    page.wait_for_selector(".packview >> text=from Coach C for Ben")
    assert "3 new" in page.inner_text(".packview") and "Licence:" in page.inner_text(".packview")
    keys(page, "Enter")
    page.wait_for_function("document.getElementById('status-message').textContent.startsWith('Pack Back ranks: 3 new, 3 puzzles')")
    page.wait_for_function("window.SPOS.library.state().q.startsWith('src:s')")
    assert Position.objects.filter(pack__isnull=False).count() == 3
    open_mode(page, "train")
    page.wait_for_function("window.SPOS.train && document.querySelector('[data-train-launcher]:not([hidden])')")
    keys(page, "r")
    page.wait_for_function("window.SPOS.train.state().state === 'solving'")
    keys(page, "s")
    page.wait_for_function("window.SPOS.train.state().state === 'feedback'")
    assert "Back ranks (from Coach C for Ben)" in page.inner_text("[data-fb-source]")


def test_the_starter_pack_from_the_first_run_screen(page):
    """An empty library: Welcome offers the starter pack (s); it is previewed, imported, and its puzzles train like
    any other (the opponent's move is played first, then you solve)."""
    from spaced_positions.library import starter

    open_mode(page, "home")
    page.wait_for_selector("[data-view=today] .home__welcome")
    page.click("[data-view=today] .pane__title")
    keys(page, "s")
    page.wait_for_selector(".packview >> text=Starter pack")
    assert "CC0" in page.inner_text(".packview")
    keys(page, "Enter")
    page.wait_for_function("document.getElementById('status-message').textContent.includes('Pack Starter pack')", timeout=60000)
    total = json.loads(zipfile.ZipFile(starter.PATH).read("manifest.json"))["puzzles"]
    assert Puzzle.objects.filter(active=True).count() == total
    # a Review: the first card is a starter puzzle, solved with its line
    keys(page, "Space", "r")
    page.wait_for_function("window.SPOS.train && window.SPOS.train.state().state === 'solving'")
    line = page.evaluate("window.SPOS.train.puzzle().line")
    page.evaluate(
        """async (line) => { const b = document.querySelector('#ws-train [data-island=board]').board
          const { Chess } = await import(new URL('../vendor/chess.js', document.querySelector('script[type=module]').src).href); const c = new Chess(b.line.start)
          for (let i = 0; i < line.length; i += 2) {
            b.submit(c.move({from: line[i].slice(0,2), to: line[i].slice(2,4), promotion: line[i][4]}))
            await new Promise(r => setTimeout(r, 500))
            if (line[i+1]) c.move({from: line[i+1].slice(0,2), to: line[i+1].slice(2,4), promotion: line[i+1][4]}) } }""",
        line,
    )
    page.wait_for_function("window.SPOS.train.state().solved === 1", timeout=15000)
