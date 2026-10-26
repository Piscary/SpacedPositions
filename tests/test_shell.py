"""Server side of the shell: pages, fragments, layout persistence, server commands, token access."""

import json

import pytest
from django.test import override_settings

from spaced_positions.core import layouts
from spaced_positions.core.models import NamedLayout, Preferences, UIState

pytestmark = pytest.mark.django_db


def post(client, url, body):
    return client.post(url, json.dumps(body), content_type="application/json")


@pytest.mark.parametrize("mode", [m.key for m in layouts.MODES])
def test_every_mode_renders(client, mode):
    response = client.get(f"/{mode}/")
    assert response.status_code == 200
    html = response.content.decode()
    assert 'id="boot"' in html and f'id="ws-{mode}"' in html
    assert html.count('data-pane="') == len(layouts.number_panes(layouts.default_layout(mode)))


def test_unknown_mode_is_404(client):
    assert client.get("/nope/").status_code == 404


@pytest.mark.parametrize("view", list(layouts.VIEWS))
def test_every_view_fragment_renders(client, view):
    response = client.get(f"/v/{view}/", {"pane": "p9", "n": "3", "group": "A", "mode": "ui"})
    assert response.status_code == 200
    html = response.content.decode()
    assert 'data-pane="p9"' in html and f'data-view="{view}"' in html


def test_buttons_show_their_keys(client):
    html = client.get("/ui/").content.decode()
    # The split button in a pane header carries its command and the keys ␣ w v.
    assert 'data-cmd="pane.split.vertical"' in html
    assert '<kbd class="keycap">␣</kbd><kbd class="keycap">w</kbd><kbd class="keycap">v</kbd>' in html


def test_layout_is_saved_and_restored(client):
    layout = layouts.default_layout("home")
    layout["sizes"] = [30, 70]
    for pane in layouts.number_panes(layout):
        pane.pop("n")
    assert post(client, "/state/home/", {"layout": layout, "focus": "p2"}).status_code == 200
    state = UIState.objects.get(mode="home")
    assert state.layout["sizes"] == [30, 70] and state.focus == "p2"
    assert 'data-focus="p2"' in client.get("/home/").content.decode()


@pytest.mark.parametrize(
    "layout",
    [
        {"type": "pane", "id": "p1", "view": "../nope"},  # not a view name (an unknown one is fine: its pane says so)
        {"type": "split", "dir": "diagonal", "sizes": [1], "children": [{"type": "pane", "id": "p1", "view": "board"}]},
        {"type": "split", "dir": "row", "sizes": [1, 2], "children": [{"type": "pane", "id": "p1", "view": "board"}]},
    ],
)
def test_invalid_layouts_are_rejected(client, layout):
    assert post(client, "/state/home/", {"layout": layout}).status_code == 400


def test_theme_set_returns_css_and_undo(client):
    response = post(client, "/cmd/theme.set/", {"args": ["ink"], "context": {}})
    data = response.json()
    assert data["ok"] and "--bg: #16181d" in data["effects"]["theme"]["css"]
    assert data["undo"] == {"command": "theme.set", "args": ["auto"]}
    assert Preferences.current().theme == "ink"
    assert post(client, "/cmd/theme.set/", {"args": ["nope"]}).status_code == 422


def test_pref_set_validates_and_undoes(client):
    data = post(client, "/cmd/pref.set/", {"args": ["main=E2B714"]}).json()
    assert data["ok"] and Preferences.current().tokens == {"main": "#e2b714"}
    assert data["undo"] == {"command": "pref.reset", "args": ["main"]}
    assert "--main: #e2b714" in data["effects"]["theme"]["css"]
    bad = post(client, "/cmd/pref.set/", {"args": ["font-size=99"]})
    assert bad.status_code == 422 and "outside" in bad.json()["message"]
    assert post(client, "/cmd/pref.reset/", {"args": ["main"]}).json()["ok"]
    assert Preferences.current().tokens == {}


def test_enum_tokens_become_css_values(client):
    """`density=compact` must write `--space: 3px`, not the enum name (a bug the screenshots caught)."""
    data = post(client, "/cmd/pref.set/", {"args": ["density=compact"]}).json()
    assert "--space: 3px" in data["effects"]["theme"]["css"]
    assert "--space: 3px" in client.get("/home/").content.decode()


def test_theme_pair_switches_light_and_dark(client):
    data = post(client, "/cmd/ui.themepair/", {"args": [], "context": {"theme": "paper"}}).json()
    assert data["effects"]["theme"]["name"] == "ink"


def test_layout_save(client):
    layout = layouts.default_layout("ui")
    assert post(client, "/cmd/layout.save/", {"args": ["study"], "context": {"mode": "ui"}, "layout": layout}).json()["ok"]
    assert NamedLayout.objects.get(name="study").mode == "ui"
    assert client.get("/layouts/").json()["layouts"][0]["name"] == "study"


def test_quit_only_when_launched(client):
    assert post(client, "/cmd/app.quit/", {}).status_code == 422


@override_settings(SPOS_TOKEN="secret-token")
def test_token_access(client):
    assert client.get("/home/").status_code == 403
    assert client.get("/home/?token=wrong").status_code == 403
    response = client.get("/home/?token=secret-token&x=1")
    assert response.status_code == 302 and response["Location"] == "/home/?x=1"
    assert client.get("/home/").status_code == 200  # the cookie was set
    from django.conf import settings
    assert client.get(f"{settings.STATIC_URL}css/app.css").status_code == 200  # under the build stamp


def test_every_view_has_a_guide_with_bound_keys(client):
    """`?` shows each pane's own guide (spec 04 · Help): one per view, and every key it names is bound."""
    import re
    from pathlib import Path

    from django.conf import settings

    from spaced_positions.core import layouts

    folder = Path(settings.PACKAGE_DIR) / "templates" / "help"
    for view in [*layouts.VIEWS, "search", "pane"]:
        if view == "components":  # the style guide is for developers
            continue
        assert (folder / f"{view}.html").exists(), f"no guide for the view '{view}'"
        html = client.get(f"/help/{view}/").content.decode()
        assert 'class="guide' in html
        assert not re.findall(r">:[\w.]+<", html), f"{view}: a key in the guide has no binding"
