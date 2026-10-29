"""Analysis: the move tree, its journal (undo/redo), puzzles set up from the analysis, the book-style rendering and
the endpoints of Analyse."""

import json

import pytest

from spaced_positions.analysis import puzzles as analysis_puzzles
from spaced_positions.analysis import render, tree
from spaced_positions.analysis.models import JournalEntry, Node
from spaced_positions.training import puzzles as training_puzzles
from spaced_positions.training.models import Puzzle

pytestmark = pytest.mark.django_db

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
RUY = ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"]


def post(client, url, body=None):
    return client.post(url, json.dumps(body or {}), content_type="application/json")


@pytest.fixture
def ruy():
    return tree.create_position(START, RUY, title="Ruy Lopez")


def line_of(position):
    """The main line in SAN."""
    kids = tree.kids_map(tree.nodes(position))
    node, out = tree.root(position), []
    while kids.get(node.id):
        node = kids[node.id][0]
        out.append(node.san)
    return out


def node_at(position, *sans):
    """The node reached by these moves (each a child of the previous)."""
    node = tree.root(position)
    for san in sans:
        node = node.kids.get(san=san)
    return node


# ── Tree operations ───────────────────────────────────────────────────────────────────────────────────────────


def test_create_position_has_the_moves_as_main_line(ruy):
    assert line_of(ruy) == ["e4", "e5", "Nf3", "Nc6", "Bb5"]
    data = tree.tree_json(ruy)
    assert data["position"]["title"] == "Ruy Lopez"
    assert len(data["nodes"]) == 6 and data["nodes"][0]["parent"] is None


def test_play_reuses_moves_and_adds_variations(ruy):
    e4 = node_at(ruy, "e4")
    same, created = tree.play(e4, "e7e5")
    assert not created and same.san == "e5"
    sicilian, created = tree.play(e4, "c7c5")
    assert created and sicilian.order == 1 and sicilian.ply == 2
    with pytest.raises(tree.TreeError):
        tree.play(e4, "e2e4")  # not legal for black


def test_promote_reorder_and_delete(ruy):
    e4 = node_at(ruy, "e4")
    c5, _ = tree.play(e4, "c7c5")
    tree.add_line(c5, ["g1f3", "d7d6"])
    tree.promote(node_at(ruy, "e4", "c5", "Nf3"))
    assert line_of(ruy) == ["e4", "c5", "Nf3", "d6"]
    tree.reorder(c5, 1)
    assert line_of(ruy)[:2] == ["e4", "e5"]
    parent = tree.delete(node_at(ruy, "e4", "c5"))
    assert parent.id == e4.id and [k.order for k in e4.kids.all()] == [0]
    with pytest.raises(tree.TreeError):
        tree.delete(tree.root(ruy))


def test_edit_keeps_one_move_symbol_and_one_evaluation(ruy):
    e4 = node_at(ruy, "e4")
    tree.edit(e4, {"nags": [1, 2, 16, 14], "mark": "nonsense", "color": "#AB12CD", "comment": "Best by test",
                   "shapes": [{"orig": "e2", "dest": "e4", "brush": "green"}, {"bad": 1}], "squares": {"e4": "green", "toolong": 1}})
    e4.refresh_from_db()
    assert e4.nags == [2, 14]
    assert e4.mark == "" and e4.color == "#ab12cd" and e4.comment == "Best by test"
    assert e4.shapes == [{"orig": "e2", "dest": "e4", "brush": "green"}] and e4.squares == {"e4": "green"}


def test_change_root_keeps_the_analysis_when_the_moves_stay_legal(ruy):
    # The same position with the h-pawn on h3: every move of the analysis is still legal.
    fen = "rnbqkbnr/pppppppp/8/8/8/7P/PPPPPPP1/RNBQKBNR w KQkq - 0 1"
    assert tree.change_root(ruy, fen) == 0
    assert line_of(ruy) == ["e4", "e5", "Nf3", "Nc6", "Bb5"]
    assert node_at(ruy, "e4").fen.startswith("rnbqkbnr/pppppppp/8/8/4P3/7P/")
    # Without the knight on g1, Nf3 is impossible: the correction needs force and drops the moves.
    without = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKB1R w KQkq - 0 1"
    with pytest.raises(tree.TreeError, match="5 moves would go"):
        tree.change_root(ruy, without)
    assert tree.change_root(ruy, without, force=True) == 5
    assert line_of(ruy) == [] and ruy.fen == without


# ── The journal ───────────────────────────────────────────────────────────────────────────────────────────────


