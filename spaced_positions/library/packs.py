"""Puzzle packs (spec 09 §12): a coach's own material, as a file for students.

A pack (`.sppack`) is a zip: `manifest.json`, `positions.jsonl` (one compact JSON object a line: the position, its
analysis as PGN movetext, its tags, its puzzles with their moves as tree paths like `0.1.0`), `sources.json` (the
books the positions cite) and `tags.json` (tags a receiver may not have). Training history is never in a pack.

Importing makes the pack the source of its positions (so `src:` and training filters work on it) and keeps each
position's uuid, so a newer version of the same pack updates what came with the old one: new moves, comments and tags
are added, puzzles follow the new marks, and the student's cards and history stay."""

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

from spaced_positions import chesslogic
from spaced_positions.analysis import pgn as pgn_io
from spaced_positions.analysis import tree
from spaced_positions.training.models import Position, Puzzle

from .models import Pack, PackExport, PositionTag, ReceivedPack, Source, Tag, TagField
from .vocabulary import DATA as VOCABULARY

FORMAT = 1
SUFFIX = ".sppack"
DEFAULT_LICENCE = "For the personal use of the student it was made for. Please don't pass it on."
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


def movetext(position) -> str:
    """The analysis as PGN movetext (no headers): variations, comments, NAGs, drawings."""
    game = pgn_io._game_of(position, {})
    text = game.accept(chess.pgn.StringExporter(headers=False, columns=None)).strip()
    return "" if text in ("*", "") else text.removesuffix(" *")


# ── Export ────────────────────────────────────────────────────────────────────────────────────────────────────


def builtin_tags() -> set[str]:
    return {t["key"] for t in json.loads(VOCABULARY.read_text())["tags"]}


def exportable(positions):
    """Positions from a pack made for someone else stay out (spec 09 §12: packs don't spread by accident)."""
    return positions.exclude(source__pack__student__gt="")


def build(positions, pack: Pack, author: str = "", student: str = "", include_received: bool = False) -> tuple[bytes, dict]:
    """The pack file of these positions, and its manifest. Each build is a new version, logged."""
    positions = positions if include_received else exportable(positions)
    positions = positions.filter(deleted_at=None).select_related("source").prefetch_related("tag_links__tag__field", "puzzles")
    builtin = builtin_tags()
    sources, source_index, extra_tags, lines, n_puzzles = [], {}, {}, [], 0
    for p in positions:
        paths = paths_of(p)
        rec = {"id": str(p.uuid), "fen": p.fen, "title": p.title, "task": p.objective, "desc": p.description,
               "page": p.source_page, "ref": p.source_ref, "diff": p.difficulty_override, "diagram": p.diagram or None}
        if p.source_id:
            if p.source_id not in source_index:
                s = p.source
                source_index[p.source_id] = len(sources)
                sources.append({k: v for k, v in {"title": s.title, "short": s.short, "authors": s.authors, "year": s.year,
                                                   "publisher": s.publisher, "kind": s.kind}.items() if v})
            rec["src"] = source_index[p.source_id]
        tags = [link.tag for link in p.tag_links.all() if link.origin != "suggested"]
        rec["tags"] = [t.key for t in tags]
        for t in tags:
            if t.key not in builtin:
                extra_tags[t.key] = {"key": t.key, "name": t.name, "name_en": t.name_en, "field": t.field.key,
                                     "parent": t.parent.key if t.parent_id else None, "aliases": t.aliases}
        rec["moves"] = movetext(p)
        rec["puzzles"] = [{"start": paths.get(z.start_node_id, ""), "active": z.active,
                           **{k: [paths[n] for n in z.marks.get(k, []) if n in paths] for k in ("ends", "also", "replies")}}
                          for z in p.puzzles.all() if z.start_node_id in paths]
        n_puzzles += len(rec["puzzles"])
        lines.append(json.dumps({k: v for k, v in rec.items() if v not in (None, "", [], {})}, ensure_ascii=False, separators=(",", ":")))
    if not lines:
        raise PackError("no positions to put in a pack")
    pack.version += 1
    pack.save(update_fields=["version", "updated_at"])
    copy = uuid.uuid4().hex[:12] if student else ""
    manifest = {"format": FORMAT, "pack": str(pack.uuid), "version": pack.version, "title": pack.title, "author": author,
                "description": pack.description, "licence": pack.licence or DEFAULT_LICENCE, "created": timezone.now().isoformat(),
                "positions": len(lines), "puzzles": n_puzzles}
    if student:
        manifest |= {"for": student, "copy": copy}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        z.writestr("positions.jsonl", "\n".join(lines) + "\n")
        z.writestr("sources.json", json.dumps(sources, ensure_ascii=False, separators=(",", ":")))
        z.writestr("tags.json", json.dumps(list(extra_tags.values()), ensure_ascii=False, separators=(",", ":")))
    PackExport.objects.create(pack=pack, version=pack.version, student=student, copy=copy, positions=len(lines))
    return buf.getvalue(), manifest


