"""Analyse journeys in a real browser (spec 04 · Analyse): opening a position, stepping through the move tree,
adding variations, annotations, comments, undo across a reload, the engine, puzzles set up from the analysis, and
the ways in (paste, Train)."""

from pathlib import Path

import pytest

from spaced_positions.analysis import puzzles as analysis_puzzles
from spaced_positions.analysis import tree
from spaced_positions.analysis.models import Node
from spaced_positions.training.models import Position, Puzzle
from tests.browser import click_square, keys, open_mode, paste

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
RUY = ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"]
AXE = Path(__file__).parent / "vendor" / "axe.min.js"


@pytest.fixture
def ruy():
    position = tree.create_position(START, RUY, title="Ruy Lopez")
    tree.play(tree.root(position).kids.get(san="e4"), "c7c5")
    return position


def analyse(page, position, node=None):
    open_mode(page, "analyse")
    page.evaluate("([pid, node]) => window.SPOS.analysis.open(pid, {node})", [str(position.uuid), node])
    page.wait_for_selector("#ws-analyse [data-island=moves] [data-movetree]")
    focus(page, "moves")


def focus(page, view):
    page.click(f"#ws-analyse [data-view={view}] .pane__header .pane__title")


def cursor_san(page):
    return page.evaluate("""(() => { const el = document.querySelector('#ws-analyse .mt-move.is-cursor')
      return el ? el.querySelector('.mt-san').textContent : null })()""")


def board_ply(page):
    return page.evaluate("document.querySelector('#ws-analyse [data-island=board]').board.line.ply")


def wait_status(page, text):
    page.wait_for_function(f"document.getElementById('status-message').textContent.includes({text!r})", timeout=5000)


def test_open_with_the_command_line_and_step_through_variations(page, ruy):
    open_mode(page, "analyse")
    keys(page, ":")
    page.keyboard.type("analyse Ruy")
    page.wait_for_selector(".cmdline__row >> text=Ruy Lopez")
    keys(page, "Enter")
    page.wait_for_selector("#ws-analyse [data-movetree]")
    focus(page, "moves")
    assert cursor_san(page) is None and board_ply(page) == 0
    keys(page, "l", "l")
    assert cursor_san(page) == "e5" and board_ply(page) == 2
    keys(page, "j")  # the other answer to e4
    assert cursor_san(page) == "c5"
    keys(page, "g", "g")
    assert board_ply(page) == 0
    keys(page, "G")
    assert cursor_san(page) == "Bb5" and board_ply(page) == 5
    keys(page, "h")
    assert cursor_san(page) == "Nc6"
    page.click("#ws-analyse .mt-move >> text=c5")
    assert cursor_san(page) == "c5"
    # The Inspector follows the cursor.
    page.wait_for_selector("#ws-analyse [data-inspector] >> text=c5")


def test_moves_annotations_and_undo_after_a_reload(page, ruy):
    analyse(page, ruy)
    keys(page, "l")  # 1.e4
    click_square(page, "d7")
    click_square(page, "d5")  # a new answer: 1...d5
    page.wait_for_function("document.querySelector('#ws-analyse .mt-move.is-cursor')?.textContent.includes('d5')")
    assert ruy.nodes.filter(san="d5").exists()
    keys(page, "2")  # ?
    page.wait_for_selector("#ws-analyse .mt-move.is-cursor .mt-nag >> text=?")
    keys(page, "m", "b")
    page.wait_for_selector("#ws-analyse .mt-move.is-cursor.is-bad")
    assert ruy.nodes.get(san="d5").nags == [2]
    page.reload()
    page.wait_for_selector("#ws-analyse .mt-move.is-cursor.is-bad")  # the cursor came back
    focus(page, "moves")
    keys(page, "u")
    wait_status(page, "Undone: Mark d5")
    keys(page, "u")
    wait_status(page, "Undone: Annotation d5")
    keys(page, "u")
    wait_status(page, "Undone: Move d7d5")
    assert not ruy.nodes.filter(san="d5").exists()
    assert cursor_san(page) == "e4"  # the nearest move that is still there
    keys(page, "U")
    wait_status(page, "Redone: Move d7d5")
    assert ruy.nodes.filter(san="d5").exists()


