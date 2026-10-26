"""Puzzle packs (spec 09 §12) from the coach to a student: export (format, personal copies, the log),
import (preview, the pack as source, duplicates, unknown tags) and a newer version that keeps the student's training."""

import io
import json
import zipfile

import pytest

from spaced_positions.analysis import puzzles as analysis_puzzles
from spaced_positions.analysis import tree
from spaced_positions.library import packs
from spaced_positions.library.models import Pack, PackExport, PositionTag, ReceivedPack, Source, Tag
from spaced_positions.training.models import Attempt, Card, Position
from tests.factories import back_rank

pytestmark = pytest.mark.django_db

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


@pytest.fixture
def coach():
    book = Source.objects.create(title="Mating Patterns", short="MP", authors="A. Author")
    made = []
    for i in range(3):
        p = tree.create_position(back_rank(i), ["d1d8"], title=f"Back rank {i}")
        p.source, p.source_page, p.source_ref, p.objective = book, "12", f"Nr. {i + 1}", "Mate in 1"
        p.save()
        root = tree.root(p)
        tree.edit(p.nodes.get(san="Rd8#"), {"comment": "The back rank!", "nags": [1]})
        PositionTag.objects.create(position=p, tag=Tag.objects.get(key="back-rank-mate"))
        analysis_puzzles.act(root, "start")
        analysis_puzzles.act(root, "ready")
        analysis_puzzles.rebuild_all(p)
        made.append(p)
    custom = Tag.objects.create(key="coach-favourite", name="Lieblinge", field=Tag.objects.get(key="fork").field)
    PositionTag.objects.create(position=made[0], tag=custom)
    return made


def files(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n).decode() for n in z.namelist()}


def forget(positions):
    """The student's database doesn't have them: remove the coach's copies (test data only)."""
    ids = [p.pk for p in positions]
    Card.objects.filter(puzzle__position_id__in=ids).delete()
    Position.objects.filter(pk__in=ids).delete()
    Tag.objects.filter(key="coach-favourite").delete()


def test_export_format_and_log(coach):
    pack = Pack.objects.create(title="Back ranks", description="Three classics")
    data, manifest = packs.build(Position.objects.filter(pk__in=[p.pk for p in coach]), pack, author="Coach C", student="Ben")
    assert manifest["version"] == 1 and manifest["for"] == "Ben" and manifest["positions"] == 3 and manifest["puzzles"] == 3
    assert manifest["licence"] == packs.DEFAULT_LICENCE
    f = files(data)
    first = json.loads(f["positions.jsonl"].splitlines()[0])
    assert first["moves"] == "1. Rd8# $1 { The back rank! }" and first["puzzles"] == [{"start": "", "active": True, "ends": [], "also": [], "replies": []}]
    assert first["tags"][0] == "back-rank-mate" and json.loads(f["sources.json"]) == [{"title": "Mating Patterns", "short": "MP", "authors": "A. Author", "kind": "book"}]
    assert [t["key"] for t in json.loads(f["tags.json"])] == ["coach-favourite"]  # the built-in vocabulary needn't travel
    log = PackExport.objects.get()
    assert (log.version, log.student, log.positions, len(log.copy)) == (1, "Ben", 3, 12)
    assert len(f["positions.jsonl"]) / 3 < 400  # compact


