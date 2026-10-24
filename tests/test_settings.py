"""Phase 6 on the server: settings (`:set` for settings next to tokens), user themes, key bindings of one's own and
the settings as one TOML file (export, import, a pasted theme)."""

import json

import pytest

from spaced_positions.core import keymap, settings_io
from spaced_positions.core import settings as user_settings
from spaced_positions.core.models import KeymapOverride, Preferences, UserTheme

pytestmark = pytest.mark.django_db


def run(client, cid, *args, context=None):
    return client.post(f"/cmd/{cid}/", json.dumps({"args": list(args), "context": context or {}}), content_type="application/json").json()


# ── Settings ──────────────────────────────────────────────────────────────────────────────────────────────────


def test_parse_checks_types_and_ranges():
    assert user_settings.parse("training.new-per-day", "35") == (35, None)
    assert user_settings.parse("training.new-per-day", "500")[1]
    assert user_settings.parse("keys.teach", "off") == (False, None)
    assert user_settings.parse("training.storm-pace", "slow") == ("slow", None)
    assert user_settings.parse("training.storm-pace", "glacial")[1]
    assert user_settings.parse("nope.nope", "1")[1]
    assert user_settings.values({})["engine.depth"] == 24


def test_set_a_setting_with_undo_and_reset(client):
    result = run(client, "pref.set", "training.new-per-day=35")
    assert result["ok"] and result["effects"]["settings"]["training.new-per-day"] == 35
    assert Preferences.current().settings == {"training.new-per-day": 35}
    assert result["undo"] == {"command": "pref.set", "args": ["training.new-per-day=20"]}
    assert not run(client, "pref.set", "training.new-per-day=-3")["ok"]
    run(client, "pref.reset", "training.new-per-day")
    assert Preferences.current().settings == {}
    run(client, "pref.set", "main=#336699")  # tokens still go where they went
    assert Preferences.current().tokens == {"main": "#336699"}


def test_settings_rows_and_boot(client):
    run(client, "pref.set", "keys.keycaps=compact")
    html = client.get("/settings/rows/").content.decode()
    assert 'data-set="keys.keycaps"' in html and 'data-value="compact"' in html and "is-changed" in html
    assert 'data-theme="nord"' in html and 'data-set="main"' in html
    page = client.get("/settings/").content.decode()
    assert '"keys.keycaps": "compact"' in page


# ── Themes ────────────────────────────────────────────────────────────────────────────────────────────────────


def test_theme_save_choose_and_delete(client):
    run(client, "theme.set", "nord")
    run(client, "pref.set", "main=#ff8800")
    result = run(client, "theme.save", "My", "nord")
    assert result["ok"] and result["message"].startswith("Theme My nord saved")
    theme = UserTheme.objects.get(name="my-nord")
    assert theme.extends == "nord" and theme.values == {"main": "#ff8800"}
    prefs = Preferences.current()
    assert (prefs.theme, prefs.tokens) == ("my-nord", {})  # the override moved into the theme
    assert "my-nord" in result["effects"]["themes"] and "--main: #ff8800" in result["effects"]["theme"]["css"]
    assert not run(client, "theme.save", "paper")["ok"]  # built-in names stay built-in
    run(client, "theme.delete", "my-nord")
    assert not UserTheme.objects.exists() and Preferences.current().theme == "nord"


def test_theme_export_is_toml_that_imports(client):
    run(client, "theme.set", "sepia")
    run(client, "pref.set", "main=#aa3300")
    text = run(client, "theme.export")["effects"]["copy"]
    assert 'extends = "sepia"' in text and 'main = "#aa3300"' in text
    result = settings_io.import_toml(text)
    assert result["ok"] and UserTheme.objects.get(name="sepia-mine").values == {"main": "#aa3300"}


# ── Keymap ────────────────────────────────────────────────────────────────────────────────────────────────────


