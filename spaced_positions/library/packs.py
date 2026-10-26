"""Puzzle packs (spec 09 §12): a coach's own material, as a file for students.

A pack (`.sppack`) is a zip: `manifest.json`, `positions.jsonl` (one compact JSON object a line: the position, its
analysis as PGN movetext, its tags, its puzzles, and the marks and tags of its moves by tree path like `0.1.0`),
`games.jsonl` (games the same way), `sources.json` (the books they cite) and `tags.json` (tags a receiver may not
have). Tags set by detection are written `~key`. Training history and private notes are never in a pack.

Importing keeps each position's book as its source and links it to the pack (so `src:` finds the book and the
pack), and keeps each uuid, so a newer version of the same pack updates what came with the old one: new moves,
comments and tags are added, puzzles follow the new marks, and the student's cards and history stay."""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from dataclasses import dataclass, field

import chess
import chess.pgn
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext, gettext_noop

from spaced_positions import chesslogic
from spaced_positions.analysis import pgn as pgn_io
from spaced_positions.analysis import tree
from spaced_positions.training.models import Position, Puzzle

from .models import Game, GameTag, NodeTag, Pack, PackExport, PositionTag, ReceivedPack, Source, Tag, TagField
from .vocabulary import DATA as VOCABULARY

TagLinkOrigin = PositionTag.Origin

FORMAT = 1
SUFFIX = ".sppack"
DEFAULT_LICENCE = gettext_noop("For the personal use of the student it was made for. Please don't pass it on.")
MAX_BYTES = 200_000_000  # a pack file


class PackError(ValueError):
    pass


# ── Trees as paths ────────────────────────────────────────────────────────────────────────────────────────────


def paths_of(owner) -> dict[int, str]:
    """Each move's path from the root: the index among its siblings at each step (`0.1.0`); the root is ''."""
    nodes = tree.nodes(owner)
    kids = tree.kids_map(nodes)
    root = next(n for n in nodes if n.parent_id is None)
    out, stack = {root.id: ""}, [root]
    while stack:
        node = stack.pop()
        for i, kid in enumerate(kids.get(node.id, [])):
            out[kid.id] = f"{out[node.id]}.{i}" if out[node.id] else str(i)
            stack.append(kid)
    return out


def movetext(owner) -> str:
    """The analysis (or a game's moves) as PGN movetext (no headers): variations, comments, NAGs, drawings."""
    game = pgn_io._game_of(owner, {})
    text = game.accept(chess.pgn.StringExporter(headers=False, columns=None)).strip()
    return "" if text in ("*", "") else text.removesuffix(" *")


def tag_keys(links) -> list[str]:
    """`key` for a tag set by hand, `~key` for one set by detection; suggestions stay out."""
    return [("~" if link.origin == "auto" else "") + link.tag.key for link in links if link.origin != "suggested"]


def tree_extras(owner, paths: dict[int, str]) -> dict:
    """What movetext doesn't carry, by path: the marks (good, dubious, bad), line colours, filled squares, move tags."""
    out = {"marks": {}, "colors": {}, "squares": {}, "mtags": {}}
    for node in tree.nodes(owner):
        path = paths.get(node.id)
        if path is None:
            continue
        if node.mark:
            out["marks"][path] = node.mark
        if node.color:
            out["colors"][path] = node.color
        if node.squares:
            out["squares"][path] = node.squares
    links = NodeTag.objects.filter(node_id__in=paths).select_related("tag")
    by_node = {}
    for link in links:
        by_node.setdefault(link.node_id, []).append(link)
    for node_id, node_links in by_node.items():
        keys = tag_keys(node_links)
        if keys:
            out["mtags"][paths[node_id]] = keys
    return {k: v for k, v in out.items() if v}


# ── Export ────────────────────────────────────────────────────────────────────────────────────────────────────


def builtin_tags() -> set[str]:
    return {t["key"] for t in json.loads(VOCABULARY.read_text(encoding="utf-8"))["tags"]}


def exportable(rows):
    """Positions and games from a pack made for someone else stay out (spec 09 §12: packs don't spread by accident)."""
    return rows.exclude(pack__student__gt="")