def test_change_writes_a_journal_entry_and_restore_undoes_it(ruy):
    e4 = node_at(ruy, "e4")
    with tree.change(ruy, "Move c5"):
        c5, _ = tree.play(e4, "c7c5")
        tree.edit(c5, {"comment": "Sicilian"})
    entry = JournalEntry.objects.get()
    assert entry.label == "Move c5"
    tree.restore(ruy, entry.before)
    assert not Node.objects.filter(id=c5.id).exists()
    tree.restore(ruy, entry.after)
    back = Node.objects.get(id=c5.id)  # the same id: puzzles pointing at it stay linked
    assert back.comment == "Sicilian" and back.parent_id == e4.id


def test_nothing_changed_writes_no_entry_and_a_new_change_ends_the_redo_chain(ruy):
    with tree.change(ruy, "Nothing"):
        tree.play(node_at(ruy, "e4"), "e7e5")  # exists already
    assert not JournalEntry.objects.exists()
    with tree.change(ruy, "One"):
        tree.edit(node_at(ruy, "e4"), {"nags": [1]})
    JournalEntry.objects.update(undone=True)
    with tree.change(ruy, "Two"):
        tree.edit(node_at(ruy, "e4"), {"nags": [3]})
    assert list(JournalEntry.objects.values_list("label", flat=True)) == ["Two"]


# ── Puzzles from the analysis ─────────────────────────────────────────────────────────────────────────────────


def test_puzzle_set_up_marked_and_put_into_training(ruy):
    r = tree.root(ruy)
    with tree.change(ruy, "start"):
        analysis_puzzles.act(r, "start")
    puzzle = Puzzle.objects.get(position=ruy)
    assert not puzzle.active and puzzle.start_node_id == r.id
    # The main line, solver = white: e4 (e5) Nf3 (Nc6) Bb5
    assert training_puzzles.lines(puzzle.solution) == [RUY]
    # Another answer to e4, with a solver move after it, becomes a second line once all answers count.
    c5, _ = tree.play(node_at(ruy, "e4"), "c7c5")
    tree.play(c5, "g1f3")
    with tree.change(ruy, "answers"):
        assert analysis_puzzles.act(node_at(ruy, "e4"), "answers").startswith("All 2 answers")
    puzzle.refresh_from_db()
    assert sorted(training_puzzles.lines(puzzle.solution)) == sorted([RUY, ["e2e4", "c7c5", "g1f3"]])
    # The solution ends at Nf3 in the main line.
    with tree.change(ruy, "end"):
        analysis_puzzles.act(node_at(ruy, "e4", "e5", "Nf3"), "end")
    puzzle.refresh_from_db()
    assert ["e2e4", "e7e5", "g1f3"] in training_puzzles.lines(puzzle.solution)
    assert puzzle.cards.filter(in_solution=True).count() == 2
    assert puzzle.cards.filter(in_solution=False).count() == 1  # the old full line keeps its history
    with tree.change(ruy, "ready"):
        assert analysis_puzzles.act(r, "ready") == "Ready for training"
    puzzle.refresh_from_db()
    assert puzzle.active
    with pytest.raises(tree.TreeError):
        analysis_puzzles.act(node_at(ruy, "e4", "e5"), "also")  # an answer, not a solver move


def test_also_correct_adds_a_solver_alternative(ruy):
    analysis_puzzles.act(tree.root(ruy), "start")
    d4, _ = tree.play(tree.root(ruy), "d2d4")
    tree.add_line(d4, ["d7d5", "c2c4"])
    analysis_puzzles.act(d4, "also")
    analysis_puzzles.rebuild_all(ruy)
    puzzle = Puzzle.objects.get(position=ruy)
    assert [m["uci"] for m in puzzle.solution["moves"]] == ["e2e4", "d2d4"]


def test_undo_removes_an_untrained_puzzle_but_keeps_a_trained_one(ruy):
    r = tree.root(ruy)
    with tree.change(ruy, "start"):
        analysis_puzzles.act(r, "start")
    entry = JournalEntry.objects.get()
    puzzle = Puzzle.objects.get(position=ruy)
    tree.restore(ruy, entry.before)
    assert not Puzzle.objects.filter(id=puzzle.id).exists()
    tree.restore(ruy, entry.after)
    puzzle = Puzzle.objects.create(position=ruy, start_node=r, start_fen=r.fen, solution={"moves": []}, active=True, origin="analysis")
    analysis_puzzles.rebuild(puzzle)
    puzzle.cards.update(attempts=1)
    tree.restore(ruy, entry.before)
    puzzle.refresh_from_db()
    assert not puzzle.active  # trained since: out of training, its history stays


