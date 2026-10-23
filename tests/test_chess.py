"""Server chess: FEN checks and fixes, paste detection, static boards (spec 06)."""

import json

import pytest

from spaced_positions import chesslogic
from spaced_positions.core.models import UIState

START = chesslogic.START_FEN


def test_legal_start_position():
    check = chesslogic.check_fen(START)
    assert check["ok"] and check["canonical"] == "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"


def test_castling_problem_has_a_fix():
    check = chesslogic.check_fen("4k3/8/8/8/8/8/8/R3K3 w KQ - 0 1")
    assert not check["ok"]
    assert check["problems"] == [{"message": "castling K (rook not on h1) impossible", "fix": "castling"}]
    assert check["fixed"] == "4k3/8/8/8/8/8/8/R3K3 w Q - 0 1"


def test_side_not_to_move_in_check_is_fixed_by_switching_sides():
    check = chesslogic.check_fen("4k3/8/8/8/8/8/8/4RK2 w - - 0 1")  # black is in check, white to move
    assert not check["ok"] and check["problems"][0]["fix"] == "side"
    assert check["fixed"].split()[1] == "b"


def test_unfixable_and_unreadable():
    empty = chesslogic.check_fen("8/8/8/8/8/8/8/8 w - - 0 1")
    assert [p["message"] for p in empty["problems"]] == ["the board is empty", "no white king", "no black king"]
    assert empty["fixed"] is None
    assert chesslogic.check_fen("not a fen")["readable"] is False


def test_canonical_fen_drops_impossible_en_passant():
    assert chesslogic.canonical_fen("4k3/8/8/8/4P3/8/8/4K3 b - e3 0 1") == "4k3/8/8/8/4P3/8/8/4K3 b - -"


@pytest.mark.parametrize(
    ("text", "fen"),
    [
        ("8/8/1KP5/3r4/8/8/8/k7 w - - 0 1", "8/8/1KP5/3r4/8/8/8/k7 w - - 0 1"),
        ("8/8/1KP5/3r4/8/8/8/k7", "8/8/1KP5/3r4/8/8/8/k7 w - - 0 1"),  # placement only
        ("https://lichess.org/analysis/standard/8/8/1KP5/3r4/8/8/8/k7_w_-_-_0_1", "8/8/1KP5/3r4/8/8/8/k7 w - - 0 1"),
        ("https://lichess.org/editor/7K/8/k1P5/7p/8/8/8/8_w_-_-_0_1", "7K/8/k1P5/7p/8/8/8/8 w - - 0 1"),
    ],
)
def test_paste_fen(text, fen):
    result = chesslogic.parse_paste(text)
    assert result["kind"] == "fen" and result["fen"] == fen


def test_paste_pgn_with_two_games():
    pgn = '[White "Morphy"]\n[Black "Duke"]\n[Date "1858.??.??"]\n\n1. e4 e5 2. Nf3 d6 *\n\n[White "A"]\n[Black "B"]\n\n1. d4 *'
    result = chesslogic.parse_paste(pgn)
    assert result["kind"] == "pgn" and result["games"] == 2
    assert result["title"] == "Morphy – Duke 1858"
    assert [m["san"] for m in result["moves"]] == ["e4", "e5", "Nf3", "d6"]
    assert result["moves"][0]["uci"] == "e2e4"


def test_paste_other_things():
    assert chesslogic.parse_paste("1. e4 e5 2. Nf3")["kind"] == "pgn"
    assert chesslogic.parse_paste("8/8/1KP5/3r4/8/8/8/k7\n7K/8/k1P5/7p/8/8/8/8 w")["kind"] == "fens"
    assert chesslogic.parse_paste("https://lichess.org/abcdEFGH")["kind"] == "lichess-game"
    assert chesslogic.parse_paste("hello")["kind"] == "unknown"
    assert chesslogic.parse_paste("   ")["kind"] == "unknown"


def test_board_svg_draws_illegal_diagrams():
    svg = chesslogic.board_svg("8/8/8/8/8/8/8/KK6 w - - 0 1", size=64, light="#ffffff", dark="#000000")
    assert svg.startswith("<svg") and "#000000" in svg


@pytest.mark.django_db
class TestEndpoints:
    def test_fen_check(self, client):
        data = client.get("/chess/fen/", {"fen": "4k3/8/8/8/8/8/8/R3K3 w KQ - 0 1"}).json()
        assert data["fixed"] == "4k3/8/8/8/8/8/8/R3K3 w Q - 0 1"

    def test_paste(self, client):
        data = client.post("/chess/paste/", json.dumps({"text": "8/8/1KP5/3r4/8/8/8/k7"}), content_type="application/json").json()
        assert data["kind"] == "fen"

    def test_board_svg_is_cached_by_colour_hash(self, client):
        response = client.get("/svg/board/", {"fen": START, "size": 64, "t": "abc"})
        assert response.status_code == 200 and response["Content-Type"] == "image/svg+xml"
        assert "immutable" in response["Cache-Control"]
        assert client.get("/svg/board/", {"fen": "x/y"}).status_code == 400

    def test_miniboard_tag_carries_the_theme_hash(self, client):
        html = client.get("/ui/").content.decode()
        assert 'class="miniboard ' in html and "/svg/board/?fen=" in html and "&amp;t=" in html

    def test_lines_are_saved_with_the_mode(self, client):
        subject = {"lines": {"A": {"start": START, "moves": ["e2e4"], "ply": 1, "shapes": {}, "title": ""}}}
        response = client.post("/state/ui/", json.dumps({"subject": subject}), content_type="application/json")
        assert response.status_code == 200
        assert UIState.objects.get(mode="ui").subject == subject
        assert '"e2e4"' in client.get("/ui/").content.decode()


@pytest.mark.parametrize("piece_set", ["cburnett", "kiwen-suwi", "totoy", "fantasy"])
def test_board_svg_in_every_kind_of_piece_set(piece_set):
    svg = chesslogic.board_svg(START, size=64, pieces=piece_set)
    assert svg.count("<symbol") == 12 and svg.count("<use") == 32
    assert f'href="#ps-{piece_set}-wK"' in svg


def test_board_svg_prefixes_ids_inside_pieces():
    svg = chesslogic.board_svg(START, pieces="kiwen-suwi")  # its pieces use clipPath id="a"
    assert 'id="a"' not in svg and 'id="ps-kiwen-suwi-wK-a"' in svg and "url(#ps-kiwen-suwi-wK-a)" in svg


def test_unknown_piece_set_falls_back():
    assert 'href="#ps-cburnett-wK"' in chesslogic.board_svg(START, pieces="nope")


@pytest.mark.django_db
def test_piece_set_preference(client):
    ok = client.post("/cmd/pref.set/", json.dumps({"args": ["piece-set=merida"]}), content_type="application/json")
    assert ok.status_code == 200
    assert 'data-pieces="merida"' in client.get("/ui/").content.decode()
    assert 'href="#ps-merida-wK"' in client.get("/svg/board/", {"fen": START}).content.decode()
    bad = client.post("/cmd/pref.set/", json.dumps({"args": ["piece-set=alpha"]}), content_type="application/json")
    assert bad.status_code == 422  # alpha isn't free to redistribute, so it isn't bundled