class _Writer:
    """Collects the sources and the tags a receiver may lack while records are written."""

    def __init__(self):
        self.builtin = builtin_tags()
        self.sources, self.index, self.extra_tags = [], {}, {}

    def source(self, s) -> int | None:
        if s is None or s.kind == Source.Kind.PACK:
            return None
        if s.pk not in self.index:
            self.index[s.pk] = len(self.sources)
            self.sources.append({k: v for k, v in {"title": s.title, "short": s.short, "authors": s.authors, "year": s.year,
                                                    "publisher": s.publisher, "kind": s.kind, "url": s.url}.items() if v})
        return self.index[s.pk]

    def note_tags(self, links):
        for link in links:
            t = link.tag
            if link.origin != "suggested" and t.key not in self.builtin:
                self.extra_tags[t.key] = {"key": t.key, "name": t.name, "name_en": t.name_en, "field": t.field.key,
                                          "parent": t.parent.key if t.parent_id else None, "aliases": t.aliases}

    @staticmethod
    def line(rec: dict) -> str:
        return json.dumps({k: v for k, v in rec.items() if v not in (None, "", [], {})}, ensure_ascii=False, separators=(",", ":"))


def position_record(p, w: _Writer) -> dict:
    paths = paths_of(p)
    links = list(p.tag_links.all())
    w.note_tags(links)
    rec = {"id": str(p.uuid), "fen": p.fen, "title": p.title, "task": p.objective, "desc": p.description,
           "page": p.source_page, "ref": p.source_ref, "diff": p.difficulty_override, "diagram": p.diagram or None,
           "src": w.source(p.source), "tags": tag_keys(links), "moves": movetext(p)}
    rec["puzzles"] = [{"start": paths.get(z.start_node_id, ""), "active": z.active,
                       **{k: [paths[n] for n in z.marks.get(k, []) if n in paths] for k in ("ends", "also", "replies")}}
                      for z in p.puzzles.all() if z.start_node_id in paths]
    w.note_tags(NodeTag.objects.filter(node__position=p).select_related("tag__field", "tag__parent"))
    return rec | tree_extras(p, paths)


GAME_FIELDS = {"white": "white_name", "black": "black_name", "welo": "white_elo", "belo": "black_elo", "result": "result",
               "date": "date", "event": "event", "site": "site", "round": "round", "eco": "eco", "annotator": "annotator"}


def game_record(g, w: _Writer) -> dict:
    paths = paths_of(g)
    links = list(g.tag_links.all())
    w.note_tags(links)
    rec = {"id": str(g.uuid), **{k: getattr(g, f) for k, f in GAME_FIELDS.items()}, "headers": g.headers or None,
           "fen": g.start_fen if g.start_fen != chess.STARTING_FEN else None, "src": w.source(g.source), "ref": g.source_ref,
           "tags": tag_keys(links), "moves": movetext(g)}
    w.note_tags(NodeTag.objects.filter(node__game=g).select_related("tag__field", "tag__parent"))
    return rec | tree_extras(g, paths)


def build(positions, pack: Pack, author: str = "", student: str = "", include_received: bool = False, games=None) -> tuple[bytes, dict]:
    """The pack file of these positions (and games), and its manifest. Each build is a new version, logged."""
    positions = positions if include_received else exportable(positions)
    positions = positions.filter(deleted_at=None).select_related("source").prefetch_related("tag_links__tag__field", "tag_links__tag__parent", "puzzles")
    games = Game.objects.none() if games is None else (games if include_received else exportable(games))
    games = games.filter(deleted_at=None).select_related("source").prefetch_related("tag_links__tag__field", "tag_links__tag__parent")
    w = _Writer()
    lines, n_puzzles = [], 0
    for p in positions:
        rec = position_record(p, w)
        n_puzzles += len(rec["puzzles"])
        lines.append(w.line(rec))
    game_lines = [w.line(game_record(g, w)) for g in games]
    if not lines and not game_lines:
        raise PackError(gettext("no positions or games to put in a pack"))
    sources, extra_tags = w.sources, w.extra_tags
    pack.version += 1
    pack.save(update_fields=["version", "updated_at"])
    copy = uuid.uuid4().hex[:12] if student else ""
    manifest = {"format": FORMAT, "pack": str(pack.uuid), "version": pack.version, "title": pack.title, "author": author,
                "description": pack.description, "licence": pack.licence or gettext(DEFAULT_LICENCE), "created": timezone.now().isoformat(),
                "positions": len(lines), "puzzles": n_puzzles, "games": len(game_lines)}
    if student:
        manifest |= {"for": student, "copy": copy}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        z.writestr("positions.jsonl", "".join(line + "\n" for line in lines))
        if game_lines:
            z.writestr("games.jsonl", "".join(line + "\n" for line in game_lines))
        z.writestr("sources.json", json.dumps(sources, ensure_ascii=False, separators=(",", ":")))
        z.writestr("tags.json", json.dumps(list(extra_tags.values()), ensure_ascii=False, separators=(",", ":")))
    PackExport.objects.create(pack=pack, version=pack.version, student=student, copy=copy, positions=len(lines) + len(game_lines))
    return buf.getvalue(), manifest


