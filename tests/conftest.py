import os
import sys

import pytest

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")  # Playwright's sync API runs an event loop


@pytest.fixture(scope="session")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Chromium not installed: {e}")
        yield browser
        browser.close()


@pytest.fixture
def page(browser, live_server):
    from tests.browser import open_mode

    context = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=live_server.url)
    page = context.new_page()
    if os.environ.get("SPOS_TEST_CPU"):  # SPOS_TEST_CPU=4: a browser 4× slower, as on a busy CI machine
        context.new_cdp_session(page).send("Emulation.setCPUThrottlingRate", {"rate": float(os.environ["SPOS_TEST_CPU"])})
    errors = []
    jitter_on = bool(os.environ.get("SPOS_TEST_JITTER"))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
    # a command may be refused (4xx, the status line says why); a server error is a failure everywhere
    # under jitter, 404s from analysis endpoints are expected: the inspector/puzzle pane fetches
    # may still be in flight when the transaction rolls back at teardown
    def _on_response(r):
        if r.status >= 500 or (r.status >= 400 and "/cmd/" not in r.url):
            if not (jitter_on and r.status == 404 and "/analysis/" in r.url):
                errors.append(f"{r.status} {r.url}")
    page.on("response", _on_response)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.base = live_server.url
    open_mode(page, "ui")
    yield page
    # the usage counts of this test are stored now, not by a request that reaches the server during the next test
    if not page.is_closed():
        page.evaluate("window.SPOS?.usage?.flush()")
        # Under jitter, the panes' requests (inspector, puzzle pane: a 120 ms debounce, then a delayed request and a
        # delayed answer) may still be on their way: let them arrive while this test's data is still there.
        jitter_ms = float(os.environ.get("SPOS_TEST_JITTER", 0)) * 1000
        if jitter_ms:
            page.wait_for_timeout(int(jitter_ms * 2 + 300))
    context.close()
    assert errors == [], errors


@pytest.fixture(autouse=True)
def vocabulary(request):
    """The starter tags (a data migration) for every test with a database: tests that empty the database between
    tests (the browser ones) would otherwise lose them."""
    marker = request.node.get_closest_marker("django_db")
    if marker is None and not {"db", "transactional_db", "live_server"} & set(request.fixturenames):
        return
    request.getfixturevalue("transactional_db" if (marker and marker.kwargs.get("transaction")) or "live_server" in request.fixturenames else "db")
    from spaced_positions.library import vocabulary as vocab
    from spaced_positions.library.models import Tag, TagField

    if not Tag.objects.exists():
        vocab.load(TagField, Tag)


@pytest.fixture(autouse=True)
def fresh_training_data():
    """Every test reads the training data afresh: a rolled-back test can leave the same ids and counts behind, which
    the cache of stats.metrics.load would take for unchanged data."""
    from spaced_positions.stats import metrics

    metrics._cached.clear()
    yield
    metrics._cached.clear()


def pytest_runtest_logreport(report):
    """On GitHub Actions, a failing test becomes an annotation (file, line and the error) on the run's page: the reason
    is visible without downloading the log."""
    if not os.environ.get("GITHUB_ACTIONS") or not report.failed:
        return
    crash = getattr(report.longrepr, "reprcrash", None)
    message = crash.message if crash else str(report.longrepr)
    path, line = (crash.path, crash.lineno) if crash else (report.location[0], (report.location[1] or 0) + 1)
    try:
        path = os.path.relpath(path)
    except ValueError:  # Windows: on another drive than the repository (Python's own files)
        pass
    text = f"{report.nodeid} ({report.when}): {message}"[:3000].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    sys.__stdout__.write(f"::error file={path},line={line},title=test failed::{text}\n")