def test_roles_mark_the_puzzle_in_the_move_tree(ruy):
    analysis_puzzles.act(tree.root(ruy), "start")
    analysis_puzzles.rebuild_all(ruy)
    roles = analysis_puzzles.roles(ruy, tree.kids_map(tree.nodes(ruy)))
    assert roles[tree.root(ruy).id]["role"] == "start"
    assert roles[node_at(ruy, "e4").id]["role"] == "solver"
    assert roles[node_at(ruy, "e4", "e5").id]["role"] == "answer"
    assert roles[node_at(ruy, "e4", "e5", "Nf3", "Nc6", "Bb5").id].get("end")


def test_trainer_payload_names_the_position_and_start(ruy):
    analysis_puzzles.act(tree.root(ruy), "start")
    analysis_puzzles.rebuild_all(ruy)
    card = Puzzle.objects.get(position=ruy).cards.first()
    data = training_puzzles.payload(card)
    assert data["position"] == str(ruy.uuid) and data["startNode"] == tree.root(ruy).id


# ── Rendering ─────────────────────────────────────────────────────────────────────────────────────────────────


def test_render_is_a_book_with_variations_and_comments(ruy):
    e4 = node_at(ruy, "e4")
    c5, _ = tree.play(e4, "c7c5")
    tree.edit(e4, {"comment": "Best by test", "nags": [1]})
    html = render.render(ruy)
    assert html.startswith('<div class="movetree" data-movetree')
    assert '<span class="mt-num">1.</span><span class="mt-san">e4</span><span class="mt-nag">!</span>' in html
    assert '<span class="mt-num">1…</span><span class="mt-san">e5</span>' in html  # a black move after a comment gets its number
    assert 'data-variation="%d" data-more="0"><button type="button" class="mt-caret" data-fold' % c5.id in html  # a fold caret
    assert '<span class="mt-label">A</span>' in html
    assert html.count("data-node=") == 7  # six moves and the start position before them
    assert 'class="mt-start" data-node="%d"' % tree.root(c5.position).id in html
    empty = tree.create_position(START, [])
    assert "No moves yet" in render.render(empty)


# ── Endpoints ─────────────────────────────────────────────────────────────────────────────────────────────────


def test_load_play_and_undo_through_the_journal(client, ruy):
    pid = ruy.uuid
    data = client.get(f"/analysis/{pid}/").json()
    assert data["ok"] and data["journal"] is None and len(data["tree"]["nodes"]) == 6
    e4 = node_at(ruy, "e4")
    same = post(client, f"/analysis/{pid}/play/", {"parent": e4.id, "uci": "e7e5"}).json()
    assert same["journal"] is None and same["node"] == node_at(ruy, "e4", "e5").id
    played = post(client, f"/analysis/{pid}/play/", {"parent": e4.id, "uci": "c7c5"}).json()
    assert played["journal"]["label"] == "Move c7c5" and 'class="mt-variation"' in played["html"]
    assert post(client, f"/analysis/{pid}/play/", {"parent": e4.id, "uci": "e2e4"}).status_code == 422
    eid = played["journal"]["id"]
    assert [e["id"] for e in client.get("/journal/").json()["entries"]] == [eid]
    undone = post(client, f"/journal/{eid}/undo/").json()
    assert undone["message"] == "Undone: Move c7c5" and len(undone["tree"]["nodes"]) == 6
    assert post(client, f"/journal/{eid}/undo/").status_code == 409
    redone = post(client, f"/journal/{eid}/redo/").json()
    assert len(redone["tree"]["nodes"]) == 7


def test_edit_line_reorder_promote_delete_endpoints(client, ruy):
    pid, e4 = ruy.uuid, node_at(ruy, "e4")
    assert post(client, f"/analysis/{pid}/edit/", {"node": e4.id, "mark": "good"}).json()["journal"]["label"] == "Mark e4"
    line = post(client, f"/analysis/{pid}/line/", {"parent": e4.id, "ucis": ["c7c5", "g1f3"]}).json()
    nf3 = line["node"]
    assert post(client, f"/analysis/{pid}/promote/", {"node": nf3}).json()["ok"]
    assert line_of(ruy)[:3] == ["e4", "c5", "Nf3"]
    c5 = node_at(ruy, "e4", "c5")
    assert post(client, f"/analysis/{pid}/reorder/", {"node": c5.id, "step": "down"}).json()["ok"]
    assert post(client, f"/analysis/{pid}/delete/", {"node": c5.id}).json()["node"] == e4.id
    assert post(client, f"/analysis/{pid}/delete/", {"node": tree.root(ruy).id}).status_code == 422