def test_import_preview_and_training_survive_a_newer_version(coach):
    pack = Pack.objects.create(title="Back ranks")
    data, manifest = packs.build(Position.objects.filter(pk__in=[p.pk for p in coach]), pack, author="Coach C", student="Ben")
    uuids = sorted(str(p.uuid) for p in coach)
    forget(coach)
    preview = packs.scan(data)
    assert preview["counts"] == {"new": 3, "update": 0, "duplicate": 0, "yours": 0} and preview["for"] == "Ben"
    assert preview["unknown_tags"] == ["coach-favourite"] and preview["earlier"] is None
    report = packs.run(data)
    assert report.counts["new"] == 3 and report.counts["puzzles"] == 3 and report.counts["tags"] == 1
    got = Position.objects.filter(uuid__in=uuids)
    assert got.count() == 3 and {p.source.title for p in got} == {"Mating Patterns"}  # the book stays the source
    assert {p.pack_id for p in got} == {ReceivedPack.objects.get().pk}
    from spaced_positions.library.query import run as query

    assert query(f"src:s{ReceivedPack.objects.get().source_id}", "positions").queryset.count() == 3  # the pack finds them too
    p = got.get(title="Back rank 0")
    assert p.source_text == "MP · p. 12 · Nr. 1" and p.nodes.get(san="Rd8#").comment == "The back rank!"
    assert {t.key for t in p.tags.all()} == {"back-rank-mate", "coach-favourite"}
    received = ReceivedPack.objects.get()
    assert received.credit == "from Coach C for Ben"
    # the student trains a card
    card = Card.objects.get(puzzle__position=p)
    Attempt.objects.create(card=card, success=True, ms=3000)
    # version 2: a new comment and a new answer move in the coach's analysis
    f = files(data)
    lines = [json.loads(line) for line in f["positions.jsonl"].splitlines()]
    lines[0]["moves"] = "1. Rd8# $1 { The back rank, again! } ( 1. Rd7 )"
    manifest2 = json.loads(f["manifest.json"]) | {"version": 2}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest2))
        z.writestr("positions.jsonl", "\n".join(json.dumps(x) for x in lines))
        z.writestr("sources.json", f["sources.json"])
        z.writestr("tags.json", f["tags.json"])
    assert packs.scan(buf.getvalue())["counts"]["update"] == 3 and packs.scan(buf.getvalue())["earlier"] == 1
    report = packs.run(buf.getvalue())
    assert report.counts["updated"] == 3 and report.counts["new"] == 0
    p.refresh_from_db()
    assert p.nodes.filter(san="Rd7").exists() and ReceivedPack.objects.get().version == 2
    assert Attempt.objects.filter(card=card).count() == 1 and Card.objects.filter(pk=card.pk).exists()  # training kept


def test_yours_and_personal_copies_stay_out(coach):
    pack = Pack.objects.create(title="Back ranks")
    data, _ = packs.build(Position.objects.filter(pk__in=[p.pk for p in coach]), pack)
    assert packs.scan(data)["counts"]["yours"] == 3  # the coach imports their own pack: nothing doubles
    assert packs.run(data).counts["yours"] == 3
    # a student with a personal copy doesn't pass it on by accident
    personal, _ = packs.build(Position.objects.filter(pk__in=[p.pk for p in coach]), pack, student="Ben")
    forget(coach)
    packs.run(personal)
    mine = Pack.objects.create(title="Ben's own")
    with pytest.raises(packs.PackError):
        packs.build(Position.objects.all(), mine)
    _, manifest = packs.build(Position.objects.all(), mine, include_received=True)
    assert manifest["positions"] == 3


def test_round_trip_keeps_games_marks_and_move_tags_and_can_be_packed_again(coach):
    """The coach's own library moves to a new installation as packs, and is packed again for a student from there."""
    from spaced_positions.library.importer import Players, import_game
    from spaced_positions.library.models import Game, NodeTag

    p = coach[0]
    rd8 = p.nodes.get(san="Rd8#")
    rd8.mark = "good"
    rd8.save()
    NodeTag.objects.create(node=rd8, tag=Tag.objects.get(key="fork"), origin="manual")
    PositionTag.objects.create(position=p, tag=Tag.objects.get(key="mate-in-1"), origin="auto")
    game = next(iter(analysis_puzzles_free_games()))
    g = import_game(game, Players(), source=Source.objects.get(title="Mating Patterns"))
    pack = Pack.objects.create(title="Mating Patterns", licence="For the owner of the book")
    data, manifest = packs.build(Position.objects.filter(pk__in=[x.pk for x in coach]), pack, author="Coach C",
                                 games=Game.objects.filter(pk=g.pk))
    assert manifest["games"] == 1 and "games.jsonl" in files(data)
    game_uuid = str(g.uuid)
    forget(coach)
    Game.objects.filter(pk=g.pk).delete()
    assert packs.scan(data)["game_counts"] == {"new": 1, "update": 0, "yours": 0}
    report = packs.run(data)
    assert report.counts["new"] == 3 and report.counts["games"] == 1
    p = Position.objects.get(title="Back rank 0")
    rd8 = p.nodes.get(san="Rd8#")
    assert rd8.mark == "good" and NodeTag.objects.filter(node=rd8, tag__key="fork").exists()
    assert p.tag_links.get(tag__key="mate-in-1").origin == "auto" and p.tag_links.get(tag__key="back-rank-mate").origin == "manual"
    g = Game.objects.get(uuid=game_uuid)
    assert g.white_name == "Anderssen" and g.source.title == "Mating Patterns" and g.nodes.count() > 5
    assert p.citation == "MP · p. 12 · Nr. 1"  # not a personal pack: the book alone
    # packed again for a student, from the new installation: the book travels along
    again, m2 = packs.build(Position.objects.filter(pack__isnull=False), Pack.objects.create(title="For Ben"), author="Coach C", student="Ben")
    assert m2["positions"] == 3 and json.loads(files(again)["sources.json"])[0]["title"] == "Mating Patterns"