# ── Reading ───────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass
class Contents:
    manifest: dict
    positions: list[dict]
    sources: list[dict]
    tags: list[dict]
    games: list[dict] = field(default_factory=list)


def read(data: bytes) -> Contents:
    if len(data) > MAX_BYTES:
        raise PackError(gettext("this file is too large for a pack"))
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = set(z.namelist())
            if not {"manifest.json", "positions.jsonl"} <= names:
                raise PackError(gettext("not a puzzle pack (no manifest)"))
            manifest = json.loads(z.read("manifest.json"))

            def jsonl(name):
                return [json.loads(line) for line in z.read(name).decode().splitlines() if line.strip()] if name in names else []

            positions, games = jsonl("positions.jsonl"), jsonl("games.jsonl")
            sources = json.loads(z.read("sources.json")) if "sources.json" in names else []
            tags = json.loads(z.read("tags.json")) if "tags.json" in names else []
    except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError, KeyError) as e:
        raise PackError(gettext("not a puzzle pack ({error})").format(error=e)) from None
    if manifest.get("format", 0) > FORMAT:
        raise PackError(gettext("this pack was made by a newer version of Spaced Positions: update the app"))
    if not manifest.get("pack"):
        raise PackError(gettext("not a puzzle pack (no pack id)"))
    return Contents(manifest, positions, sources, tags, games)


def _keys(rec: dict, name: str = "tags") -> set[str]:
    return {k.removeprefix("~") for k in rec.get(name, [])} | {k.removeprefix("~") for keys in rec.get("mtags", {}).values() for k in keys}


def scan(data: bytes) -> dict:
    """What an import would do: new positions and games, updates of an earlier version, duplicates here, unknown tags."""
    c = read(data)
    received = ReceivedPack.objects.filter(pack_id=c.manifest["pack"]).first()
    have = {str(u): pack for u, pack in Position.objects.filter(uuid__in=[p["id"] for p in c.positions]).values_list("uuid", "pack_id")}
    canon = {}
    for p in c.positions:
        if p["id"] not in have:
            canon[p["id"]] = chesslogic.check_fen(p["fen"], diagram=bool(p.get("diagram"))).get("canonical") or chesslogic.canonical_fen(p["fen"])
    duplicates = set(Position.alive.filter(canonical__in=set(canon.values())).values_list("canonical", flat=True))
    counts = {"new": 0, "update": 0, "duplicate": 0, "yours": 0}
    for p in c.positions:
        if p["id"] in have:
            counts["update" if received and have[p["id"]] == received.pk else "yours"] += 1
        elif canon[p["id"]] in duplicates:
            counts["duplicate"] += 1
        else:
            counts["new"] += 1
    have_games = {str(u): pack for u, pack in Game.objects.filter(uuid__in=[g["id"] for g in c.games]).values_list("uuid", "pack_id")}
    games = {"new": 0, "update": 0, "yours": 0}
    for g in c.games:
        games["new" if g["id"] not in have_games else "update" if received and have_games[g["id"]] == received.pk else "yours"] += 1
    known = set(Tag.objects.values_list("key", flat=True))
    unknown = sorted(set().union(*(_keys(r) for r in c.positions + c.games)) - known)
    m = c.manifest
    return {"title": m.get("title", ""), "author": m.get("author", ""), "description": m.get("description", ""),
            "licence": m.get("licence", ""), "for": m.get("for", ""), "version": m.get("version", 1),
            "positions": len(c.positions), "puzzles": sum(len(p.get("puzzles", [])) for p in c.positions), "games": len(c.games),
            "earlier": received.version if received else None, "counts": counts, "game_counts": games, "unknown_tags": unknown}


