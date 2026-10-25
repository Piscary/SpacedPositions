"""Library, Collect and import journeys in a real browser (spec 04 · Library, Collect; 11): the query bar with
completion, selection and bulk commands with undo, the collections, the filter pane, training from results, saved
queries in the launcher, entering positions in Collect, PGN import, games in Analyse and tags in Analyse."""

from pathlib import Path

import pytest

from spaced_positions.analysis import puzzles as analysis_puzzles
from spaced_positions.analysis import tree
from spaced_positions.library.models import Game, PositionTag, SavedQuery, Source, Tag
from spaced_positions.training.models import Position, Puzzle
from tests.browser import keys, open_mode, paste
from tests.factories import back_rank

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AXE = Path(__file__).parent / "vendor" / "axe.min.js"


@pytest.fixture
def positions():
    reti = Source.objects.create(title="Endgame Studies", short="Réti 1922")
    made = []
    for i, (title, tag, diff) in enumerate([("Fork one", "knight-fork", 3), ("Fork two", "family-fork", 4), ("Pin one", "pin", 2)]):
        p = tree.create_position(back_rank(i), ["d1d8"], title=title)
        p.source, p.source_ref, p.difficulty_override = reti, f"Nr. {i + 1}", diff
        p.save()
        PositionTag.objects.create(position=p, tag=Tag.objects.get(key=tag))
        root = tree.root(p)
        analysis_puzzles.act(root, "start")
        analysis_puzzles.act(root, "ready")
        analysis_puzzles.rebuild_all(p)
        made.append(p)
    return made


def library(page):
    open_mode(page, "library")
    page.wait_for_selector("#ws-library [data-library-results] #query-info", state="attached")
    page.click("#ws-library [data-view=library] .pane__title")
    return page


def query(page, text):
    page.click("#ws-library [data-querybar]")
    page.fill("#ws-library [data-querybar]", text)
    page.wait_for_function(
        f"document.querySelector('#ws-library [data-query-count]').textContent && window.SPOS.library.state().q === {text!r}"
    )
    page.wait_for_timeout(300)  # the results arrive after the debounce
    keys(page, "Enter")
    page.wait_for_function("window.SPOS.ctx.layer === 'normal'")


def count(page):
    return page.inner_text("#ws-library [data-query-count]")


def rows(page):
    return page.eval_on_selector_all("#ws-library [data-library-results] [data-row]", "els => els.map(e => e.dataset.row)")


def wait_status(page, text):
    try:
        page.wait_for_function(f"document.getElementById('status-message').textContent.includes({text!r})", timeout=5000)
    except Exception:  # noqa: BLE001
        raise AssertionError(f"status line: {page.inner_text('#status-message')!r}, wanted {text!r}") from None


def test_query_with_completion_cursor_and_preview(page, positions):
    library(page)
    keys(page, "/")
    page.wait_for_function("document.activeElement.matches('[data-querybar]')")
    page.keyboard.type("motif:gab")
    page.wait_for_selector("#ws-library .querybar__option >> text=motif:fork")
    keys(page, "Tab")
    assert page.input_value("#ws-library [data-querybar]") == "motif:fork "
    page.wait_for_function("document.querySelector('#ws-library [data-query-count]').textContent.startsWith('2 ')")
    keys(page, "Enter")
    page.wait_for_function("window.SPOS.ctx.layer === 'normal'")
    assert sorted(rows(page)) == sorted([f"p{positions[0].pk}", f"p{positions[1].pk}"])
    keys(page, "j")
    page.wait_for_function(
        "document.querySelector('.workspace:not([hidden]) [data-island=board]').board.line.start === "
        "document.querySelector('#ws-library [data-library-results] .is-cursor').dataset.fen"
    )
    query(page, "diff:>=3 sort:-difficulty")
    assert rows(page) == [f"p{positions[1].pk}", f"p{positions[0].pk}"]
    query(page, "motif:nonsense")
    page.wait_for_selector("#ws-library .querybar__problem >> text=no tag 'nonsense' in motif")


