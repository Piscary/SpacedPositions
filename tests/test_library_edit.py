"""Phase 6: editing the vocabulary, sources and players (`:edit`, `:new-tag`, `:new-player`, `:new-source`,
`:delete`, `:player-link`), each with its undo."""

import json

import pytest

from spaced_positions.analysis import tree
from spaced_positions.library import query
from spaced_positions.library.models import Game, Player, PositionTag, Source, Tag
from tests.factories import back_rank

pytestmark = pytest.mark.django_db

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def run(client, cid, *args, c=None, ids=None):
    body = {"args": list(args), "context": {}}
    if c:
        body |= {"c": c, "ids": ids or []}
    return client.post(f"/cmd/{cid}/", json.dumps(body), content_type="application/json").json()


def undo(client, result):
    return run(client, result["undo"]["command"], *result["undo"]["args"])


def redo(client, result):
    return run(client, result["redo"]["command"], *result["redo"]["args"])


def test_new_tag_under_a_parent_takes_its_field(client):
    result = run(client, "tag.new", 'Kreuzfesselung parent=fesselung en="Cross pin" aliases="crosspin,x-pin"')  # parent by name
    assert result["ok"], result
    tag = Tag.objects.get(key="cross-pin")
    assert tag.parent.key == "pin" and tag.field == tag.parent.field and tag.name_en == "Cross pin"
    assert tag.aliases == ["crosspin", "x-pin"]
    undo(client, result)
    assert not Tag.objects.filter(key="cross-pin").exists()
    redo(client, result)
    assert Tag.objects.get(key="cross-pin").pk == tag.pk
    assert not run(client, "tag.new", 'Kreuzbindung en="Cross pin"')["ok"]  # the key is taken


def test_edit_tags_by_selection_and_by_name_with_undo(client):
    fork = Tag.objects.get(key="fork")
    old = (fork.name_en, fork.base_difficulty)
    result = run(client, "library.edit", "en=Fork! difficulty=3", c="tags", ids=["#fork"])
    assert result["ok"], result
    fork.refresh_from_db()
    assert (fork.name_en, fork.base_difficulty) == ("Fork!", 3)
    undo(client, result)
    fork.refresh_from_db()
    assert (fork.name_en, fork.base_difficulty) == old
    assert not run(client, "library.edit", "#fork difficulty=9")["ok"]
    assert not run(client, "library.edit", "#fork colour=red")["ok"]
    # the hierarchy can't loop
    child = fork.children.first()
    assert not run(client, "library.edit", f"#fork parent={child.key}")["ok"]
    assert run(client, "library.edit", f"#{child.key} parent=none")["ok"]
    assert Tag.objects.get(pk=child.pk).parent is None


def test_weights_move_the_automatic_difficulty(client):
    p = tree.create_position(back_rank(0), ["d1d8"])
    PositionTag.objects.create(position=p, tag=Tag.objects.get(key="mate-in-1"))
    run(client, "library.edit", "#mate-in-1 difficulty=1")
    p.refresh_from_db()
    assert p.difficulty_auto == 1
    run(client, "library.edit", "#mate-in-1 difficulty=4")
    p.refresh_from_db()
    assert p.difficulty_auto == 4


