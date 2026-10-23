"""Helpers for the Playwright tests (fixtures are in conftest.py)."""


def open_mode(page, mode):
    page.goto(f"{page.base}/{mode}/")
    page.wait_for_function("window.SPOS && window.SPOS.ctx && window.SPOS.ctx.pane")


def keys(page, *sequence):
    for key in sequence:
        page.keyboard.press(key)


def panes(page):
    return page.eval_on_selector_all(".workspace:not([hidden]) [data-pane]", "els => els.map(e => e.dataset.view)")


def layer(page):
    return page.get_attribute("#shell", "data-layer")


def board_state(page):
    return page.evaluate(
        """(() => { const b = document.querySelector('.workspace:not([hidden]) [data-island=board]').board
          return {layer: b.layer, start: b.line.start, ply: b.line.ply, moves: b.line.moves.map(m => m.san),
                  shapes: b.line.shapes[b.line.ply] || [], squares: (b.line.squares || {})[b.line.ply] || {},
                  title: b.line.title} })()"""
    )


def square(page, name, orientation="white"):
    """Viewport coordinates of a square's centre on the visible board."""
    board = page.locator(".workspace:not([hidden]) [data-view=board] cg-board")
    board.wait_for(state="visible")
    box = board.bounding_box()
    file, rank = "abcdefgh".index(name[0]), int(name[1])
    if orientation == "black":
        file, rank = 7 - file, 9 - rank
    size = box["width"] / 8
    return box["x"] + size * (file + 0.5), box["y"] + size * (8 - rank + 0.5)


def click_square(page, name, **kwargs):
    x, y = square(page, name)
    page.mouse.click(x, y, **kwargs)


def paste(page, text):
    page.evaluate(
        """(text) => { const dt = new DataTransfer(); dt.setData('text/plain', text)
          document.body.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true})) }""",
        text,
    )


def until(page, condition):
    """Wait until a JS condition on the visible board `b` holds, e.g. until(page, "b.line.moves.length === 1")."""
    page.wait_for_function(
        f"(() => {{ const el = document.querySelector('.workspace:not([hidden]) [data-island=board]'); const b = el && el.board; return Boolean(b && ({condition})) }})()",
        timeout=5000,
    )
    return board_state(page)