def test_select_tag_and_undo(page, positions):
    library(page)
    query(page, "src:reti sort:title")
    keys(page, "x", "j", "x")
    page.wait_for_selector("#ws-library [data-bulk]:not([hidden]) >> text=2 selected")
    keys(page, "t")  # opens the command line with "tag "
    page.keyboard.type("zwischenzug")
    page.wait_for_timeout(300)
    keys(page, "Enter")
    wait_status(page, "Tagged 2 items Zwischenzug")
    assert PositionTag.objects.filter(tag__key="zwischenzug").count() == 2
    keys(page, "u")
    wait_status(page, "Undone")
    assert PositionTag.objects.filter(tag__key="zwischenzug").count() == 0
    assert PositionTag.objects.count() == 3  # nothing else was touched


def test_collections_tags_players_and_opening_in_analyse(page, positions):
    library(page)
    keys(page, "6")
    page.wait_for_function("window.SPOS.library.state().c === 'tags'")
    query(page, "springergabel")
    keys(page, "Enter")  # a tag opens its positions
    page.wait_for_function("window.SPOS.library.state().c === 'positions' && window.SPOS.library.state().q === '#knight-fork'")
    page.wait_for_function("document.querySelector('#ws-library [data-query-count]').textContent === '2 positions'")
    assert sorted(rows(page)) == sorted([f"p{positions[0].pk}", f"p{positions[1].pk}"])  # Familiengabel is a Springergabel
    keys(page, "Enter")  # a position opens in Analyse
    page.wait_for_function("window.SPOS.ctx.mode === 'analyse'")
    page.wait_for_selector("#ws-analyse [data-movetree] >> text=Rd8#")


def test_trash_restore_and_empty(page, positions):
    library(page)
    query(page, "pin")
    keys(page, "d")
    wait_status(page, "Moved 1 to the trash")
    assert Position.objects.get(pk=positions[2].pk).deleted_at is not None
    query(page, "is:trash")
    assert rows(page) == [f"p{positions[2].pk}"]
    keys(page, "r")
    wait_status(page, "Restored 1")
    assert Position.objects.get(pk=positions[2].pk).deleted_at is None
    keys(page, "u")  # the restore undone: in the trash again
    page.wait_for_function("document.getElementById('status-message').textContent.startsWith('Undone')")
    keys(page, ":")
    page.keyboard.type("trash-empty")
    keys(page, "Enter")
    wait_status(page, "y / n")
    keys(page, "y")
    wait_status(page, "Trash emptied: 1 positions")
    assert not Position.objects.filter(pk=positions[2].pk).exists()


def test_filter_pane_and_training_from_results(page, positions):
    library(page)
    page.click("#ws-library [data-view=filters] .pane__title")
    page.wait_for_selector("#ws-library [data-filters] [data-term='motif:knight-fork']")
    term = page.eval_on_selector_all("#ws-library [data-filters] [data-term]", "els => els.map(e => e.dataset.term)").index("motif:knight-fork")
    keys(page, *(["j"] * term), "Enter")  # the cursor starts on the first facet
    page.wait_for_function("window.SPOS.library.state().q === 'motif:knight-fork'")
    page.click("#ws-library [data-view=library] .pane__title")
    page.wait_for_function("document.querySelector('#ws-library [data-query-count]').textContent.startsWith('2 ')")
    keys(page, "T")  # nothing selected: everything the query found
    page.wait_for_function("window.SPOS.ctx.mode === 'train' && window.SPOS.train.state().state === 'solving'")
    assert page.evaluate("window.SPOS.train.puzzle().title") in ("Fork one", "Fork two")