# ── Reading ───────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass
class Contents:
    manifest: dict
    positions: list[dict]
    sources: list[dict]
    tags: list[dict]


def read(data: bytes) -> Contents:
    if len(data) > MAX_BYTES:
        raise PackError("this file is too large for a pack")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = set(z.namelist())
            if not {"manifest.json", "positions.jsonl"} <= names:
                raise PackError("not a puzzle pack (no manifest)")
            manifest = json.loads(z.read("manifest.json"))
            positions = [json.loads(line) for line in z.read("positions.jsonl").decode().splitlines() if line.strip()]
            sources = json.loads(z.read("sources.json")) if "sources.json" in names else []
            tags = json.loads(z.read("tags.json")) if "tags.json" in names else []
    except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError, KeyError) as e:
        raise PackError(f"not a puzzle pack ({e})") from None
    if manifest.get("format", 0) > FORMAT:
        raise PackError("this pack was made by a newer version of Spaced Positions: update the app")
    if not manifest.get("pack"):
        raise PackError("not a puzzle pack (no pack id)")
    return Contents(manifest, positions, sources, tags)


def scan(data: bytes) -> dict:
    """What an import would do: new positions, updates of an earlier version, duplicates here, unknown tags."""
    c = read(data)
    received = ReceivedPack.objects.filter(pack_id=c.manifest["pack"]).first()
    have = {str(u): src for u, src in Position.objects.filter(uuid__in=[p["id"] for p in c.positions]).values_list("uuid", "source_id")}
    canon = {}
    for p in c.positions:
        if p["id"] not in have:
            canon[p["id"]] = chesslogic.check_fen(p["fen"], diagram=bool(p.get("diagram"))).get("canonical") or chesslogic.canonical_fen(p["fen"])
    duplicates = set(Position.alive.filter(canonical__in=set(canon.values())).values_list("canonical", flat=True))
    counts = {"new": 0, "update": 0, "duplicate": 0, "yours": 0}
    for p in c.positions:
        if p["id"] in have:
            counts["update" if received and have[p["id"]] == received.source_id else "yours"] += 1
        elif canon[p["id"]] in duplicates:
            counts["duplicate"] += 1
        else:
            counts["new"] += 1
    known = set(Tag.objects.values_list("key", flat=True))
    unknown = sorted({k for p in c.positions for k in p.get("tags", [])} - known)
    m = c.manifest
    return {"title": m.get("title", ""), "author": m.get("author", ""), "description": m.get("description", ""),
            "licence": m.get("licence", ""), "for": m.get("for", ""), "version": m.get("version", 1),
            "positions": len(c.positions), "puzzles": sum(len(p.get("puzzles", [])) for p in c.positions),
            "earlier": received.version if received else None, "counts": counts, "unknown_tags": unknown}


# ── Importing ─────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass
class Report:
    counts: dict = field(default_factory=lambda: {"new": 0, "updated": 0, "duplicate": 0, "yours": 0, "puzzles": 0, "tags": 0, "failed": 0})
    problems: list[str] = field(default_factory=list)
    source: Source | None = None


def run(data: bytes, ready: bool = True) -> Report:
    c = read(data)
    report = Report()
    with transaction.atomic():
        source = receive(c.manifest)
        report.source = source
        tags = ensure_tags(c.tags, report)
        books = c.sources
        for rec in c.positions:
            try:
                with transaction.atomic():
                    import_position(rec, source, books, tags, ready, report)
            except (ValueError, KeyError, tree.TreeError, chess.IllegalMoveError) as e:
                report.counts["failed"] += 1
                report.problems.append(f"{rec.get('title') or rec.get('id')}: {e}")
    return report