def test_promote_delete_and_annotate_menu(page, ruy):
    analyse(page, ruy)
    keys(page, "l", "l", "j")  # 1...c5
    keys(page, "P")
    page.wait_for_function("document.querySelector('#ws-analyse .mt-variation .mt-move')?.textContent.includes('e5')")  # e5 is now the variation
    assert tree.root(ruy).kids.get().kids.order_by("order").first().san == "c5"
    keys(page, "a")
    page.wait_for_selector(".menu")
    keys(page, "j", "j", "Enter")  # the third symbol: !!
    page.wait_for_selector("#ws-analyse .mt-move.is-cursor .mt-nag >> text=!!")
    keys(page, "d")
    page.wait_for_function("!document.querySelector('#ws-analyse [data-movetree]').textContent.includes('c5')")
    assert cursor_san(page) == "e4"


def test_comment_with_figurines_saved_by_mod_enter(page, ruy):
    analyse(page, ruy)
    keys(page, "l")
    keys(page, "c")
    page.wait_for_function("document.activeElement.matches('[data-comment-form][data-node=\"%d\"] textarea')" % ruy.nodes.get(san="e4").id)
    page.keyboard.type("Main line ")
    keys(page, "Alt+KeyN", "ControlOrMeta+Enter")
    page.wait_for_selector("#ws-analyse .mt-comment >> text=Main line ♘")
    assert ruy.nodes.get(san="e4").comment == "Main line ♘"
    assert page.get_attribute("#shell", "data-layer") == "normal"


def test_engine_lines_eval_bar_and_best_move(page, ruy):
    analyse(page, ruy)
    keys(page, "G")  # after 3.Bb5, black to move
    keys(page, "e")
    page.wait_for_selector("#ws-analyse .engine__line .engine__move", timeout=20000)
    page.wait_for_selector("#ws-analyse [data-evalbar]:not([hidden])")
    assert page.evaluate("window.SPOS.engine.state().enabled")
    before = ruy.nodes.count()
    keys(page, "Enter")  # play the engine's best move
    page.wait_for_function(f"document.querySelectorAll('#ws-analyse [data-movetree] [data-node]').length === {before}", timeout=5000)
    assert ruy.nodes.count() == before + 1
    keys(page, "e")
    page.wait_for_selector("#ws-analyse [data-evalbar][hidden]", state="attached")
    assert page.inner_text("#ws-analyse [data-engine-state]") == "off"


def test_puzzle_set_up_in_the_analysis(page, ruy):
    analyse(page, ruy)
    keys(page, "p", "s")
    wait_status(page, "Puzzle set up from here")
    page.wait_for_selector("#ws-analyse .mt-puzzle.is-draft")
    keys(page, "G")
    keys(page, "h", "h")  # 2.Nf3
    keys(page, "p", "x")
    wait_status(page, "The solution ends here")
    keys(page, "p", "r")
    wait_status(page, "Ready for training")
    page.wait_for_selector("#ws-analyse .mt-move.pz-end >> text=Nf3")
    puzzle = Puzzle.objects.get(position=ruy)
    assert puzzle.active and puzzle.cards.filter(in_solution=True).count() == 1
    assert list(puzzle.cards.get(in_solution=True).line) == ["e2e4", "e7e5", "g1f3"]


def test_paste_a_game_and_analyse_it(page):
    open_mode(page, "analyse")
    paste(page, '[Event "Test"]\n[White "A"]\n[Black "B"]\n\n1. d4 d5 2. c4 *')
    page.wait_for_selector("#status-message .keyhint")
    keys(page, "a")
    page.wait_for_selector("#ws-analyse [data-movetree] >> text=c4")
    position = Position.objects.get(origin="paste")
    assert [n.san for n in Node.objects.filter(position=position).exclude(parent=None).order_by("ply")] == ["d4", "d5", "c4"]


