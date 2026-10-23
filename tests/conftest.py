import os

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
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
    page.on("response", lambda r: errors.append(f"{r.status} {r.url}") if r.status >= 400 and "/cmd/" not in r.url else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.base = live_server.url
    open_mode(page, "ui")
    yield page
    context.close()
    assert errors == [], errors
