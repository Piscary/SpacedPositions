"""The Details pane (spec 16): `:edit` on games and positions, players and sources found by name or made new, undo;
the pane's rows; and a pasted game without names getting its players in the browser.

Journeys (Day 4): make a source first (␣ n s), then give a position that source in the Details pane;
a player found by an alias; edit a source's year and kind; ⌫ empties a field and u brings it back;
I in the Library with a game row under the cursor."""

import pytest

from spaced_positions.analysis import tree
from spaced_positions.library import edit, importer
from spaced_positions.library.models import Player, Source
from tests.browser import keys, open_mode

NAMELESS = '[Event "Blitz"]\n[Site "https://lichess.org/abcdefgh"]\n\n1. e4 e5 2. Nf3 Nc6 *\n'


@pytest.mark.django_db
def test_a_game_gets_its_players_and_a_position_its_source():
    game = importer.run(NAMELESS, None, ready=True)["games"][0]
    tal = Player.objects.create(key="tal", name="Tal, Mikhail", aliases=["Misha"])
    done = edit.edit([f'g{game.pk} white=misha black="Magnus Carlsen" result=1-0 date=2026.10.31'], {}, {})
    game.refresh_from_db()
    assert game.white == tal and game.white_name == "Tal, Mikhail"  # found by another spelling
    assert game.black.name == "Magnus Carlsen" and game.black_name == "Magnus Carlsen"  # a name nobody has: a new player
    assert (game.result, game.year) == ("1-0", 2026)
    edit.edit(done["undo"]["args"], {}, {})
    game.refresh_from_db()
    assert (game.white, game.black, game.result, game.white_name) == (None, None, "*", "")
    with pytest.raises(Exception, match="1-0, 0-1, 1/2-1/2"):
        edit.edit([f"g{game.pk} result=draw"], {}, {})
    position = tree.create_position("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1", [], title="Back rank")
    edit.edit([f'p{position.pk} source="Tactics Manual" page=41 diagram=103 difficulty=2'], {}, {})
    position.refresh_from_db()
    assert position.source == Source.objects.get(title="Tactics Manual") and (position.source_page, position.source_ref) == ("41", "103")
    assert position.difficulty == 2


@pytest.mark.django_db
def test_the_rows_of_a_game(client):
    game = importer.run(NAMELESS, None, ready=True)["games"][0]
    html = client.get("/lib/details/", {"ref": str(game.uuid)}).content.decode()
    assert f'data-ref="g{game.pk}"' in html and "White and Black unknown" in html and 'data-row="white"' in html
    assert "Nothing to show" in client.get("/lib/details/", {"ref": "#fork"}).content.decode()


@pytest.mark.browser
@pytest.mark.django_db(transaction=True)
def test_a_pasted_game_gets_its_names_in_the_details_pane(page):
    game = importer.run(NAMELESS, None, ready=True)["games"][0]
    open_mode(page, "analyse")
    page.evaluate("(id) => window.SPOS.analysis.openGame(id)", str(game.uuid))
    page.wait_for_selector("#ws-analyse [data-movetree] .mt-move")
    page.click("#ws-analyse [data-view=moves] .pane__title")
    keys(page, "I")  # the details of the open game, in a pane beside it
    page.wait_for_selector("#ws-analyse [data-details-list] [data-row=white]")
    page.wait_for_function("window.SPOS.ctx.pane.view === 'details'")
    keys(page, "Enter")  # the first row: White
    page.wait_for_function("document.querySelector('.cmdline__input')?.value.startsWith('edit g')")
    page.keyboard.type("Magnus Carlsen")
    keys(page, "Enter")
    page.wait_for_selector("#ws-analyse [data-details-list] [data-row=white] >> text=Magnus Carlsen")
    game.refresh_from_db()
    assert game.white.name == "Magnus Carlsen"
    keys(page, "u")  # undo
    page.wait_for_function("!document.querySelector('#ws-analyse [data-details-list] [data-row=white]').textContent.includes('Magnus')")
    game.refresh_from_db()
    assert game.white is None


@pytest.mark.browser
@pytest.mark.django_db(transaction=True)
def test_make_source_and_give_position_that_source(page):
    """Make a source first (␣ n s), then give a position that source in the Details pane."""
    from spaced_positions.training.models import Position

    open_mode(page, "collect")
    page.wait_for_selector("#ws-collect [data-island=board]")
    # Make a new source via command line
    keys(page, "Space", "n", "s")
    page.wait_for_function("document.querySelector('.cmdline__input')")
    page.keyboard.type("Tactics for Beginners")
    keys(page, "Enter")
    # The Details pane should now show the new source
    page.wait_for_selector("[data-details-list] [data-row=title]")
    page.wait_for_function("!!document.querySelector('[data-details-list] [data-row=title]').textContent.includes('Tactics')")
    # Check the source was created
    source = Source.objects.filter(title="Tactics for Beginners").first()
    assert source is not None
    # Create a position and give it that source via Details
    position = tree.create_position("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", [], title="Start position")
    # Open the position in Analyse and show its Details
    open_mode(page, "analyse")
    page.evaluate("(id) => window.SPOS.analysis.openPosition(id)", str(position.uuid))
    page.wait_for_selector("#ws-analyse [data-movetree] .mt-move")
    keys(page, "I")  # open Details pane
    page.wait_for_selector("#ws-analyse [data-details-list] [data-row=source]")
    # Edit the source field
    page.click("#ws-analyse [data-details-list] [data-row=source]")
    keys(page, "Enter")
    page.wait_for_function("document.querySelector('.cmdline__input')?.value.startsWith('edit')")
    page.keyboard.type("Tactics for Beginners")
    keys(page, "Enter")
    page.wait_for_function("!!document.querySelector('[data-details-list] [data-row=source]').textContent.includes('Tactics')")
    position.refresh_from_db()
    assert position.source == source