def test_train_feedback_opens_the_puzzle_in_analyse(page, ruy):
    root = tree.root(ruy)
    analysis_puzzles.act(root, "start")
    analysis_puzzles.act(root, "ready")
    analysis_puzzles.rebuild_all(ruy)
    open_mode(page, "train")
    page.wait_for_function("window.SPOS.train && document.querySelector('[data-train-launcher]:not([hidden])')")
    keys(page, "r")
    page.wait_for_function("window.SPOS.train.state().state === 'solving'")
    keys(page, "s")  # show the solution
    page.wait_for_function("window.SPOS.train.state().state === 'feedback'")
    keys(page, "e")  # edit the puzzle in Analyse
    page.wait_for_function("window.SPOS.ctx.mode === 'analyse'")
    page.wait_for_selector("#ws-analyse .mt-puzzle")
    page.wait_for_selector("#ws-analyse [data-section-key=z]:not(.is-collapsed) >> text=in training")


def test_result_list_opens_its_puzzles_in_analyse(page, ruy):
    root = tree.root(ruy)
    analysis_puzzles.act(root, "start")
    analysis_puzzles.act(root, "ready")
    analysis_puzzles.rebuild_all(ruy)
    open_mode(page, "train")
    page.wait_for_function("window.SPOS.train && document.querySelector('[data-train-launcher]:not([hidden])')")
    keys(page, "r")
    page.wait_for_function("window.SPOS.train.state().state === 'solving'")
    keys(page, "s")
    page.wait_for_function("window.SPOS.train.state().state === 'feedback'")
    keys(page, "Escape", "q")  # end the session
    page.wait_for_function("window.SPOS.train.state().state === 'result'")
    keys(page, "a")  # the missed ones as a subject list
    page.wait_for_function("window.SPOS.ctx.mode === 'analyse'")
    page.wait_for_selector("#ws-analyse [data-movetree] .mt-puzzle")
    assert page.evaluate("window.SPOS.analysis.current().list.ids.length") == 1


def test_accessibility_with_a_position_open(page, ruy):
    analyse(page, ruy)
    keys(page, "l")
    page.wait_for_selector("#ws-analyse [data-inspector]")
    page.add_script_tag(path=str(AXE))
    result = page.evaluate(
        """async () => {
          const r = await axe.run(document, {resultTypes: ['violations'], preload: false})
          return r.violations.filter(v => ['serious', 'critical'].includes(v.impact))
            .map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.slice(0, 3).map(n => n.target.join(' '))}))
        }"""
    )
    assert result == [], result


def test_train_feedback_analyses_beside_the_board(page, ruy):
    """`a` on the feedback shows the puzzle's analysis in Train, beside the board; the next puzzle closes it."""
    root = tree.root(ruy)
    analysis_puzzles.act(root, "start")
    analysis_puzzles.act(root, "ready")
    analysis_puzzles.rebuild_all(ruy)
    open_mode(page, "train")
    page.wait_for_function("window.SPOS.train && document.querySelector('[data-train-launcher]:not([hidden])')")
    keys(page, "r")
    page.wait_for_function("window.SPOS.train.state().state === 'solving'")
    assert page.locator("#ws-train [data-island=moves]").count() == 0
    keys(page, "s")
    page.wait_for_function("window.SPOS.train.state().state === 'feedback'")
    keys(page, "a")
    page.wait_for_selector("#ws-train [data-island=moves] [data-movetree] >> text=Nf3")
    assert page.evaluate("window.SPOS.ctx.mode") == "train"
    keys(page, "Enter")  # the next puzzle (the same card again, or the result): the analysis goes
    page.wait_for_function("!document.querySelector('#ws-train [data-island=moves]')")


# ── A Library pane in Analyse: previews, opening, pasting, the tag picker ───────────────────────────────────


@pytest.fixture
def book():
    from spaced_positions.library.models import Source
    from tests.factories import back_rank

    source = Source.objects.create(title="Puzzle Book", short="Book")
    made = []
    for i in range(3):
        p = tree.create_position(back_rank(i), ["d1d8"], title=f"Diagram {i + 1}")
        p.source, p.source_ref = source, str(i + 1)
        p.save()
        made.append(p)
    return made


def library_below_the_board(page, position):
    analyse(page, position)
    focus(page, "board")
    keys(page, "Space", "w", "s")
    page.wait_for_selector(".menu")
    keys(page, "l")
    page.wait_for_selector("#ws-analyse [data-island=library] #query-info", state="attached")
    page.fill("#ws-analyse [data-querybar]", "src:book sort:source")
    page.wait_for_selector("#ws-analyse [data-library-results] [data-group-head]")  # the search's results (grouped by source)
    page.wait_for_timeout(300)
    page.click("#ws-analyse [data-view=library] .pane__title")