# ── Importing ─────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass
class Report:
    counts: dict = field(default_factory=lambda: {"new": 0, "updated": 0, "duplicate": 0, "yours": 0, "puzzles": 0, "tags": 0, "failed": 0,
                                                  "games": 0, "games_updated": 0})
    problems: list[str] = field(default_factory=list)
    source: Source | None = None


def run(data: bytes, ready: bool = True) -> Report:
    c = read(data)
    report = Report()
    with transaction.atomic():
        received = receive(c.manifest)
        report.source = received.source
        tags = ensure_tags(c.tags, report)
        books = Books(c.sources)
        for rec in c.positions:
            try:
                with transaction.atomic():
                    import_position(rec, received, books, tags, ready, report)
            except (ValueError, KeyError, tree.TreeError, chess.IllegalMoveError) as e:
                report.counts["failed"] += 1
                report.problems.append(f"{rec.get('title') or rec.get('id')}: {e}")
        for rec in c.games:
            try:
                with transaction.atomic():
                    import_game(rec, received, books, tags, report)
            except (ValueError, KeyError, tree.TreeError, chess.IllegalMoveError) as e:
                report.counts["failed"] += 1
                report.problems.append(f"{rec.get('white', '?')} – {rec.get('black', '?')}: {e}")
    return report


def receive(m: dict) -> ReceivedPack:
    """The pack, with its own source row (made once; a newer version updates its details)."""
    received = ReceivedPack.objects.filter(pack_id=m["pack"]).select_related("source").first()
    if received is None:
        source = Source.objects.create(kind=Source.Kind.PACK, title=m.get("title") or gettext("Puzzle pack"), origin=f"pack:{m['pack']}"[:40])
        received = ReceivedPack(source=source, pack_id=m["pack"])
    source = received.source
    source.title, source.authors, source.notes = (m.get("title") or source.title)[:300], (m.get("author") or "")[:300], m.get("description", "")
    source.save()
    received.version = max(received.version or 1, int(m.get("version", 1)))
    received.author, received.licence = (m.get("author") or "")[:120], (m.get("licence") or "")[:300]
    received.student, received.copy = (m.get("for") or "")[:120], (m.get("copy") or "")[:32]
    received.save()
    return received


class Books:
    """The pack's sources as sources here: the one with the same title (and authors), else a new one."""

    def __init__(self, sources: list[dict]):
        self.sources, self.made = sources, {}

    def get(self, index) -> Source | None:
        if not isinstance(index, int) or not 0 <= index < len(self.sources):
            return None
        if index not in self.made:
            d = self.sources[index]
            title = (d.get("title") or "").strip()[:300]
            if not title:
                return None
            found = Source.objects.exclude(kind=Source.Kind.PACK).filter(title__iexact=title)
            if d.get("authors"):
                found = found.filter(authors__iexact=d["authors"]) or found
            source = found.first()
            if source is None:
                kind = d.get("kind") if d.get("kind") in Source.Kind.values and d.get("kind") != Source.Kind.PACK else Source.Kind.BOOK
                source = Source.objects.create(title=title, short=(d.get("short") or "")[:80], authors=(d.get("authors") or "")[:300],
                                               year=d.get("year") if isinstance(d.get("year"), int) else None,
                                               publisher=(d.get("publisher") or "")[:200], url=(d.get("url") or "")[:200], kind=kind)
            self.made[index] = source
        return self.made[index]

    def citation(self, rec: dict) -> str:
        book = self.sources[rec["src"]] if isinstance(rec.get("src"), int) and 0 <= rec["src"] < len(self.sources) else {}
        name = book.get("short") or ", ".join(x for x in [book.get("authors"), book.get("title")] if x)
        return " · ".join(x for x in [name, gettext("p. {page}").format(page=rec["page"]) if rec.get("page") else "", rec.get("ref", "")] if x)[:300]


