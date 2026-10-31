"""PGN annotations (spec 15): lichess's evaluations, clocks and computer comments are read into the moves, kept out
of the comment text, and written back on export."""

from pathlib import Path

import pytest

from spaced_positions.analysis import pgn, tree
from spaced_positions.library import importer

pytestmark = pytest.mark.django_db

STUDY = (Path(__file__).parent / "fixtures" / "pgn" / "lichess-study-analysed.pgn").read_text(encoding="utf-8")
CLOCKS = """[Event "Club"]
[White "A"]
[Black "B"]
[TimeControl "300+3"]

1. e4 { [%eval 0.25,23] [%clk 0:04:58] } 1... e5 { [%clk 0:04:57] [%emt 0:00:03] } 2. Nf3 { A good move. [%eval 0.3] [%clk 0:04:52] } *
"""


def moves(game):
    return {(n.ply, n.san): n for n in tree.nodes(game) if n.parent_id}


def test_a_lichess_study_keeps_its_evaluations_out_of_the_comments():
    game = importer.run(STUDY, None, ready=True)["games"][0]
    by = moves(game)
    e4 = by[(1, "e4")]
    assert (e4.pgn_eval_cp, e4.pgn_eval_mate, e4.comment) == (18, None, "")  # a comment of commands only disappears
    c3 = by[(53, "c3")]
    assert c3.pgn_eval_cp == -80 and c3.comment == "Inaccuracy. Nf5 was best." and c3.nags == [6]  # ?! as a suffix
    mate = by[(88, "Be6#")]
    assert mate.pgn_eval_mate == 0 and mate.comment == "0-1 Black wins by checkmate."
    assert by[(87, "Bxb6")].pgn_eval_mate == -1
    assert tree.tree_json(game)["position"]["evalsFrom"] == "lichess"


def test_clocks_and_chessbase_depth_and_the_round_trip():
    game = importer.run(CLOCKS, None, ready=True)["games"][0]
    by = moves(game)
    e4, e5, nf3 = by[(1, "e4")], by[(2, "e5")], by[(3, "Nf3")]
    assert (e4.pgn_eval_cp, e4.pgn_eval_depth, e4.clock_ms) == (25, 23, 298_000)
    assert (e5.clock_ms, e5.emt_ms, e5.pgn_eval_cp) == (297_000, 3_000, None)
    assert nf3.comment == "A good move." and nf3.clock_ms == 292_000
    text = pgn.export_game(game)
    assert "[%eval 0.25,23]" in text and "[%clk 0:04:52]" in text and "A good move." in text
    again = moves(importer.run(text.replace('[White "A"]', '[White "C"]'), None, ready=True)["games"][0])
    assert [(n.pgn_eval_cp, n.pgn_eval_depth, n.clock_ms, n.emt_ms, n.comment) for n in again.values()] == \
           [(n.pgn_eval_cp, n.pgn_eval_depth, n.clock_ms, n.emt_ms, n.comment) for n in by.values()]


def test_the_tree_and_the_inspector(client):
    game = importer.run(STUDY + "\n\n" + CLOCKS, None, ready=True)["games"]
    study, clocks = game
    html = client.get(f"/analysis/{study.uuid}/").json()["html"]
    assert "[%eval" not in html
    assert 'mt-comment--engine' in html and '⚙ Inaccuracy</span><span class="mt-comment__more"> Nf5 was best.' in html
    c3 = moves(study)[(53, "c3")]
    assert "lichess -0.80" in client.get(f"/analysis/{study.uuid}/inspector/", {"node": c3.id}).content.decode()
    nf3 = moves(clocks)[(3, "Nf3")]
    facts = client.get(f"/analysis/{clocks.uuid}/inspector/", {"node": nf3.id}).content.decode()
    assert "PGN +0.30" in facts and "clock 4:52 · used 0:09" in facts  # 4:58 − 4:52 + 3 s increment