def test_saved_query_filters_a_custom_session(page, positions):
    library(page)
    query(page, "diff:2")
    keys(page, ":")
    page.keyboard.type("save-query easy ones")
    keys(page, "Enter")
    wait_status(page, "Saved as q:easy-ones")
    assert SavedQuery.objects.get().query == "diff:2"
    open_mode(page, "train")
    page.wait_for_selector("[data-train-query='in:q:easy-ones']")
    page.click("[data-train-query='in:q:easy-ones']")
    assert page.input_value("[data-train-filter]") == "in:q:easy-ones"
    page.click("[data-cmd='train.custom']")
    page.wait_for_function("window.SPOS.train.state().state === 'solving'")
    assert page.evaluate("window.SPOS.train.puzzle().title") == "Pin one"
    assert page.evaluate("window.SPOS.train.state().results") == 0


# ── Collect ───────────────────────────────────────────────────────────────────────────────────────────────────


def test_collect_save_next_duplicate_and_solution(page):
    open_mode(page, "collect")
    page.wait_for_selector("#ws-collect [data-island=entry]")
    page.click("#ws-collect [data-view=entry] .pane__title")
    keys(page, "s")
    page.keyboard.type("Reti Studien")
    keys(page, "Enter")
    wait_status(page, "New source: Reti Studien")
    page.wait_for_selector("#ws-collect [data-entry-source] >> text=Reti Studien")
    paste(page, back_rank(0))
    page.wait_for_selector("#status-message .keyhint")
    keys(page, "c")  # onto the Collect board, in the editor
    page.wait_for_function("document.querySelector('#ws-collect [data-island=board]').board.layer === 'setup'")
    keys(page, "ControlOrMeta+Enter")
    wait_status(page, "Saved p")
    first = Position.objects.get()
    assert (first.title, first.source.title, first.source_ref) == ("Reti Studien Nr. 1", "Reti Studien", "1")
    assert page.input_value("#ws-collect [data-entry=ref]") == "2"  # diagram + 1
    assert page.evaluate("document.querySelector('#ws-collect [data-island=board]').board.layer") == "setup"
    # the same position again: a duplicate, merged with its solution
    paste(page, back_rank(0))
    page.wait_for_selector("#status-message .keyhint")
    keys(page, "c")
    page.wait_for_selector("#ws-collect [data-entry-state].is-duplicate")
    keys(page, "S")  # to the solution layer
    page.wait_for_function("document.querySelector('#ws-collect [data-island=board]').board.layer === 'play'")
    page.evaluate("""(() => { const b = document.querySelector('#ws-collect [data-island=board]').board
      b.submit(b.chess.move('Rd8#')) })()""")
    keys(page, "ControlOrMeta+Enter")
    wait_status(page, "m merge")
    keys(page, "m")
    wait_status(page, f"Merged into p{first.pk}")
    assert Position.objects.count() == 1
    assert Puzzle.objects.get(position=first).active  # ready for training by default


# ── Import, games ─────────────────────────────────────────────────────────────────────────────────────────────

PGN = """[Event "Club"]
[White "Tal, Mikhail"]
[Black "Smith, J."]
[Result "1-0"]
[Date "1960.05.01"]

1. e4 {Best} e5 (1... c5 2. Nf3) 2. Nf3 Nc6 3. Bb5 1-0

[Event "Back rank"]
[FEN "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1"]
[SetUp "1"]

1. Rd8# *
"""


def test_import_pgn_games_and_puzzles_then_undo(page):
    open_mode(page, "library")
    paste(page, PGN)
    page.wait_for_selector("#status-message .keyhint")
    keys(page, "i")
    page.wait_for_selector(".importer >> text=1 game, 1 puzzle")
    keys(page, "r", "Enter")  # puzzles into training, import
    wait_status(page, "Imported 1 game · 1 puzzle in training")
    game = Game.objects.get()
    assert (game.white_name, game.result, game.year) == ("Tal, Mikhail", "1-0", 1960)
    assert [n.san for n in game.nodes.exclude(parent=None).order_by("ply", "order")] == ["e4", "e5", "c5", "Nf3", "Nf3", "Nc6", "Bb5"]
    assert game.nodes.get(san="e4").comment == "Best"
    assert Puzzle.objects.get().active
    keys(page, "Escape", "u")
    wait_status(page, "Undone: Imported 1 game")
    assert Game.objects.get().deleted_at and Position.objects.get().deleted_at