def ensure_tags(definitions: list[dict], report: Report) -> dict[str, Tag]:
    """Tags by key; the pack's own tags are made when they are missing (in their field, else custom)."""
    tags = {t.key: t for t in Tag.objects.all()}
    fields = {f.key: f for f in TagField.objects.all()}
    for d in definitions:
        if d.get("key") in tags or not d.get("key"):
            continue
        tag = Tag(key=d["key"][:100], name=(d.get("name") or d["key"])[:100], name_en=(d.get("name_en") or "")[:100],
                  aliases=[a for a in d.get("aliases") or [] if isinstance(a, str)],
                  field=fields.get(d.get("field")) or fields.get("custom") or next(iter(fields.values())), weight=1.0)
        tag.save()
        tags[tag.key] = tag
        report.counts["tags"] += 1
    for d in definitions:
        if d.get("parent") in tags and d.get("key") in tags and tags[d["key"]].parent_id is None:
            tags[d["key"]].parent = tags[d["parent"]]
            tags[d["key"]].save(update_fields=["parent"])
    return tags


def _tag_links(keys: list[str], tags: dict) -> list[tuple[Tag, str]]:
    """[(tag, origin)] of `key` / `~key` entries this database knows."""
    out = []
    for raw in keys:
        key = raw.removeprefix("~")
        if key in tags:
            out.append((tags[key], TagLinkOrigin.AUTO if raw.startswith("~") else TagLinkOrigin.MANUAL))
    return out


def fill(owner, fen: str, rec: dict, tags: dict) -> dict[str, int]:
    """The moves, then what movetext doesn't carry (marks, colours, squares, move tags). Returns {path: node id}."""
    from spaced_positions.analysis.models import Node

    root = tree.root(owner)
    if rec.get("moves"):
        game = chess.pgn.read_game(io.StringIO(f'[FEN "{fen}"]\n[SetUp "1"]\n\n{rec["moves"]} *\n'))
        if game is not None:
            pgn_io.fill_tree(root, game)  # existing moves are reused: an update adds what is new
    by_path = {path: node_id for node_id, path in paths_of(owner).items()}
    for name, attr in (("marks", "mark"), ("colors", "color")):
        for path, value in rec.get(name, {}).items():
            if path in by_path:
                Node.objects.filter(pk=by_path[path]).update(**{attr: value})
    for path, squares in rec.get("squares", {}).items():  # filled squares travel as circles in PGN: put them back
        node = Node.objects.filter(pk=by_path.get(path)).first()
        if node is not None and isinstance(squares, dict):
            node.shapes = [s for s in node.shapes or [] if s.get("dest") or s.get("orig") not in squares]
            node.squares = squares
            node.save(update_fields=["shapes", "squares"])
    for path, keys in rec.get("mtags", {}).items():
        if path in by_path:
            for tag, origin in _tag_links(keys, tags):
                NodeTag.objects.get_or_create(node_id=by_path[path], tag=tag, defaults={"origin": origin})
    return by_path