def test_correcting_the_position_asks_before_dropping_moves(client, ruy):
    without = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKB1R w KQkq - 0 1"
    conflict = post(client, f"/analysis/{ruy.uuid}/position/", {"fen": without})
    assert conflict.status_code == 200 and conflict.json()["conflict"] and not conflict.json()["ok"]
    forced = post(client, f"/analysis/{ruy.uuid}/position/", {"fen": without, "force": True}).json()
    assert forced["message"] == "Position corrected; 5 moves of the analysis were dropped"


def test_replace_create_puzzle_inspector_and_search(client, ruy):
    pid = ruy.uuid
    replaced = post(client, f"/analysis/{pid}/replace/", {"start": START, "moves": ["d2d4", "d7d5"]}).json()
    assert replaced["ok"] and line_of(ruy) == ["d4", "d5"]
    root = tree.root(ruy).id
    setup = post(client, f"/analysis/{pid}/puzzle/", {"node": root, "action": "start"}).json()
    assert setup["message"].startswith("Puzzle set up") and setup["tree"]["puzzles"][0]["start"] == root
    html = client.get(f"/analysis/{pid}/inspector/", {"node": root}).content.decode()
    assert "data-comment-form" in html
    pane = client.get(f"/analysis/{pid}/puzzle-pane/", {"node": root, "list": "2/5"}).content.decode()
    assert "a draft: not trained yet" in pane and "pzpane__where--start" in pane and "Position 3 of 5 in the list" in pane
    assert 'data-args="also" title="Puzzle: go to one of the solver&#x27;s moves" aria-disabled="true"' in pane
    on_d4 = client.get(f"/analysis/{pid}/puzzle-pane/", {"node": node_at(ruy, "d4").id}).content.decode()
    assert "pzpane__where--solver" in on_d4 and "1 line, one card" in on_d4
    move = client.get(f"/analysis/{pid}/inspector/", {"node": node_at(ruy, "d4").id}).content.decode()
    assert 'data-cmd="analysis.nag"' in move
    created = post(client, "/analysis/new/", {"start": START, "moves": ["g1f3"], "title": "Réti"}).json()
    assert created["ok"]
    found = client.get("/positions/search/", {"q": "réti"}).json()["positions"]
    assert [p["id"] for p in found] == [created["position"]]
    assert post(client, "/analysis/new/", {"start": "8/8/8/8/8/8/8/8 w - - 0 1"}).status_code == 422
    assert client.get("/analysis/not-a-uuid/").status_code == 404


# ── The Puzzle pane ───────────────────────────────────────────────────────────────────────────────────────────


def test_puzzle_pane_black_to_move_also_correct_and_all_answers():
    # after 1.e4: black solves, 1…e5 2.Nf3 (2.Nc3) Nc6, and 1…c5 as another solver move
    position = tree.create_position("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1", ["e7e5", "g1f3", "b8c6"])
    tree.play(node_at(position, "e5"), "b1c3")
    tree.add_line(node_at(position, "e5", "Nc3"), ["g8f6"])
    tree.play(tree.root(position), "c7c5")
    root = tree.root(position)
    analysis_puzzles.act(root, "start")
    pane = analysis_puzzles.pane(position, root)
    assert pane["side"] == "Black" and pane["start_label"] == "from the start position" and pane["kind"] == "start"
    assert [[m.san for m in line["moves"]] for line in pane["lines"]] == [["e5", "Nf3", "Nc6"]]
    assert pane["can_also"] and pane["why"].startswith("At the start")
    c5 = node_at(position, "c5")
    assert analysis_puzzles.pane(position, c5)["kind"] == "outside"
    analysis_puzzles.act(c5, "also")
    also = analysis_puzzles.pane(position, c5)
    assert also["kind"] == "also" and also["also_on"]
    e5 = node_at(position, "e5")
    analysis_puzzles.act(e5, "answers")  # 2.Nc3 counts too: a second line
    lines = analysis_puzzles.pane(position, e5)["lines"]
    assert [[m.san for m in line["moves"]] for line in lines] == [["e5", "Nf3", "Nc6"], ["e5", "Nc3", "Nf6"]]
    answer = analysis_puzzles.pane(position, node_at(position, "e5", "Nf3"))
    assert answer["kind"] == "answer" and answer["why"].startswith("On an answer") and answer["can_also"]


def test_puzzle_pane_of_a_game_offers_a_position_of_its_own(client):
    from spaced_positions.library import importer

    game = importer.run('[White "A"]\n[Black "B"]\n\n1. e4 e5 2. Nf3 *', None, ready=True)["games"][0]
    html = client.get(f"/analysis/{game.uuid}/puzzle-pane/").content.decode()
    assert "Puzzles come from positions, not from games" in html and 'data-cmd="analysis.newposition"' in html