def test_game_in_analyse_and_new_position(page):
    from spaced_positions.library import importer

    importer.run(PGN.split("\n\n[Event \"Back rank\"]")[0], None, False)
    library(page)
    keys(page, "2")
    page.wait_for_function("window.SPOS.library.state().c === 'games'")
    page.wait_for_selector("#ws-library [data-library-results] [data-game]")
    keys(page, "Enter")
    page.wait_for_function("window.SPOS.ctx.mode === 'analyse'")
    page.wait_for_selector("#ws-analyse [data-inspector] >> text=Tal, Mikhail")
    page.click("#ws-analyse [data-view=moves] .pane__title")
    keys(page, "l", "l", "l")  # after 2.Nf3
    keys(page, ":")
    page.keyboard.type("new-position moves")
    keys(page, "Enter")
    wait_status(page, "New position")
    position = Position.objects.get()
    assert position.game == Game.objects.get() and position.game_node.san == "Nf3"
    assert [n.san for n in position.nodes.exclude(parent=None).order_by("ply")] == ["Nc6", "Bb5"]


def test_tags_in_analyse(page, positions):
    p = positions[0]
    open_mode(page, "analyse")
    page.evaluate("(pid) => window.SPOS.analysis.open(pid)", str(p.uuid))
    page.wait_for_selector("#ws-analyse [data-movetree]")
    page.click("#ws-analyse [data-view=moves] .pane__title")
    keys(page, "T")
    page.keyboard.type("opfer")
    page.wait_for_timeout(300)
    keys(page, "Enter")
    wait_status(page, "Tagged 1 item Sacrifice")
    page.wait_for_selector("#ws-analyse [data-inspector] .inspector__tags >> text=Sacrifice")
    keys(page, "l", "t")
    page.keyboard.type("zwischenzug")
    page.wait_for_timeout(300)
    keys(page, "Enter")
    page.wait_for_selector("#ws-analyse .mt-tag >> text=Zwischenzug")
    assert p.nodes.get(san="Rd8#").tags.get().key == "zwischenzug"


def test_library_accessibility(page, positions):
    library(page)
    page.add_script_tag(path=str(AXE))
    result = page.evaluate(
        """async () => {
          const r = await axe.run(document, {resultTypes: ['violations'], preload: false})
          return r.violations.filter(v => ['serious', 'critical'].includes(v.impact))
            .map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.slice(0, 3).map(n => n.target.join(' '))}))
        }"""
    )
    assert result == [], result


def test_edit_players_and_link_a_name(page):
    """A player made and edited from the Library, a name on a game linked to it, `d` refused while used."""
    from spaced_positions.library.models import Player

    Game.objects.create(white_name="Tal, M.", black_name="Larsen", start_fen=START)
    library(page)
    keys(page, ":")
    page.keyboard.type('new-player "Tal, Mikhail" role=model')
    keys(page, "Enter")
    page.wait_for_function("document.getElementById('status-message').textContent.startsWith('New player: Tal, Mikhail')")
    keys(page, "4")
    page.wait_for_selector("#ws-library [data-row='@tal']")
    page.click("#ws-library [data-row='@tal'] .list__title")
    keys(page, "c")
    page.keyboard.type("title=GM")
    keys(page, "Enter")
    page.wait_for_selector("#ws-library [data-row='@tal'] .chip >> text=GM")
    keys(page, ":")
    page.keyboard.type('player-link "Tal, M." @tal')
    keys(page, "Enter")
    page.wait_for_selector("#ws-library [data-row='@tal'] >> text=1 game")
    keys(page, "d")
    page.wait_for_function("document.getElementById('status-message').textContent.includes('is used by 1 game')")
    keys(page, "u")  # the link is undone
    page.wait_for_selector("#ws-library [data-row='@tal'] >> text=0 games")
    assert Player.objects.get(key="tal").aliases == []