def import_position(rec: dict, received: ReceivedPack, books: Books, tags: dict, ready: bool, report: Report) -> None:
    from spaced_positions.analysis import puzzles as analysis_puzzles
    from spaced_positions.library.detect import refresh_difficulty
    from spaced_positions.training import puzzles

    position = Position.objects.filter(uuid=rec["id"]).first()
    if position is not None and position.pack_id != received.pk:
        report.counts["yours"] += 1  # the coach importing their own pack, or the same position from elsewhere
        return
    fields = {"title": (rec.get("title") or "")[:200], "objective": (rec.get("task") or "")[:120], "description": rec.get("desc", ""),
              "source": books.get(rec.get("src")), "source_page": (rec.get("page") or "")[:40], "source_ref": (rec.get("ref") or "")[:300],
              "source_text": books.citation(rec), "difficulty_override": rec.get("diff")}
    if position is None:
        check = chesslogic.check_fen(rec["fen"], diagram=bool(rec.get("diagram")))
        canonical = check.get("canonical") or chesslogic.canonical_fen(rec["fen"])
        if Position.alive.filter(canonical=canonical).exists():
            report.counts["duplicate"] += 1
            return
        position = Position.objects.create(uuid=rec["id"], fen=rec["fen"], canonical=canonical, pack=received,
                                           diagram=bool(rec.get("diagram")), origin=f"pack:{received.pk}", **fields)
        report.counts["new"] += 1
    else:
        for k, v in fields.items():
            setattr(position, k, v)
        position.save()
        report.counts["updated"] += 1
    by_path = fill(position, rec["fen"], rec, tags)
    for tag, origin in _tag_links(rec.get("tags", []), tags):
        PositionTag.objects.get_or_create(position=position, tag=tag, defaults={"origin": origin})
    for z in rec.get("puzzles", []):
        start = by_path.get(z.get("start", ""))
        if start is None:
            continue
        marks = {k: [by_path[p] for p in z.get(k, []) if p in by_path] for k in ("ends", "also", "replies")}
        puzzle = position.puzzles.filter(start_node_id=start).first()
        if puzzle is None:
            node = position.nodes.get(pk=start)
            puzzle = Puzzle.objects.create(position=position, start_node=node, start_fen=node.fen, marks=marks, solution={"moves": []},
                                           active=ready and z.get("active", True), origin=f"pack:{received.pk}")
            report.counts["puzzles"] += 1
        else:
            puzzle.marks = marks
            puzzle.save(update_fields=["marks"])
        analysis_puzzles.rebuild(puzzle)  # cards follow the lines: the student's cards and history stay
        puzzle.refresh_from_db()
        puzzles.validate(puzzle.start_fen, puzzle.solution)
    refresh_difficulty(position)
    position.save()  # the search text and the derived fields


def import_game(rec: dict, received: ReceivedPack, books: Books, tags: dict, report: Report) -> None:
    from .importer import Players, dedupe_of
    from .importer import import_game as make_game

    g = Game.objects.filter(uuid=rec["id"]).first()
    if g is not None and g.pack_id != received.pk:
        report.counts["yours"] += 1
        return
    headers = {"Event": rec.get("event", ""), "Site": rec.get("site", ""), "Date": rec.get("date", ""), "Round": rec.get("round", ""),
               "White": rec.get("white", ""), "Black": rec.get("black", ""), "Result": rec.get("result", "*"),
               "WhiteElo": str(rec.get("welo") or ""), "BlackElo": str(rec.get("belo") or ""), "ECO": rec.get("eco", ""),
               "Annotator": rec.get("annotator", ""), **(rec.get("headers") or {})}
    fen = rec.get("fen") or chess.STARTING_FEN
    pgn = "".join(f'[{k} "{str(v).replace(chr(34), chr(39))}"]\n' for k, v in headers.items() if v)
    if fen != chess.STARTING_FEN:
        pgn += f'[FEN "{fen}"]\n[SetUp "1"]\n'
    parsed = chess.pgn.read_game(io.StringIO(f"{pgn}\n{rec.get('moves', '')} {rec.get('result', '*')}\n"))
    if parsed is None:
        raise ValueError(gettext("no game"))
    if g is None:
        if Game.objects.filter(dedupe=dedupe_of(parsed), deleted_at=None).exists():
            report.counts["duplicate"] += 1
            return
        g = make_game(parsed, Players(), source=books.get(rec.get("src")))
        Game.objects.filter(pk=g.pk).update(uuid=rec["id"], pack=received, source_ref=(rec.get("ref") or "")[:300], origin=f"pack:{received.pk}")
        g.refresh_from_db()
        report.counts["games"] += 1
    else:
        g.source, g.source_ref = books.get(rec.get("src")), (rec.get("ref") or "")[:300]
        g.save()
        report.counts["games_updated"] += 1
    fill(g, fen, rec, tags)
    for tag, origin in _tag_links(rec.get("tags", []), tags):
        GameTag.objects.get_or_create(game=g, tag=tag, defaults={"origin": origin})