def analysis_puzzles_free_games():
    from spaced_positions.analysis import pgn as pgn_io

    return pgn_io.read_games('''[White "Anderssen"]
[Black "Kieseritzky"]
[Result "1-0"]

1. e4 e5 2. f4 exf4 3. Bc4 Qh4+ 4. Kf1 b5 5. Bxb5 Nf6 1-0
''')


def test_not_a_pack():
    with pytest.raises(packs.PackError):
        packs.read(b"not a zip")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps({"format": 99, "pack": "x"}))
        z.writestr("positions.jsonl", "")
    with pytest.raises(packs.PackError, match="newer version"):
        packs.read(buf.getvalue())


# ── First run, licences, updates ──────────────────────────────────────────────────────────────────────────────


def test_first_run_welcome_until_there_is_a_position(client):
    html = client.get("/m/home/").content.decode()
    assert "your library is empty" in html and 'data-cmd="pack.import"' in html
    tree.create_position(back_rank(0), ["d1d8"])
    assert "your library is empty" not in client.get("/m/home/").content.decode()


def test_licences_name_the_source_and_every_component(client):
    from spaced_positions import SOURCE_URL

    html = client.get("/settings/rows/").content.decode()
    assert SOURCE_URL in html and "GNU General Public License" in html
    for name in ("chessground.min.js", "stockfish-17.1-lite-single-03e3232.wasm", "Pieces: Merida", "chess 1."):
        assert name in html, name


def test_update_check_is_opt_in_and_compares_versions(client, monkeypatch, settings, tmp_path):
    from spaced_positions.core import updates
    from spaced_positions.core.models import Preferences

    settings.DATA_DIR = tmp_path
    calls = []

    class Reply(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake(request, timeout):
        calls.append(request.full_url)
        return Reply(json.dumps([{"tag_name": "nightly", "html_url": "https://example.test/nightly"},
                                 {"tag_name": "v9.1.0", "draft": True, "html_url": "https://example.test/draft"},
                                 {"tag_name": "v9.0.0-beta", "prerelease": True, "html_url": "https://example.test/release"},
                                 {"tag_name": "v1.0.0", "html_url": "https://example.test/old"}]).encode())

    monkeypatch.setattr(updates.urllib.request, "urlopen", fake)
    assert client.get("/app/update/").json() == {"available": None} and calls == []  # off: nothing is asked
    Preferences.objects.update_or_create(pk=Preferences.current().pk, defaults={"settings": {"app.updates": True}})
    answer = client.get("/app/update/").json()
    # the newest version, a pre-release too; not a draft, not the nightly build
    assert {k: answer[k] for k in ("available", "url")} == {"available": "9.0.0-beta", "url": "https://example.test/release"}
    assert answer["how"]  # how this copy is updated (install.py): shown with the notice
    client.get("/app/update/")
    assert len(calls) == 1 and "/releases?" in calls[0]  # once a day
    assert updates.version_tuple("v0.10.0") > updates.version_tuple("0.9.3")


def test_licence_text_and_notices(client):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert (root / "LICENSE").read_text(encoding="utf-8") == (root / "spaced_positions/static/licences/GPL-3.0.txt").read_text(encoding="utf-8")
    text = client.get("/licences/notices.txt").content.decode()
    for name in ("chessground.min.js", "Piece set Merida", "Django", "waitress", "python-chess" if "python-chess" in text else "chess",
                 "Python Software Foundation", "GNU GENERAL PUBLIC LICENSE"):
        assert name in text, name
    assert text.count("Version 3, 29 June 2007") == 1  # the GPL once, at the end
