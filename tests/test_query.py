"""The query language (spec 11 §3): parsing (pure) and compiling to querysets for each collection."""

from datetime import timedelta

import pytest
from django.utils import timezone

from spaced_positions.analysis import puzzles as analysis_puzzles
from spaced_positions.analysis import tree
from spaced_positions.library.models import Game, Player, PositionTag, SavedQuery, Source, Tag
from spaced_positions.library.query import parse, run
from spaced_positions.library.text import fold
from spaced_positions.training.models import Position

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
ROOK_ENDING = "8/8/4k3/8/8/4K3/4R3/4r3 b - - 0 1"


# ── Parsing ───────────────────────────────────────────────────────────────────────────────────────────────────


def test_parse_terms_values_negation_and_spans():
    text = 'motif:gabel,spiess diff:>=3 -is:diagram "back rank" #opfer'
    terms = parse(text).terms()
    assert [(t.key, t.op, t.values, t.neg) for t in terms] == [
        ("motif", "", ["gabel", "spiess"], False),
        ("diff", ">=", ["3"], False),
        ("is", "", ["diagram"], True),
        ("", "", ["back rank"], False),
        ("#", "", ["opfer"], False),
    ]
    assert text[terms[3].start:terms[3].end] == '"back rank"'


def test_parse_groups_or_and_problems():
    parsed = parse("(src:polgar or src:nunn) -(motif:gabel) diff:")
    root = parsed.root.alternatives[0]
    assert len(root[0].alternatives) == 2 and root[1].neg
    assert [p.message for p in parsed.problems] == ["diff: needs a value"]
    assert [p.message for p in parse("(a b").problems] == ["this ( isn't closed"]
    assert [p.message for p in parse("a ) b").problems] == ["no ( for this )"]
    assert len(parse("a or b").root.alternatives) == 2
    assert parse("").terms() == []


def test_fold():
    assert fold("Spieß") == "spiess" and fold("Qualitätsopfer") == "qualitatsopfer"


# ── Positions ─────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def library(db):
    polgar = Source.objects.create(title="5334 Problems", short="Polgár 5334", authors="László Polgár")
    fork = tree.create_position(START, ["e2e4", "e7e5", "g1f3"], title="Fork drill")
    fork.source, fork.source_page, fork.difficulty_override = polgar, "41", 4
    fork.save()
    PositionTag.objects.create(position=fork, tag=Tag.objects.get(key="knight-fork"))
    ending = tree.create_position(ROOK_ENDING, [], title="Rook ending")
    ending.difficulty_override = 2
    ending.save()
    PositionTag.objects.create(position=ending, tag=Tag.objects.get(key="pin"), origin="suggested")
    diagram = Position.objects.create(fen=START, canonical="x", title="Illustration", diagram=True, source_text="Nunn, Tactics")
    analysis_puzzles.act(tree.root(fork), "start")
    return {"fork": fork, "ending": ending, "diagram": diagram}


def titles(query, collection="positions"):
    result = run(query, collection)
    assert result.problems == [], result.problems
    return sorted(str(x) for x in result.queryset)


def test_tag_terms_follow_the_hierarchy(library):
    assert titles("motif:gabel") == ["Fork drill"]  # Gabel → Springergabel (knight-fork)
    assert titles("motif:fork") == ["Fork drill"]  # the English name
    assert titles("motif:=gabel") == []  # the tag alone, not its descendants
    assert titles("#springergabel") == ["Fork drill"]
    assert titles("tag:pin") == []  # suggested tags don't count
    result = run("motif:nonsense")
    assert [p.message for p in result.problems] == ["no tag 'nonsense' in motif"]


def test_numbers_text_source_and_states(library):
    assert titles("diff:>=3") == ["Fork drill"]
    assert titles("diff:1..2") == ["Rook ending"]
    assert titles("side:b") == ["Rook ending"]
    assert titles("src:polgar page:41") == ["Fork drill"]
    assert titles("src:nunn") == ["Illustration"]
    assert titles('"rook end"') == ["Rook ending"]
    assert titles("knight") == ["Fork drill"]  # text finds tag names too
    assert titles("has:analysis") == ["Fork drill"]
    assert titles("has:puzzle is:draft") == ["Fork drill"]
    assert titles("no:analysis -is:diagram") == ["Rook ending"]
    assert titles("material:KRvKR") == ["Rook ending"]
    assert titles("pieces:<=4") == ["Rook ending"]
    assert titles("is:diagram or diff:4") == ["Fork drill", "Illustration"]
    assert titles("fen:8/8/4k3") == ["Rook ending"]


def test_trash_dates_sort_and_saved_queries(library):
    library["ending"].deleted_at = timezone.now()
    library["ending"].save()
    assert "Rook ending" not in titles("")
    assert titles("is:trash") == ["Rook ending"]
    old = library["diagram"]
    Position.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=40))
    assert titles("created:<7d") == ["Fork drill"]
    assert titles("created:>30d") == ["Illustration"]
    ordered = [p.title for p in run("sort:-difficulty").queryset]
    assert ordered[0] == "Fork drill"
    assert [p.message for p in run("sort:nonsense").problems][0].startswith("sort: not 'nonsense'")
    SavedQuery.objects.create(key="hard", name="Hard ones", query="diff:>=4")
    assert titles("in:q:hard") == ["Fork drill"]
    assert [p.message for p in run("colour:red").problems] == ["colour: not a key for positions"]


# ── Puzzles, games, the rest ──────────────────────────────────────────────────────────────────────────────────


