"""Board journeys in a real browser (spec 06): moving, stepping, drawing, the square tool, typed moves,
promotion, the board editor with validation and fixes, paste detection, persistence, accessibility."""

from pathlib import Path

import pytest

from tests.browser import board_state, click_square, keys, layer, open_mode, paste, square, until

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]

AXE = Path(__file__).parent / "vendor" / "axe.min.js"


@pytest.fixture
def board(page):
    keys(page, "Space", "3")  # the style guide's board (linked to the demo list)
    assert page.inner_text("#status-pane").startswith("3")
    return page


def test_click_move_and_step(board):
    click_square(board, "e2")
    click_square(board, "e4")
    until(board, "b.line.moves.length === 1")
    assert board_state(board)["moves"] == ["e4"]
    keys(board, "h")
    assert board_state(board)["ply"] == 0
    keys(board, "l")
    assert board_state(board)["ply"] == 1
    keys(board, "u")  # undo the move
    assert board_state(board)["moves"] == []


def test_drag_move_and_illegal_move_snaps_back(board):
    x1, y1 = square(board, "g1")
    x2, y2 = square(board, "f3")
    board.mouse.move(x1, y1)
    board.mouse.down()
    board.mouse.move(x2, y2, steps=5)
    board.mouse.up()
    assert until(board, "b.line.moves.length === 1")["moves"] == ["Nf3"]
    click_square(board, "e7")
    click_square(board, "e3")  # illegal for black
    board.wait_for_timeout(100)
    assert board_state(board)["moves"] == ["Nf3"]


def test_typed_moves_in_english_and_german(board):
    keys(board, "i")
    assert layer(board) == "entry"
    for text in ("e4", "e5", "Sf3", "Nc6"):
        for ch in text:
            board.keyboard.press(ch)
        keys(board, "Enter")
    until(board, "b.line.moves.length === 4")
    keys(board, "Escape")
    assert layer(board) == "normal"
    assert board_state(board)["moves"] == ["e4", "e5", "Nf3", "Nc6"]


def test_arrows_and_square_tool(board):
    x1, y1 = square(board, "e2")
    x2, y2 = square(board, "e4")
    board.keyboard.down("Shift")
    board.mouse.move(x1, y1)
    board.mouse.down(button="right")
    board.mouse.move(x2, y2, steps=5)
    board.mouse.up(button="right")
    board.keyboard.up("Shift")
    shapes = until(board, "(b.line.shapes[b.line.ply] || []).length === 1")["shapes"]
    assert [(s["orig"], s["dest"], s["brush"]) for s in shapes] == [("e2", "e4", "red")]
    keys(board, "q")
    click_square(board, "d4", button="right")
    assert board_state(board)["squares"] == {"d4": "green"}
    keys(board, "Backspace")
    state = board_state(board)
    assert state["shapes"] == [] and state["squares"] == {}


def test_promotion_asks_for_the_piece(board):
    paste(board, "8/1P6/8/8/8/8/8/k1K5 w - - 0 1")
    board.wait_for_selector("#status-message .keyhint")
    keys(board, "b")
    board.wait_for_function("document.querySelector('[data-island=board]').board.line.start.startsWith('8/1P6')")
    click_square(board, "b7")
    click_square(board, "b8")
    board.wait_for_selector(".menu")
    keys(board, "n")
    assert until(board, "b.line.moves.length === 1")["moves"] == ["b8=N"]


def test_board_editor_validates_and_fixes(board):
    keys(board, "S")
    assert layer(board) == "setup" and board_state(board)["layer"] == "setup"
    click_square(board, "h1", button="right")  # remove the h1 rook: castling K becomes impossible
    board.wait_for_selector(".board__problems")
    assert "castling K" in board.inner_text(".board__problems")
    keys(board, "S")  # can't leave with an illegal position
    assert board_state(board)["layer"] == "setup"
    keys(board, "a")  # fix
    board.wait_for_function("!document.querySelector('.board__problems')")
    keys(board, "6")
    board.keyboard.down("Shift")
    click_square(board, "e4")  # Shift: a second black king, illegal again
    board.keyboard.up("Shift")
    board.wait_for_selector(".board__problems")
    click_square(board, "e4", button="right")
    board.wait_for_function("!document.querySelector('.board__problems')")
    keys(board, "S")
    state = until(board, "b.layer === 'play'")
    assert layer(board) == "normal"
    assert state["start"] == "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBN1 w Qkq - 0 1"
    keys(board, "u")
    assert until(board, "b.line.start.endsWith('RNBQKBNR w KQkq - 0 1')")


