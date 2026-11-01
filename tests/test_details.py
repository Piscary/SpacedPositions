"""The Details pane (spec 16): `:edit` on games and positions, players and sources found by name or made new, undo;
the pane's rows; and a pasted game without names getting its players in the browser."""

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