def test_puzzle_terms(library):
    puzzle = library["fork"].puzzles.get()
    analysis_puzzles.act(tree.root(library["fork"]), "ready")
    analysis_puzzles.rebuild(puzzle)
    puzzle.cards.update(attempts=4, successes=1, lapses=2, state="review", due=timezone.now() - timedelta(hours=1),
                        last_seen=timezone.now() - timedelta(days=3))
    assert len(run("due:today", "puzzles").queryset) == 1
    assert len(run("lapses:>=2 success:<50 motif:gabel", "puzzles").queryset) == 1
    assert len(run("state:new", "puzzles").queryset) == 0
    assert len(run("last:<7d diff:4", "puzzles").queryset) == 1


def test_games_players_sources_tags(db):
    tal = Player.objects.create(key="tal", name="Tal, Mikhail", aliases=["Michail Tal"])
    Game.objects.create(white=tal, white_name="Tal, M.", black_name="Larsen, Bent", result="1-0", year=1965, eco="B90",
                        event="Candidates", start_fen=START, white_elo=2620)
    Game.objects.create(white_name="Carlsen", black_name="Nepo", result="1/2-1/2", year=2021, start_fen=START)
    assert titles("player:@tal", "games") == ["Tal, M. – Larsen, Bent 1-0 1965"]
    assert titles("white:michail", "games") == ["Tal, M. – Larsen, Bent 1-0 1965"]
    assert titles("result:draw year:>2000", "games") == ["Carlsen – Nepo 1/2-1/2 2021"]
    assert titles("eco:B9 elo:>=2600", "games") == ["Tal, M. – Larsen, Bent 1-0 1965"]
    assert titles("candidates", "games") == ["Tal, M. – Larsen, Bent 1-0 1965"]
    assert titles("mikhail", "players") == ["Tal, Mikhail"]
    Source.objects.create(title="Schach ohne Partner", authors="Grasemann")
    assert titles("grasemann", "sources") == ["Schach ohne Partner"]
    assert "Gabel" in titles("field:motif gabel", "tags")


# ── Sources, words and the order of a book ────────────────────────────────────────────────────────────────────


@pytest.fixture
def books(db):
    made = {}
    for title, authors in (("Chess Monkeys Level 1", "Roman Vidonyak"), ("Chess Monkeys Level 2", "Roman Vidonyak"),
                           ("CHESS - 5334 Problems", "László Polgár")):
        source = Source.objects.create(title=title, authors=authors)
        for n in (12, 2, 9):
            p = tree.create_position(START, [], title=f"{title} {n}")
            p.source, p.source_page, p.source_ref = source, str(n // 4 + 1), f"Nr. {n}"
            p.save()
            made[(title, n)] = p
    return made


def count(text):
    return run(text, "positions").queryset.count()


def test_one_source_exactly_or_all_with_the_words(books):
    assert count('src:"Chess Monkeys Level 1"') == 3  # exactly that one
    assert count("src:chess") == 9 and count("src:monkeys") == 6
    assert count('src:"monkeys 2"') == 3  # all the words, in any order
    assert count("src:polgar") == 3  # the authors count too
    source = Source.objects.get(title="CHESS - 5334 Problems")
    assert count(f"src:s{source.pk}") == 3


def test_words_find_titles_sources_tags_and_comments(books):
    p = books[("Chess Monkeys Level 1", 2)]
    p.description = "Ein Spieß gewinnt die Dame"
    p.save()
    root = tree.root(p)
    move, _ = tree.play(root, "e2e4")
    tree.edit(move, {"comment": "The only good move"})
    assert count("spiess") == 1 and count("SPIESS") == 1  # case and accents don't matter
    assert count("only good") == 1  # two words: both somewhere
    assert count('"only good"') == 1 and count('"good only"') == 0
    assert count("vidonyak") == 6  # the source's authors


def test_sort_by_source_page_and_diagram(books):
    titles = [p.title for p in run('src:"Chess Monkeys Level 2" sort:source', "positions").queryset]
    assert titles == ["Chess Monkeys Level 2 2", "Chess Monkeys Level 2 9", "Chess Monkeys Level 2 12"]  # 9 before 12
    assert [p.ref_number for p in run("src:polgar sort:-diagram", "positions").queryset] == [12, 9, 2]


def test_facets_pick_one_source_and_training_follows_the_order(books, client):
    import json
    import re

    html = client.get("/lib/facets/", {"q": 'src:"Chess Monkeys Level 1"'}).content.decode()
    from html import unescape

    on = [unescape(t) for t in re.findall(r'filters__row is-on"[^>]*data-term="([^"]*)"', html)]
    assert on == ['src:"Chess Monkeys Level 1"']  # only the chosen one is on
    for (title, n), p in books.items():
        if title == "Chess Monkeys Level 1":
            root = tree.root(p)
            tree.play(root, "e2e4")
            analysis_puzzles.act(root, "start")
            analysis_puzzles.act(root, "ready")
            analysis_puzzles.rebuild_all(p)
    data = client.post("/lib/cards/", json.dumps({"c": "positions", "q": 'src:"Chess Monkeys Level 1" sort:diagram'}),
                       content_type="application/json").json()
    from spaced_positions.training.models import Card

    order = [Card.objects.get(uuid=u).puzzle.position.ref_number for u in data["cards"]]
    assert order == [2, 9, 12]  # in the order of the diagrams


def test_a_star_is_ignored(books):
    assert count("src:monkeys*") == 6 and count('src:"Chess Monkeys*"') == 6
    assert count("Level*") == count("Level")
