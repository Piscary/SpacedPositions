"""The two marks on positions (GitHub #5, #6): a diagram and a broken puzzle's flag go on and off again, with undo; an
illegal diagram stays one; Collect's merge sets the diagram mark of a saved position; the Details pane's switches."""

import json

import pytest

from spaced_positions.library import marks
from spaced_positions.training import puzzles
from spaced_positions.training.models import Position, Puzzle
from spaced_positions.training.selection import pool
from tests.factories import back_rank


def post(client, url, body):
    return client.post(url, json.dumps(body), content_type="application/json")


def body(*ids, c="positions"):
    return {"c": c, "ids": list(ids)}


@pytest.mark.django_db
def test_a_diagram_goes_on_and_off_and_undo_puts_it_back():
    puzzle = puzzles.create_from_line(back_rank(0), ["d1d8"])
    ref = f"p{puzzle.position.pk}"
    on = marks.diagram([], {}, body(ref))
    assert Position.objects.get().diagram and "shown, not trained" in on["message"]
    assert not pool().exists()  # a diagram is never trained
    off = marks.diagram([], {}, body(ref))  # the same key again: off
    assert not Position.objects.get().diagram and "trains again" in off["message"]
    marks.diagram(off["undo"]["args"], {}, {})
    assert Position.objects.get().diagram
    marks.diagram(["off"], {}, body(ref))
    marks.diagram(["off"], {}, body(ref))  # off when it is off: stays off
    assert not Position.objects.get().diagram


@pytest.mark.django_db
def test_an_illegal_diagram_stays_one():
    illegal = Position.objects.create(fen="8/8/8/8/8/8/8/KK5k w - - 0 1", canonical="x", diagram=True)
    with pytest.raises(Exception, match="not legal"):
        marks.diagram(["off"], {}, body(f"p{illegal.pk}"))
    assert Position.objects.get(pk=illegal.pk).diagram


@pytest.mark.django_db
def test_the_flag_comes_off_again(client):
    puzzle = puzzles.create_from_line(back_rank(0), ["d1d8"])
    on = marks.flag([], {}, body(str(puzzle.uuid), c="puzzles"))
    assert Puzzle.objects.get().flagged and "! again" in on["message"]
    off = marks.flag([], {}, body(f"p{puzzle.position.pk}"))  # from the position (the Library, Analyse, Details)
    assert not Puzzle.objects.get().flagged
    marks.flag(off["undo"]["args"], {}, {})
    assert Puzzle.objects.get().flagged
    html = client.get("/lib/results/", {"q": "is:flagged"}).content.decode()
    assert f'data-row="p{puzzle.position.pk}"' in html and "flagged" in html
    details = client.get("/lib/details/", {"ref": f"p{puzzle.position.pk}"}).content.decode()
    assert 'data-toggle-cmd="library.flag"' in details and 'data-toggle-cmd="library.diagram"' in details
    with pytest.raises(Exception, match="nothing selected"):
        marks.flag([], {}, body())


@pytest.mark.django_db
def test_collect_merge_sets_the_diagram_mark(client):
    first = {"start": back_rank(0), "moves": ["d1d8"], "ready": True}
    assert post(client, "/lib/collect/save/", first).json()["ok"]
    merged = post(client, "/lib/collect/save/", first | {"diagram": True, "how": "merge"}).json()
    assert merged["ok"] and "now a diagram" in merged["message"] and Position.objects.get().diagram
    merged = post(client, "/lib/collect/save/", first | {"diagram": False, "how": "merge"}).json()
    assert "no longer a diagram" in merged["message"] and not Position.objects.get().diagram


# ── In the browser: the mouse ─────────────────────────────────────────────────────────────────────────────────────

from tests.browser import keys, open_mode  # noqa: E402


@pytest.mark.browser
@pytest.mark.django_db(transaction=True)
def test_mouse_right_click_a_row_to_a_new_lesson_then_switch_its_diagram_mark(page):
    """A right click on a Library row → To a lesson → the line suggests, a click on 'a new lesson' makes it; Ctrl + click
    selects; the Details pane's switch makes the position a diagram and back."""
    for i in range(2):
        puzzles.create_from_line(back_rank(i), ["d1d8"], title=f"Back rank {i}")
    open_mode(page, "library")
    rows = "#ws-library [data-library-results] [data-row]"
    page.wait_for_selector(rows)
    page.locator(rows).nth(0).click()
    page.locator(rows).nth(1).click(modifiers=["ControlOrMeta"])
    page.wait_for_function(f"document.querySelectorAll('{rows}.is-selected').length === 1")
    page.locator(rows).nth(1).click(button="right")
    page.click(".menu >> text=To a lesson")
    page.wait_for_function("document.querySelector('.cmdline__input')?.value === 'lesson-add '")
    page.keyboard.type("Endgames")
    page.click(".cmdline__row >> text=a new lesson")
    page.wait_for_function("document.getElementById('status-message').textContent.includes('added to the lesson Endgames')")
    from spaced_positions.coaching.models import Lesson

    assert Lesson.objects.get().items.count() == 1  # the selected row only
    page.locator(rows).nth(0).click(button="right")
    page.click(".menu >> text=Details")
    switch = "#ws-library [data-details-list] [data-row=is-diagram] .toggle"
    page.wait_for_selector(switch)
    page.click(switch)
    page.wait_for_function(f"document.querySelector('{switch}')?.getAttribute('aria-pressed') === 'true'")
    assert Position.objects.filter(diagram=True).count() == 1
    page.click("[data-cmd=undo]")  # ↶ in the app bar
    page.wait_for_function(f"document.querySelector('{switch}')?.getAttribute('aria-pressed') === 'false'")
    keys(page, "Escape")