def test_map_unmap_and_reset(client):
    result = run(client, "key.map", "space o train.storm 5")
    assert result["ok"], result
    assert keymap.effective()["keymap"]["global"]["space o"] == {"command": "train.storm", "args": ["5"]}
    assert result["undo"] == {"command": "key.reset", "args": ["space", "o"]}
    assert result["effects"]["registry"]["keymap"]["global"]["space o"]["command"] == "train.storm"
    run(client, result["undo"]["command"], *result["undo"]["args"])
    assert "space o" not in keymap.effective()["keymap"]["global"]
    # removing a default binding, in another context
    seq = next(iter(keymap.effective()["keymap"]["view.library"]))
    unmapped = run(client, "key.unmap", f"@view.library {seq}")
    assert unmapped["ok"] and seq not in keymap.effective()["keymap"]["view.library"]
    run(client, unmapped["undo"]["command"], *unmapped["undo"]["args"])
    assert seq in keymap.effective()["keymap"]["view.library"]
    run(client, "key.reset")
    assert not KeymapOverride.objects.exists()


def test_map_refuses_conflicts_and_unknown_keys(client):
    assert not run(client, "key.map", "nosuchkey train.storm")["ok"]
    assert not run(client, "key.map", "space")["ok"]  # no command
    defaults = keymap.effective()["keymap"]["global"]
    prefix = next(seq.split()[0] for seq in defaults if " " in seq)  # a prefix can't become a command too
    result = run(client, "key.map", f"{prefix} train.storm")
    assert not result["ok"]
    assert not KeymapOverride.objects.exists()


def test_keymap_rows_mark_the_users_bindings(client):
    run(client, "key.map", "space o train.storm 5")
    html = client.get("/settings/keymap/").content.decode()
    assert 'data-command="train.storm"' in html and "is-mine" in html


# ── Export and import ─────────────────────────────────────────────────────────────────────────────────────────


def test_export_then_import_on_a_fresh_setup(client):
    run(client, "theme.set", "forest")
    run(client, "pref.set", "density=compact")
    run(client, "pref.set", "training.storm-pace=slow")
    run(client, "key.map", "space o train.storm 5")
    text = client.get("/settings/export/").content.decode()
    assert 'theme = "forest"' in text and "storm-pace" in text and '"space o" = "train.storm 5"' in text
    Preferences.objects.all().delete()
    KeymapOverride.objects.all().delete()
    response = client.post("/settings/import/", json.dumps({"text": text}), content_type="application/json").json()
    assert response["ok"], response
    prefs = Preferences.current()
    assert prefs.theme == "forest" and prefs.tokens.get("density") == "compact" and prefs.settings["training.storm-pace"] == "slow"
    assert KeymapOverride.objects.get(keys="space o").command == "train.storm"


def test_import_skips_what_it_cannot_use(client):
    text = '[settings]\n"training.new-per-day" = 999\n"keys.teach" = false\n[keys]\n"space o" = "no.such.command"\n'
    response = client.post("/settings/import/", json.dumps({"text": text}), content_type="application/json").json()
    assert response["ok"] and len(response["problems"]) == 2
    assert Preferences.current().settings == {"keys.teach": False}
    bad = client.post("/settings/import/", json.dumps({"text": "this is = not [toml"}), content_type="application/json")
    assert bad.status_code == 422


