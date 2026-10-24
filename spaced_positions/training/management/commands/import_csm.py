"""manage.py import_csm PATH: the analysed puzzles of a chess-study-manager database, as test data.

Reads a *copy* of the database (the original is never opened). For every active puzzle it imports the position with
its whole analysis tree (comments, annotation symbols, drawings, marks), links the puzzle to its start node with its
marks ("end", "also correct", further answers) mapped to the new nodes, and rebuilds the solution with the same
walker the analysis uses (analysis/puzzles.py). With --schedule (default) the cards keep their spaced-repetition
state. Attempts and sessions are not imported: the full migration is phase 7. Puzzles already imported (origin
csm:<id>) are skipped.
"""

import json
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from spaced_positions import chesslogic
from spaced_positions.analysis import puzzles as analysis_puzzles
from spaced_positions.analysis import tree
from spaced_positions.analysis.models import Node
from spaced_positions.library.models import PositionTag, Source, Tag
from spaced_positions.training import puzzles
from spaced_positions.training.models import Card, Position, Puzzle

BRUSH = {"G": "green", "R": "red", "B": "blue", "Y": "yellow"}


def _when(value):
    if not value:
        return None
    dt = datetime.fromisoformat(str(value).replace(" ", "T"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _json(value, default):
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except ValueError:
        return default


def _shapes(old: dict) -> tuple[list, dict]:
    shapes = [{"orig": a["from"], "dest": a["to"], "brush": BRUSH.get(a.get("color"), "green")} for a in old.get("arrows", []) if a.get("from")]
    shapes += [{"orig": c["square"], "brush": BRUSH.get(c.get("color"), "green")} for c in old.get("circles", []) if c.get("square")]
    squares = {s["square"]: BRUSH.get(s.get("color"), "green") for s in old.get("squares", []) if s.get("square")}
    return shapes, squares


class Command(BaseCommand):
    help = "Import the analysed puzzles of a chess-study-manager database (read from a copy)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="chess-study-manager db.sqlite3")
        parser.add_argument("--no-schedule", action="store_true", help="start every card as new")
        parser.add_argument("--limit", type=int, default=0, help="import at most N puzzles")

    def handle(self, path, no_schedule, limit, **options):
        source = Path(path).expanduser()
        if not source.exists():
            raise CommandError(f"{source} doesn't exist")
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "csm.sqlite3"
            for suffix in ("", "-wal", "-shm"):  # a consistent snapshot, including changes still in the WAL
                if Path(f"{source}{suffix}").exists():
                    shutil.copy2(f"{source}{suffix}", f"{copy}{suffix}")
            db = sqlite3.connect(copy)
            db.row_factory = sqlite3.Row
            try:
                counts = self.run(db, schedule=not no_schedule, limit=limit)
            finally:
                db.close()
        self.stdout.write(
            f"imported {counts['puzzles']} puzzles ({counts['cards']} cards, {counts['nodes']} analysis moves), "
            f"skipped {counts['skipped']} already here, {counts['failed']} could not be read"
        )

    def run(self, db, schedule, limit):
        rows = db.execute(
            "select p.id, p.solution, p.node_id, n.position_id from training_trainingpuzzle p "
            "join positions_variationnode n on n.id = p.node_id where p.active = 1 and n.position_id is not null order by p.id"
        ).fetchall()
        done = set(Puzzle.objects.filter(origin__startswith="csm:").values_list("origin", flat=True))
        positions = {}  # old position id → (Position, {old node id: new Node})
        counts = {"puzzles": 0, "cards": 0, "nodes": 0, "skipped": 0, "failed": 0}
        for row in rows:
            if limit and counts["puzzles"] >= limit:
                break
            origin = f"csm:{row['id']}"
            if origin in done:
                counts["skipped"] += 1
                continue
            try:
                with transaction.atomic():
                    if row["position_id"] not in positions:
                        positions[row["position_id"]] = self.import_position(db, row["position_id"], counts)
                    counts["cards"] += self.import_puzzle(db, row, origin, positions[row["position_id"]], schedule)
                counts["puzzles"] += 1
            except (ValueError, KeyError, IndexError) as e:
                positions.pop(row["position_id"], None)
                counts["failed"] += 1
                self.stderr.write(f"puzzle {row['id']}: {e}")
        return counts

    def import_position(self, db, old_id, counts):
        origin = f"csm-position:{old_id}"
        position = Position.objects.filter(origin=origin).first()
        if position is None:
            pos = db.execute("select * from positions_position where id = ?", (old_id,)).fetchone()
            check = chesslogic.check_fen(pos["fen"])
            position = Position.objects.create(
                fen=pos["fen"],
                canonical=check["canonical"] or chesslogic.canonical_fen(pos["fen"]),
                title=pos["title"] or f"Position {pos['id']}",
                source=self.source(db, pos),
                source_page=(pos["source_page"] or "")[:40],
                source_ref=(f"Nr. {pos['source_ref']}" if pos["source_ref"] else "")[:300],
                objective=self.objective(db, pos["id"]),
                difficulty_override=pos["difficulty"],
                origin=origin,
            )
            self.tag(db, position, pos["id"])
        mapping = {}
        old_nodes = db.execute(
            "select * from positions_variationnode where position_id = ? order by ply, sort_order, id", (old_id,)
        ).fetchall()
        existing_root = position.nodes.filter(parent=None).first()
        for old in old_nodes:
            shapes, squares = _shapes(_json(old["shapes"], {}))
            fields = {
                "comment": old["comment"] or "",
                "nags": [int(n) for n in _json(old["nags"], []) if str(n).isdigit()],
                "mark": old["quality"] if old["quality"] in ("good", "dubious", "bad") else "",
                "color": old["color"] or "",
                "shapes": shapes,
                "squares": squares,
            }
            if old["parent_id"] is None:
                node = existing_root or Node(position=position, fen=position.fen)
            else:
                parent = mapping[old["parent_id"]]
                node = Node(position=position, parent=parent, order=old["sort_order"], uci=old["uci"], san=old["san"],
                            ply=old["ply"], fen=old["fen_after"])
                counts["nodes"] += 1
            for k, v in fields.items():
                setattr(node, k, v)
            node.save()
            mapping[old["id"]] = node
        return position, mapping

    def import_puzzle(self, db, row, origin, imported, schedule):
        position, mapping = imported
        start = mapping[row["node_id"]]
        sol = _json(row["solution"], {})
        marks = {key: [mapping[i].id for i in sol.get(key, []) if i in mapping] for key in ("ends", "also", "replies")}
        puzzle = Puzzle.objects.create(position=position, start_node=start, start_fen=start.fen, marks=marks,
                                       solution={"moves": []}, origin=origin)
        analysis_puzzles.rebuild(puzzle)
        puzzle.refresh_from_db()
        puzzles.validate(puzzle.start_fen, puzzle.solution)
        cards = list(puzzle.cards.filter(in_solution=True))
        if schedule:
            kids = tree.kids_map(tree.nodes(position))
            by_key = {c.line_key: c for c in cards}
            for old in db.execute("select * from training_trainingcard where puzzle_id = ? and in_solution = 1", (row["id"],)):
                chosen = {mapping[int(x)].id for x in (old["line"] or "").split(",") if x.isdigit() and int(x) in mapping}
                card = by_key.get(" ".join(self.line(start, kids, puzzle.solution, chosen)))
                if card is None:
                    continue
                for field in ("state", "interval_days", "ease", "step", "reps", "lapses", "success_streak", "attempts", "successes", "total_ms", "best_ms"):
                    setattr(card, field, old[field])
                card.due = _when(old["due"]) or timezone.now()
                card.last_seen = _when(old["last_seen"])
                card.last_result = None if old["last_result"] is None else bool(old["last_result"])
                card.introduced_at = card.last_seen if card.state != Card.State.NEW else None
                card.save()
        return len(cards)

    def line(self, start, kids, solution, chosen):
        """The UCI moves of an old card's line: main solver moves, the chosen answers (by node id) where offered."""
        out, point, node = [], solution, start
        while True:
            main = point["moves"][0]
            out.append(main["uci"])
            if not main["replies"]:
                return out
            mv = next(k for k in kids.get(node.id, []) if k.uci == main["uci"])
            answers = {k.uci: k for k in kids.get(mv.id, [])}
            reply = next((r for r in main["replies"] if answers.get(r["uci"]) and answers[r["uci"]].id in chosen), main["replies"][0])
            out.append(reply["uci"])
            node, point = answers[reply["uci"]], reply["next"]

    def source(self, db, pos):
        """The old book or website as a Source (matched by title, so a second import reuses it)."""
        if pos["book_id"]:
            book = db.execute("select * from sources_book where id = ?", (pos["book_id"],)).fetchone()
            if book:
                found = Source.objects.filter(kind=Source.Kind.BOOK, title=book["title"]).first()
                return found or Source.objects.create(
                    kind=Source.Kind.BOOK, title=book["title"], authors=book["authors"] or "", year=book["year"],
                    publisher=book["publisher"] or "", isbn=book["isbn"] or "", notes=book["notes"] or "",
                )
        if pos["website_id"]:
            site = db.execute("select * from sources_website where id = ?", (pos["website_id"],)).fetchone()
            if site:
                found = Source.objects.filter(kind=Source.Kind.WEBSITE, title=site["name"]).first()
                return found or Source.objects.create(kind=Source.Kind.WEBSITE, title=site["name"], url=site["base_url"] or "")
        return None

    def objective(self, db, position_id):
        row = db.execute(
            "select t.name_en, t.name from positions_positiontag pt join positions_tag t on t.id = pt.tag_id "
            "join positions_tagfield f on f.id = t.field_id where pt.position_id = ? and f.key = 'goal' limit 1",
            (position_id,),
        ).fetchone()
        return (row["name_en"] or row["name"]) if row else ""

    def tag(self, db, position, position_id):
        """The old tags by key (the vocabulary came from the old app, decision 18); unknown keys are skipped."""
        tags = {t.key: t for t in Tag.objects.all()}
        rows = db.execute(
            "select t.slug, pt.source from positions_positiontag pt join positions_tag t on t.id = pt.tag_id where pt.position_id = ?",
            (position_id,),
        )
        for row in rows:
            if row["slug"] in tags:
                origin = PositionTag.Origin.AUTO if row["source"] == "auto" else PositionTag.Origin.MANUAL
                PositionTag.objects.get_or_create(position=position, tag=tags[row["slug"]], defaults={"origin": origin})
