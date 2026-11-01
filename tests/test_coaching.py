"""Coaching (spec 17 phase 1): a lesson, its homework pack, the student's session and results file, the coach's
table; and `L` and the Coach mode in the browser."""

import json

import pytest

from spaced_positions.coaching import homework as hw
from spaced_positions.coaching.commands import add_to, remove
from spaced_positions.coaching.models import Homework, Lesson
from spaced_positions.library import packs
from spaced_positions.training import puzzles
from spaced_positions.training.models import Attempt
from tests.browser import keys, open_mode
from tests.factories import back_rank


def two_puzzles():
    return [puzzles.create_from_line(back_rank(i), ["d1d8"], title=f"Back rank {i}") for i in range(2)]


@pytest.mark.django_db
def test_lesson_homework_results_and_the_coachs_table():
    one, two = two_puzzles()
    done = add_to(["Back ranks", f"p{one.position.pk}", f"p{two.position.pk}"], {}, {})
    lesson = Lesson.objects.get(title="Back ranks")
    assert lesson.items.count() == 2 and "2 added" in done["message"]
    remove(done["undo"]["args"], {}, {})  # undo
    assert lesson.items.count() == 0
    add_to(["back ranks", f"p{one.position.pk}", f"p{two.position.pk}"], {}, {})  # the same lesson, by its title
    data, name = hw.export(lesson, "Solve both by Friday")
    manifest = packs.read(data).manifest
    block = manifest["homework"]
    assert name.startswith("homework-Back ranks") and block["instructions"] == "Solve both by Friday"
    assert block["positions"] == [str(one.position.uuid), str(two.position.uuid)]
    # the student's side (the same database here: the pack keeps the positions' ids)
    homework = hw.receive_homework(manifest, None)
    assert Homework.objects.count() == 1 and len(hw.cards_of(homework)) == 2
    first, second = (p.cards.get() for p in (one, two))
    Attempt.objects.create(card=first, success=True, ms=4000)
    Attempt.objects.create(card=second, success=False, ms=9000, wrong_move="d1d7")
    Attempt.objects.create(card=second, success=True, ms=5000)
    assert hw.progress(homework) == (2, 2)
    sent = hw.results(homework, "Lena")
    assert [(i["first"], i["tries"], i["wrong"]) for i in sent["items"]] == [(True, 1, ""), (False, 2, "d1d7")]
    # back on the coach's side
    hw.store_results(json.dumps(sent).encode())
    hw.store_results(json.dumps(sent | {"student": "Noah", "items": [sent["items"][0] | {"first": False}, sent["items"][1]]}).encode())
    table = hw.table(lesson.assignments.get())
    assert [s["name"] for s in table["students"]] == ["Lena", "Noah"]
    assert table["columns"][0]["missed"] == 2  # the puzzle both missed first: the first column
    with pytest.raises(ValueError, match="not a results file"):
        hw.store_results(b'{"kind": "pack"}')


@pytest.mark.browser
@pytest.mark.django_db(transaction=True)
def test_l_adds_to_a_lesson_and_the_coach_mode_shows_it(page):
    two_puzzles()
    open_mode(page, "library")
    page.wait_for_selector("#ws-library [data-library-results] [data-row]")
    page.click("#ws-library [data-view=library] .pane__title")
    keys(page, "j", "L")
    page.wait_for_function("document.querySelector('.cmdline__input')?.value === 'lesson-add '")
    page.keyboard.type("Back ranks")
    keys(page, "Enter")
    page.wait_for_function("document.getElementById('status-message').textContent.includes('added to the lesson Back ranks')")
    open_mode(page, "coach")
    page.wait_for_selector("#ws-coach [data-lessons-list] [data-row]")
    page.click("#ws-coach [data-view=lessons] .pane__title")
    keys(page, "j")
    page.wait_for_selector("#ws-coach [data-lesson-list] [data-row]")
    assert page.locator("#ws-coach [data-lesson-list] [data-row]").count() == 1


@pytest.mark.django_db
def test_student_side_full_loop():
    """Student side: import a homework pack (made with coaching.homework.export),
    the homework is received, cards are found, attempts are made, results are written."""
    from spaced_positions.coaching.commands import add_to
    from spaced_positions.coaching.models import Homework
    from spaced_positions.training.models import Attempt
    from tests.factories import back_rank

    # Coach creates a lesson with one puzzle and exports homework
    puzzle = puzzles.create_from_line(back_rank(1), ["d1d8"], title="Back rank")
    add_to(["Back ranks", f"p{puzzle.position.pk}"], {}, {})
    lesson = Lesson.objects.get(title="Back ranks")
    data, name = hw.export(lesson, "Solve it")

    # Student imports the pack
    manifest = packs.read(data).manifest
    homework = hw.receive_homework(manifest, None)
    assert Homework.objects.count() == 1
    assert homework.title == "Back ranks"
    assert homework.instructions == "Solve it"
    assert len(homework.positions) == 1
    assert str(puzzle.position.uuid) in homework.positions

    # Cards are found for the homework
    cards = hw.cards_of(homework)
    assert len(cards) == 1

    # Student solves the puzzle
    card = puzzle.cards.get()
    Attempt.objects.create(card=card, success=True, ms=4000)
    assert hw.progress(homework) == (1, 1)

    # Results are written
    sent = hw.results(homework, "Lena")
    assert sent["kind"] == "results"
    assert sent["student"] == "Lena"
    assert len(sent["items"]) == 1
    assert sent["items"][0]["first"] is True
    assert sent["items"][0]["tries"] == 1
    assert sent["items"][0]["wrong"] == ""

    # Coach receives the results
    result = hw.store_results(json.dumps(sent).encode())
    assert result.student == "Lena"
    assert result.data["items"][0]["first"] is True