# ── Piece sets of the user's own ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def my_set():
    import shutil

    from spaced_positions.chesslogic import PIECES_DIR
    from spaced_positions.core import user_pieces

    base = user_pieces.folder()
    mine, bad = base / "mine", base / "bad"
    shutil.copytree(PIECES_DIR / "merida", mine)
    (mine / "about.toml").write_text('label = "My Merida"\nauthor = "me"\n')
    shutil.copytree(PIECES_DIR / "merida", bad)
    (bad / "wK.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
    yield mine
    shutil.rmtree(mine)
    shutil.rmtree(bad)


def test_user_piece_sets_from_the_data_folder(client, my_set):
    from spaced_positions.core import user_pieces

    assert list(user_pieces.available()) == ["mine"]  # the unsafe one is left out
    assert user_pieces.available()["mine"]["label"] == "My Merida"
    css = client.get("/pieces/user.css").content.decode()
    assert ':root[data-pieces="mine"] .cg-wrap piece.king.white { background-image: url("/pieces/mine/wK.svg"); }' in css
    svg = client.get("/pieces/mine/wK.svg")
    assert svg.status_code == 200 and svg["Content-Type"] == "image/svg+xml"
    assert client.get("/pieces/bad/wK.svg").status_code == 404 and client.get("/pieces/mine/xx.svg").status_code == 404
    assert run(client, "pref.set", "piece-set=mine")["ok"]
    assert not run(client, "pref.set", "piece-set=bad")["ok"]
    board = client.get("/svg/board/", {"fen": "4k3/8/8/8/8/8/8/4K3 w - - 0 1"}).content.decode()
    assert 'id="ps-mine-wK"' in board
    assert '"mine"' in client.get("/settings/").content.decode()  # boot lists it for the picker


# ── The local engine ──────────────────────────────────────────────────────────────────────────────────────────

FAKE_ENGINE = '''#!{python}
import sys
for line in sys.stdin:
    cmd = line.strip()
    if cmd == "uci":
        print("id name Fakefish", flush=True)
        print("uciok", flush=True)
    elif cmd == "isready":
        print("readyok", flush=True)
    elif cmd.startswith("go"):
        print("info depth 5 seldepth 7 multipv 1 score cp 33 nodes 1000 nps 50000 pv e2e4 e7e5 g1f3", flush=True)
        print("bestmove e2e4", flush=True)
    elif cmd == "quit":
        break
'''


@pytest.fixture
def fake_engine(tmp_path):
    import sys

    from spaced_positions.core import engine_local

    path = tmp_path / "fakefish"
    path.write_text(FAKE_ENGINE.format(python=sys.executable))
    path.chmod(0o755)
    yield path
    if engine_local._engine is not None:
        engine_local._engine.close()
        engine_local._engine = None


def read_until(client, after, text):
    seen = []
    for _ in range(20):
        data = client.get("/engine/local/", {"after": after}).json()
        assert data["ok"], data
        seen += data["lines"]
        after = data["next"]
        if text in seen:
            return seen
    raise AssertionError(seen)


def test_local_engine_through_the_app(client, fake_engine):
    run(client, "pref.set", f"engine.path={fake_engine.parent / 'nothing'}")
    answer = client.post("/engine/local/", json.dumps({"commands": ["uci"]}), content_type="application/json").json()
    assert not answer["ok"] and "is not a program" in answer["message"]
    run(client, "pref.set", f"engine.path={fake_engine}")
    answer = client.post("/engine/local/", json.dumps({"commands": ["uci", "isready"]}), content_type="application/json").json()
    assert answer["ok"] and answer["program"] == "fakefish"
    assert read_until(client, answer["after"], "readyok")[:2] == ["id name Fakefish", "uciok"]
    answer = client.post("/engine/local/", json.dumps({"commands": ["position startpos", "go depth 5"]}), content_type="application/json").json()
    assert read_until(client, answer["after"], "bestmove e2e4")[0].startswith("info depth 5")


def test_imports_never_set_the_engine_program(client):
    text = '[settings]\n"engine.path" = "/bin/sh"\n"engine.depth" = 30\n'
    response = client.post("/settings/import/", json.dumps({"text": text}), content_type="application/json").json()
    assert response["ok"] and Preferences.current().settings == {"engine.depth": 30}
    assert "engine.path" in response["problems"][0]
    run(client, "pref.set", "engine.path=/usr/local/bin/stockfish")
    assert "engine.path" not in client.get("/settings/export/").content.decode()