def test_open_beside_the_list(page, positions):
    """`o` shows the cursor row's position beside the list (a board and its moves, linked to each other)."""
    library(page)
    keys(page, "j")
    keys(page, "o")
    page.wait_for_selector("#ws-library [data-island=moves] [data-movetree]")
    groups = page.eval_on_selector_all("#ws-library [data-pane]", "els => els.map(e => [e.dataset.view, e.querySelector('[data-group]')?.dataset.group || null])")
    assert ["board", "B"] in groups and ["moves", "B"] in groups
    title = page.get_attribute("#ws-library [data-library-results] .list__row.is-cursor", "data-title")
    page.wait_for_function("(t) => document.getElementById('status-message').textContent.startsWith(t)", arg=title)
    assert "Rd8#" in page.inner_text("#ws-library [data-island=moves]")
    # Analyse's keys work on it here: the cursor moves through the analysis, the linked board follows
    page.click("#ws-library [data-view=moves] .pane__title")
    keys(page, "l")
    page.wait_for_function("document.querySelector('#ws-library .mt-move.is-cursor')?.textContent.includes('Rd8')")
    keys(page, "h")
    page.wait_for_function("!document.querySelector('#ws-library .mt-move.is-cursor')")
    # another row: the same split
    page.click("#ws-library [data-view=library] .pane__title")
    keys(page, "j", "o")
    page.wait_for_timeout(500)
    assert page.locator("#ws-library [data-island=moves]").count() == 1


def test_sort_by_a_column_and_fold_groups(page, positions):
    """`s` sorts by a column (into the query), groups by difficulty fold with z / Z, the cursor skips them."""
    library(page)
    keys(page, "s", "d")  # difficulty: the easiest first
    page.wait_for_function("window.SPOS.library.state().q === 'sort:difficulty'")
    page.wait_for_selector("#ws-library [data-group-head='★★☆☆☆']")
    heads = page.eval_on_selector_all("#ws-library [data-group-head]", "els => els.map(e => e.dataset.groupHead)")
    assert heads == ["★★☆☆☆", "★★★☆☆", "★★★★☆"]
    keys(page, "s", "d")  # again: reversed
    page.wait_for_function("window.SPOS.library.state().q === 'sort:-difficulty'")
    page.wait_for_function("document.querySelector('#ws-library [data-group-head]').dataset.groupHead === '★★★★☆'")
    keys(page, "z")  # the cursor's group (★★★★☆) folds; the cursor moves on to the next row that can be seen
    page.wait_for_selector("#ws-library [data-group-head='★★★★☆'].is-folded")
    assert page.get_attribute("#ws-library [data-library-results] .list__row.is-cursor", "data-group") == "★★★☆☆"
    keys(page, "j")
    assert page.get_attribute("#ws-library [data-library-results] .list__row.is-cursor", "data-group") == "★★☆☆☆"
    keys(page, "Z")
    page.wait_for_function("document.getElementById('status-message').textContent.startsWith('All groups open')")
    assert page.locator("#ws-library [data-library-results] .list__row[hidden]").count() == 0



def test_a_pane_of_another_mode_says_where_it_works(page):
    library(page)
    keys(page, ":")
    page.keyboard.type("vsplit queue")
    keys(page, "Enter")
    page.wait_for_selector("#ws-library [data-view=queue] >> text=It works in Train")
    page.click("#ws-library [data-view=queue] [data-cmd='mode.train']")
    page.wait_for_function("window.SPOS.ctx.mode === 'train'")