def test_diagram_keeps_an_illegal_position(board):
    keys(board, "S", "X", "D")  # empty board, as a diagram
    board.wait_for_selector(".board__problems")
    keys(board, "S")
    state = until(board, "b.layer === 'play'")
    assert state["start"].startswith("8/8/8/8/8/8/8/8")
    assert "not playable" in board.inner_text("[data-board-status]")


def test_paste_pgn_lichess_and_rubbish(board):
    paste(board, '[White "Morphy"]\n[Black "Duke"]\n\n1. e4 e5 2. Nf3 d6 3. d4 Bg4 *')
    board.wait_for_selector("#status-message .keyhint")
    assert "PGN · Morphy – Duke · 6 moves" in board.inner_text("#status-message")
    keys(board, "b")
    state = until(board, "b.line.moves.length === 6")
    assert state["moves"] == ["e4", "e5", "Nf3", "d6", "d4", "Bg4"] and state["title"] == "Morphy – Duke"
    paste(board, "https://lichess.org/analysis/8/8/1KP5/3r4/8/8/8/k7_w_-_-_0_1")
    board.wait_for_selector("#status-message .keyhint")
    keys(board, "b")
    assert until(board, "b.line.start.startsWith('8/8/1KP5')")["start"] == "8/8/1KP5/3r4/8/8/8/k7 w - - 0 1"
    paste(board, "no chess here")
    board.wait_for_function("document.getElementById('status-message').dataset.kind === 'error'")


def test_offer_keys_for_later_phases_are_disabled(board):
    paste(board, "8/8/1KP5/3r4/8/8/8/k7 w - - 0 1")
    board.wait_for_selector("#status-message .keyhint")
    keys(board, "a")  # analyse: phase 3
    assert "arrives in phase 3" in board.inner_text("#status-message")


def test_copy_fen_and_pgn(board):
    click_square(board, "d2")
    click_square(board, "d4")
    until(board, "b.line.moves.length === 1")
    keys(board, "y")
    board.wait_for_function("document.getElementById('status-message').textContent === 'Copied FEN'")
    assert board.evaluate("navigator.clipboard.readText()") == "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1"
    keys(board, "Y")
    board.wait_for_function("document.getElementById('status-message').textContent === 'Copied PGN'")
    assert board.evaluate("navigator.clipboard.readText()") == "1. d4 *"


def test_line_survives_a_reload(board):
    click_square(board, "c2")
    click_square(board, "c4")
    until(board, "b.line.moves.length === 1")
    board.wait_for_timeout(800)  # lines are saved 600 ms after the last change
    open_mode(board, "ui")
    assert until(board, "b.line.moves.length === 1")["moves"] == ["c4"]


def test_flip_keeps_moves_working(board):
    keys(board, "f")
    x, y = square(board, "e2", orientation="black")
    board.mouse.click(x, y)
    x, y = square(board, "e4", orientation="black")
    board.mouse.click(x, y)
    assert until(board, "b.line.moves.length === 1")["moves"] == ["e4"]


def test_accessibility_of_the_style_guide(page):
    """axe-core (spec 07 §8, test 6): no serious or critical violations on the style guide."""
    page.add_script_tag(path=str(AXE))
    result = page.evaluate(
        """async () => {
          const r = await axe.run(document, {resultTypes: ['violations'], preload: false})
          return r.violations.filter(v => ['serious', 'critical'].includes(v.impact))
            .map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.slice(0, 3).map(n => n.target.join(' '))}))
        }"""
    )
    assert result == [], result


def test_piece_set_picker_previews_keeps_and_undoes(page):
    before = page.get_attribute("img.miniboard", "src")
    keys(page, "Space", "u", "p")
    page.wait_for_selector(".menu")
    keys(page, "j")
    assert page.get_attribute("html", "data-pieces") == "merida"  # live preview
    keys(page, "Escape")
    assert page.get_attribute("html", "data-pieces") == "cburnett"  # Esc reverts
    keys(page, "Space", "u", "p")
    page.wait_for_selector(".menu")
    keys(page, "3")
    page.wait_for_function("document.getElementById('status-message').textContent.startsWith('piece-set = chessnut')")
    assert page.get_attribute("html", "data-pieces") == "chessnut"
    assert page.get_attribute("img.miniboard", "src") != before  # MiniBoards are redrawn in the new set
    assert page.get_attribute(".pieceset[aria-pressed=true]", "data-args") == "chessnut"
    keys(page, "u")
    page.wait_for_function("document.documentElement.dataset.pieces === 'cburnett'")


def test_piece_set_from_the_command_line(page):
    keys(page, ":")
    page.keyboard.type("pieces spa")
    keys(page, "Enter")
    page.wait_for_function("document.documentElement.dataset.pieces === 'spatial'")
