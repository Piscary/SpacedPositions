"""The usage report for the test group (spec 14 §5): commands counted by how they were started, caught errors, and a
report with counts only."""

import json

import pytest
from django.core.signals import got_request_exception

from spaced_positions.core.models import UsageCount
from spaced_positions.training import puzzles
from spaced_positions.training.models import Attempt, Session
from tests.browser import keys, open_mode
from tests.factories import back_rank


def post(client, url, body):
    return client.post(url, json.dumps(body), content_type="application/json")


def counts():
    return {(u.name, u.source): u.count for u in UsageCount.objects.all()}


@pytest.mark.django_db
def test_only_known_commands_sources_and_caught_errors_are_counted(client):
    body = {"counts": [["train.next", "key", 3], ["train.next", "mouse", 1], ["error.js", "error", 2],
                       ["my secret title", "key", 1], ["train.next", "telepathy", 1], ["train.next", "key", "many"],
                       ["error.server", "error", 5], "nonsense"]}
    assert post(client, "/usage/", body).json()["ok"]
    post(client, "/usage/", {"counts": [["train.next", "key", 2]]})
    assert counts() == {("train.next", "key"): 5, ("train.next", "mouse"): 1, ("error.js", "error"): 2}
    got_request_exception.send(sender=None, request=None)  # a request that failed on the server
    assert counts()[("error.server", "error")] == 1


@pytest.mark.django_db
def test_the_report_has_counts_and_no_texts(client):
    puzzle = puzzles.create_from_line(back_rank(0), ["d1d8"], title="My secret title")
    card = puzzle.cards.get()
    session = Session.objects.create(mode="review", duration_s=600)
    session.ended_at = session.started_at
    session.save()
    Attempt.objects.create(card=card, session=session, success=True, ms=4000)
    Attempt.objects.create(card=card, session=session, success=False, ms=8000)
    post(client, "/usage/", {"counts": [["train.next", "key", 4], ["train.next", "hint", 1], ["library.tag", "mouse", 2]]})
    response = client.get("/usage/report/")
    assert response["Content-Disposition"].startswith('attachment; filename="spaced-positions-usage-')
    text = response.content.decode()
    assert "My secret title" not in text and "d1d8" not in text
    assert "Training per day" in text and "Sessions: 1" in text and "by mode: review 1" in text
    assert "minutes per session: median 10, longest 10" in text
    assert "First solved puzzle:" in text and "days used: 1" in text
    rows = {line.split()[0]: line.split()[1:] for line in text.splitlines() if line.startswith(("train.next", "library.tag"))}
    assert rows == {"train.next": ["4", "0", "1", "0"], "library.tag": ["0", "2", "0", "0"]}  # keys, clicks, hints, cmdline
    day = [line for line in text.splitlines() if line[:4].isdigit() and "-W" not in line][0].split()
    assert day[1:4] == ["2", "1", "1"]  # puzzles, solved, missed


@pytest.mark.browser
@pytest.mark.django_db(transaction=True)
def test_keys_and_clicks_are_counted_and_the_report_downloads(page):
    open_mode(page, "settings")
    page.click("#ws-settings [data-view=settings] .pane__title")
    keys(page, "Space", "l")  # a key
    page.wait_for_function("window.SPOS.ctx.mode === 'library'")
    page.click(".appbar [data-mode-tab=settings]")  # a click
    page.wait_for_function("window.SPOS.ctx.mode === 'settings'")
    page.evaluate("window.SPOS.usage.flush()")  # awaited: the counts are stored
    with page.expect_download() as download:
        page.click("#ws-settings [data-cmd='app.testreport']")
    assert download.value.suggested_filename.startswith("spaced-positions-usage-")
    found = counts()
    assert found[("mode.library", "key")] == 1 and found[("mode.settings", "mouse")] == 1


@pytest.mark.browser
@pytest.mark.django_db(transaction=True)
def test_a_menu_entry_chosen_by_key_counts_as_a_key(page):
    open_mode(page, "settings")
    page.click("#ws-settings [data-view=settings] .pane__title")
    keys(page, "Space", "w", "w")  # the pane menu; its first entry is the search
    page.wait_for_selector(".menu")
    keys(page, "Enter")
    page.wait_for_function("document.activeElement.matches('#ws-settings [data-search]')")
    keys(page, "Escape")
    page.evaluate("window.SPOS.usage.flush()")
    found = counts()
    assert found[("search.open", "key")] == 1 and ("search.open", "mouse") not in found