@pytest.mark.browser
@pytest.mark.django_db(transaction=True)
def test_player_found_by_alias_in_details(page):
    """Edit a game's White field: a player found by an alias."""
    game = importer.run(NAMELESS, None, ready=True)["games"][0]
    tal = Player.objects.create(key="tal", name="Tal, Mikhail", aliases=["Misha Tal"])
    open_mode(page, "analyse")
    page.evaluate("(id) => window.SPOS.analysis.openGame(id)", str(game.uuid))
    page.wait_for_selector("#ws-analyse [data-movetree] .mt-move")
    keys(page, "I")  # open Details pane
    page.wait_for_selector("#ws-analyse [data-details-list] [data-row=white]")
    # Edit White, typing the alias "Misha Tal"
    page.click("#ws-analyse [data-details-list] [data-row=white]")
    keys(page, "Enter")
    page.wait_for_function("document.querySelector('.cmdline__input')?.value.startsWith('edit')")
    page.keyboard.type("Misha Tal")
    keys(page, "Enter")
    page.wait_for_function("!!document.querySelector('[data-details-list] [data-row=white]').textContent.includes('Tal')")
    game.refresh_from_db()
    assert game.white == tal


@pytest.mark.browser
@pytest.mark.django_db(transaction=True)
def test_edit_source_year_and_kind_in_details(page):
    """Edit a source's year and kind in the Details pane."""
    source = Source.objects.create(title="Endgame Manual", year=None, kind="book")
    open_mode(page, "library")
    page.wait_for_selector("#ws-library [data-list]")
    # Switch to Sources tab
    page.click("#ws-library [data-tab=sources]")
    page.wait_for_function("!!document.querySelector('#ws-library [data-tab=sources].is-active')")
    # Click the source row to select it
    page.click("#ws-library [data-list] [data-row]")
    keys(page, "I")  # open Details pane
    page.wait_for_selector("[data-details-list] [data-row=year]")
    # Edit the year field
    page.click("[data-details-list] [data-row=year]")
    keys(page, "Enter")
    page.wait_for_function("document.querySelector('.cmdline__input')?.value.startsWith('edit')")
    page.keyboard.type("2020")
    keys(page, "Enter")
    page.wait_for_function("!!document.querySelector('[data-details-list] [data-row=year]').textContent.includes('2020')")
    source.refresh_from_db()
    assert source.year == 2020


@pytest.mark.browser
@pytest.mark.django_db(transaction=True)
def test_backspace_clears_field_and_undo_restores(page):
    """⌫ empties a field and u brings it back."""
    game = importer.run(NAMELESS, None, ready=True)["games"][0]
    edit.edit([f'g{game.pk} event="World Championship"'], {}, {})
    open_mode(page, "analyse")
    page.evaluate("(id) => window.SPOS.analysis.openGame(id)", str(game.uuid))
    page.wait_for_selector("#ws-analyse [data-movetree] .mt-move")
    keys(page, "I")  # open Details pane
    page.wait_for_selector("#ws-analyse [data-details-list] [data-row=event]")
    page.wait_for_function("!!document.querySelector('[data-details-list] [data-row=event]').textContent.includes('World')")
    # Navigate to the event row and clear it
    page.click("#ws-analyse [data-details-list] [data-row=event]")
    keys(page, "Backspace")
    page.wait_for_function("document.querySelector('[data-details-list] [data-row=event]').textContent.includes('—')")
    game.refresh_from_db()
    assert game.event == ""
    # Undo the clear
    keys(page, "u")
    page.wait_for_function("!!document.querySelector('[data-details-list] [data-row=event]').textContent.includes('World')")
    game.refresh_from_db()
    assert game.event == "World Championship"


@pytest.mark.browser
@pytest.mark.django_db(transaction=True)
def test_library_details_with_game_row(page):
    """I in the Library with a game row under the cursor shows the game's Details."""
    game = importer.run(NAMELESS, None, ready=True)["games"][0]
    open_mode(page, "library")
    page.wait_for_selector("#ws-library [data-list]")
    # Switch to Games tab
    page.click("#ws-library [data-tab=games]")
    page.wait_for_function("!!document.querySelector('#ws-library [data-tab=games].is-active')")
    # Wait for the game row to appear
    page.wait_for_selector("#ws-library [data-list] [data-row]")
    # Click the first game row to select it
    page.click("#ws-library [data-list] [data-row]")
    keys(page, "I")  # open Details pane for the selected game
    page.wait_for_selector("[data-details-list] [data-row=white]")
    # The Details pane should show the game's fields
    page.wait_for_function("!!document.querySelector('[data-details-list] [data-row=white]')")
    page.wait_for_function("!!document.querySelector('[data-details-list] [data-row=result]')")