def receive(m: dict) -> Source:
    """The pack as a source (made once; a newer version updates its details)."""
    received = ReceivedPack.objects.filter(pack_id=m["pack"]).select_related("source").first()
    if received is None:
        source = Source.objects.create(kind=Source.Kind.PACK, title=m.get("title") or "Puzzle pack", origin=f"pack:{m['pack']}"[:40])
        received = ReceivedPack(source=source, pack_id=m["pack"])
    source = received.source
    source.title, source.authors, source.notes = (m.get("title") or source.title)[:300], (m.get("author") or "")[:300], m.get("description", "")
    source.save()
    received.version = max(received.version or 1, int(m.get("version", 1)))
    received.author, received.licence = (m.get("author") or "")[:120], (m.get("licence") or "")[:300]
    received.student, received.copy = (m.get("for") or "")[:120], (m.get("copy") or "")[:32]
    received.save()
    return source


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


def _citation(rec: dict, books: list[dict]) -> str:
    book = books[rec["src"]] if isinstance(rec.get("src"), int) and 0 <= rec["src"] < len(books) else {}
    name = book.get("short") or ", ".join(x for x in [book.get("authors"), book.get("title")] if x)
    return " · ".join(x for x in [name, f"p. {rec['page']}" if rec.get("page") else "", rec.get("ref", "")] if x)[:300]


def import_position(rec: dict, source: Source, books: list[dict], tags: dict, ready: bool, report: Report) -> None:
    from spaced_positions.analysis import puzzles as analysis_puzzles
    from spaced_positions.library.detect import refresh_difficulty
    from spaced_positions.training import puzzles

    position = Position.objects.filter(uuid=rec["id"]).first()
    if position is not None and position.source_id != source.pk:
        report.counts["yours"] += 1  # the coach importing their own pack, or the same position from elsewhere
        return
    fields = {"title": (rec.get("title") or "")[:200], "objective": (rec.get("task") or "")[:120], "description": rec.get("desc", ""),
              "source_page": (rec.get("page") or "")[:40], "source_ref": (rec.get("ref") or "")[:300], "source_text": _citation(rec, books),
              "difficulty_override": rec.get("diff")}
    if position is None:
        check = chesslogic.check_fen(rec["fen"], diagram=bool(rec.get("diagram")))
        canonical = check.get("canonical") or chesslogic.canonical_fen(rec["fen"])
        if Position.alive.filter(canonical=canonical).exists():
            report.counts["duplicate"] += 1
            return
        position = Position.objects.create(uuid=rec["id"], fen=rec["fen"], canonical=canonical, source=source,
                                           diagram=bool(rec.get("diagram")), origin=f"pack:{source.pk}", **fields)
        report.counts["new"] += 1
    else:
        for k, v in fields.items():
            setattr(position, k, v)
        position.save()
        report.counts["updated"] += 1
    root = tree.root(position)
    if rec.get("moves"):
        game = chess.pgn.read_game(io.StringIO(f'[FEN "{rec["fen"]}"]\n[SetUp "1"]\n\n{rec["moves"]} *\n'))
        if game is not None:
            pgn_io.fill_tree(root, game)  # existing moves are reused: an update adds what is new
    for key in rec.get("tags", []):
        if key in tags:
            PositionTag.objects.get_or_create(position=position, tag=tags[key], defaults={"origin": PositionTag.Origin.MANUAL})
    by_path = {path: node_id for node_id, path in paths_of(position).items()}
    for z in rec.get("puzzles", []):
        start = by_path.get(z.get("start", ""))
        if start is None:
            continue
        marks = {k: [by_path[p] for p in z.get(k, []) if p in by_path] for k in ("ends", "also", "replies")}
        puzzle = position.puzzles.filter(start_node_id=start).first()
        if puzzle is None:
            node = position.nodes.get(pk=start)
            puzzle = Puzzle.objects.create(position=position, start_node=node, start_fen=node.fen, marks=marks, solution={"moves": []},
                                           active=ready and z.get("active", True), origin=f"pack:{source.pk}")
            report.counts["puzzles"] += 1
        else:
            puzzle.marks = marks
            puzzle.save(update_fields=["marks"])
        analysis_puzzles.rebuild(puzzle)  # cards follow the lines: the student's cards and history stay
        puzzle.refresh_from_db()
        puzzles.validate(puzzle.start_fen, puzzle.solution)
    refresh_difficulty(position)