def current_id(page):
    return page.evaluate("window.SPOS.analysis.current()?.position.id")


def test_browsing_a_list_previews_and_never_replaces(page, book):
    library_below_the_board(page, book[0])
    keys(page, "j")  # the second diagram: a preview, the analysis stays
    page.wait_for_selector("#ws-analyse [data-island=board].is-preview")
    page.wait_for_selector("#ws-analyse .moves__preview >> text=Diagram 2")
    assert page.evaluate("window.SPOS.ctx.overlay") is None  # no question
    assert current_id(page) == str(book[0].uuid)
    # leaving the list: the board and the moves are the open analysis again
    focus(page, "moves")
    page.wait_for_selector("#ws-analyse [data-island=board]:not(.is-preview)")
    page.wait_for_selector("#ws-analyse .moves__preview", state="detached")
    assert page.evaluate("document.querySelector('#ws-analyse [data-island=board]').board.line.title") == "Diagram 1"
    # ↵ opens the row under the cursor here, in Analyse
    page.click("#ws-analyse [data-view=library] .pane__title")
    keys(page, "Enter")
    page.wait_for_function(f"window.SPOS.analysis.current()?.position.id === {str(book[1].uuid)!r}")
    assert page.evaluate("window.SPOS.ctx.mode") == "analyse"
    keys(page, "j", "a")  # a: the same for the next one
    page.wait_for_function(f"window.SPOS.analysis.current()?.position.id === {str(book[2].uuid)!r}")


def test_a_pasted_game_adds_its_moves(page, book):
    from tests.factories import back_rank

    analyse(page, book[0])
    focus(page, "board")
    fen = back_rank(0)
    page.evaluate("""(text) => { const dt = new DataTransfer(); dt.setData('text/plain', text)
      document.body.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true})) }""",
                  f'[FEN "{fen}"]\n[SetUp "1"]\n\n1. Rd7 *')
    page.wait_for_selector("#status-message .keyhint")
    keys(page, "b")  # onto the board: into this analysis, as a variation
    page.wait_for_function("document.getElementById('status-message').textContent.includes('Added 1 pasted move')")
    sans = page.eval_on_selector_all("#ws-analyse .mt-move .mt-san", "els => els.map(e => e.textContent)")
    assert "Rd8#" in "".join(sans) and "Rd7" in "".join(sans)


def test_the_tag_picker_adds_and_removes(page, book):
    analyse(page, book[0])
    keys(page, "l")  # 1.Rd8#
    keys(page, "t")
    page.wait_for_selector(".tagpicker:not([hidden])")
    page.keyboard.type("pin")
    page.wait_for_selector(".tagpicker .cmdline__row.is-cursor >> text=Pin")
    keys(page, "Enter")
    page.wait_for_selector(".tagpicker", state="hidden")
    page.wait_for_selector("#ws-analyse .mt-tag >> text=Pin")
    keys(page, "t")  # nothing typed: what the move has, ↵ takes it off
    page.wait_for_selector(".tagpicker .cmdline__row.is-cursor >> text=●")
    keys(page, "Enter")
    page.wait_for_selector("#ws-analyse .mt-tag >> text=Pin", state="detached")
    keys(page, "u")  # and back
    page.wait_for_selector("#ws-analyse .mt-tag >> text=Pin")


def test_enter_right_after_typing_takes_what_was_typed(page, book):
    """A slow search (here: delayed on purpose) doesn't swallow ↵: the picker waits for the rows of what was typed."""
    analyse(page, book[0])
    keys(page, "l")
    page.evaluate("""() => { const fetch = window.fetch
      window.fetch = (url, options) => String(url).includes('/lib/complete/')
        ? new Promise((r) => setTimeout(r, 800)).then(() => fetch(url, options)) : fetch(url, options) }""")
    keys(page, "t")
    page.wait_for_selector(".tagpicker:not([hidden])")
    page.keyboard.type("pin")
    keys(page, "Enter")  # at once: the search is still on its way
    page.wait_for_selector("#ws-analyse .mt-tag >> text=Pin")