def test_players_new_edit_link_and_delete(client):
    made = run(client, "player.new", '"Tal, Mikhail" role=model title=GM')
    assert made["ok"] and made["message"] == "New player: Tal, Mikhail"
    tal = Player.objects.get(key="tal")
    assert (tal.role, tal.title) == ("model", "GM")
    g1 = Game.objects.create(white_name="Tal, M.", black_name="Larsen, Bent", start_fen=START)
    g2 = Game.objects.create(white_name="Smyslov", black_name="TAL, M.", start_fen=START)
    assert set(query.run("is:unlinked", "games").queryset) == {g1, g2}
    link = run(client, "player.link", '"Tal, M." @tal')
    assert link["ok"] and link["message"] == "Tal, M. → Tal, Mikhail: 2 games"
    g1.refresh_from_db(), g2.refresh_from_db(), tal.refresh_from_db()
    assert g1.white == tal and g2.black == tal and tal.aliases == ["Tal, M."]
    assert set(query.run("is:unlinked", "games").queryset) == {g1, g2}  # Larsen and Smyslov match nobody yet
    # a player with games stays
    refused = run(client, "library.delete", c="players", ids=["@tal"])
    assert not refused["ok"] and "2 games" in refused["message"]
    undo(client, link)
    g1.refresh_from_db(), tal.refresh_from_db()
    assert g1.white is None and tal.aliases == []
    # without a player, the name becomes one
    larsen = run(client, "player.link", '"Larsen, Bent"')
    assert larsen["ok"] and "(new player)" in larsen["message"]
    g1.refresh_from_db()
    assert g1.black.name == "Larsen, Bent"
    undo(client, larsen)
    assert not Player.objects.filter(name="Larsen, Bent").exists()
    # an unused player is deleted, and undo brings it back with its id
    gone = run(client, "library.delete", c="players", ids=["@tal"])
    assert gone["ok"] and not Player.objects.filter(key="tal").exists()
    undo(client, gone)
    assert Player.objects.get(key="tal").pk == tal.pk


def test_sources_new_edit_and_delete_in_use(client):
    made = run(client, "source.new", '"Chess: 5334 Problems" short="Polgár" year=1994 kind=book')
    assert made["ok"], made
    source = Source.objects.get(short="Polgár")
    assert source.year == 1994
    assert run(client, "library.edit", f"s{source.pk} authors=\"Polgár, László\"")["ok"]
    source.refresh_from_db()
    assert source.authors == "Polgár, László"
    assert not run(client, "library.edit", f"s{source.pk} kind=magazine")["ok"]
    p = tree.create_position(back_rank(0), ["d1d8"])
    p.source = source
    p.save()
    assert not run(client, "library.delete", c="sources", ids=[f"s{source.pk}"])["ok"]  # used by a position


def test_delete_keeps_tags_that_are_used(client):
    p = tree.create_position(back_rank(0), ["d1d8"])
    PositionTag.objects.create(position=p, tag=Tag.objects.get(key="mate-in-1"))
    run(client, "tag.new", "Probe")
    result = run(client, "library.delete", c="tags", ids=["#mate-in-1", "#probe"])
    assert result["ok"] and result["message"] == "Deleted Probe · 1 in use stay"
    assert Tag.objects.filter(key="mate-in-1").exists() and not Tag.objects.filter(key="probe").exists()
    undo(client, result)
    assert Tag.objects.filter(key="probe").exists()


def test_game_rows_show_an_eval_thumbnail(client):
    from spaced_positions.analysis.models import Node
    from spaced_positions.library import importer

    importer.run('[White "A"]\n[Black "B"]\n[Result "*"]\n\n1. e4 e5 2. Nf3 Nc6 *\n', None, False)
    game = Game.objects.get()
    html = client.get("/lib/results/", {"c": "games"}).content.decode()
    assert "<svg class=\"spark\"" not in html  # no evaluations yet
    for cp, san in ((30, "e4"), (25, "e5"), (900, "Nf3"), (-40, "Nc6")):
        Node.objects.filter(game=game, san=san).update(eval_cp=cp)
    html = client.get("/lib/results/", {"c": "games"}).content.decode()
    assert 'aria-label="Evaluation over 4 moves"' in html and "0.0,7.5 21.3,7.6 42.7,0.0 64.0,8.6" in html  # +9 clipped at the top


# ── Moments (engine, python-chess, annotations) ───────────────────────────────────────────────────────────────

MOMENTS_PGN = '[White "A"]\n[Black "B"]\n[Result "*"]\n\n1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6?? 4. Nc3 *\n'


def moment_tags(game):
    from spaced_positions.library.models import NodeTag

    out = {}
    for san, key in NodeTag.objects.filter(node__game=game).values_list("node__san", "tag__key"):
        out.setdefault(san, set()).add(key)
    return out


def test_moments_from_stored_evaluations_chess_and_symbols():
    from spaced_positions.analysis.models import Node
    from spaced_positions.library import importer, moments
    from spaced_positions.library.models import NodeTag, TagDismissal

    importer.run(MOMENTS_PGN, None, False)
    game = Game.objects.get()
    for san, cp, mate in (("e4", 30, None), ("e5", 30, None), ("Qh5", 10, None), ("Nc6", 40, None), ("Bc4", 20, None),
                          ("Nf6", None, 1), ("Nc3", 50, None)):
        Node.objects.filter(game=game, san=san).update(eval_cp=cp, eval_mate=mate)
    result = moments.run(game, use_engine=False)
    assert result["engine"] == "stored"
    assert moment_tags(game) == {"Nf6": {"blunder", "allows-mate"}, "Nc3": {"missed-mate", "blunder", "missed-win"}}
    assert NodeTag.objects.get(node__san="Nf6", tag__key="blunder").evidence == "Annotated ??"  # the annotator's word first
    # removed by the user: not found again; a run withdraws only its own tags that no longer apply
    nc3 = Node.objects.get(game=game, san="Nc3")
    NodeTag.objects.filter(node=nc3, tag__key="missed-win").delete()
    TagDismissal.objects.create(node=nc3, tag=Tag.objects.get(key="missed-win"))
    Node.objects.filter(game=game, san="Nc3").update(eval_cp=None, eval_mate=1)  # 4.Nc3 still mates? not a blunder then
    result = moments.run(game, use_engine=False)
    assert moment_tags(game)["Nc3"] == {"missed-mate"} and result["withdrawn"] == 1


@pytest.mark.skipif(not __import__("shutil").which("stockfish"), reason="needs stockfish on the PATH")
def test_moments_with_the_local_engine():
    from spaced_positions.library import importer, moments

    importer.run(MOMENTS_PGN, None, False)
    game = Game.objects.get()
    result = moments.run(game)
    assert result["engine"] == "local"
    tags = moment_tags(game)
    assert {"blunder", "allows-mate"} <= tags["Nf6"] and {"missed-mate", "blunder", "missed-win"} <= tags["Nc3"]
    assert "only-move" not in tags.get("e4", set())


def test_moments_endpoint(client, monkeypatch):
    from spaced_positions.library import importer, moments

    monkeypatch.setattr(moments, "local_engine", lambda: None)
    importer.run(MOMENTS_PGN, None, False)
    game = Game.objects.get()
    data = client.post(f"/analysis/{game.uuid}/moments/", "{}", content_type="application/json").json()
    assert data["ok"] and data["message"].startswith("Moments without evaluations")  # python-chess and the symbols only
    assert "Erlaubt Matt" in data["html"] and "Verpasstes Matt" in data["html"]


@pytest.mark.django_db(transaction=True)
def test_big_import_in_the_background(client, monkeypatch):
    """Phase 7: a big PGN is uploaded as it is and imported in batches in the background; duplicates are left out."""
    import time

    from spaced_positions.library import importer

    monkeypatch.setattr(importer, "BATCH", 7)
    games = "".join(f'[Event "Big {i}"]\n[White "W{i}"]\n[Black "B"]\n[Result "1-0"]\n\n1. e4 e5 2. Nf3 Nc6 1-0\n\n' for i in range(30))
    pgn = games + '[Event "Big 3"]\n[White "W3"]\n[Black "B"]\n[Result "1-0"]\n\n1. e4 e5 2. Nf3 Nc6 1-0\n\n'  # one twice
    data = client.post("/lib/import/upload/", pgn.encode(), content_type="application/octet-stream").json()
    assert data["ok"]
    for _ in range(100):
        job = client.get(f"/lib/import/job/{data['id']}/").json()
        if job["done"]:
            break
        time.sleep(0.1)
    assert (job["games"], job["duplicates"], job["percent"]) == (30, 1, 100)
    assert Game.objects.filter(event__startswith="Big").count() == 30
    undo = client.post(f"/cmd/{job['undo']['command']}/", json.dumps({"args": job["undo"]["args"], "context": {}}), content_type="application/json").json()
    assert undo["ok"] and Game.objects.filter(deleted_at=None, event__startswith="Big").count() == 0
    assert not list((importer.JOBS[data["id"]].path.parent).glob("*.pgn"))  # the upload is gone
