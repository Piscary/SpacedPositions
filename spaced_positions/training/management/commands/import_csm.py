"""manage.py import_csm PATH: the training puzzles of a chess-study-manager database, as test data.

Reads a *copy* of the database (the original is never opened), rebuilds each active puzzle's solution tree from its
analysis with the old app's rules (puzzles.py there: main move, "also correct" moves, extra answers, ends, at most
8 solver moves), and creates Position, Puzzle and Card rows here. With --schedule (default) the cards keep their
spaced-repetition state, so Review has real due cards. Attempts and sessions are not imported: the full migration
is phase 7. Puzzles already imported (origin csm:<id>) are skipped.
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
from spaced_positions.training import puzzles
from spaced_positions.training.models import Card, Position, Puzzle

MAX_SOLVER_MOVES, HARD_CAP = 8, 40


class Node:
    __slots__ = ("id", "uci", "fen_after", "kids")

    def __init__(self, id, uci, fen_after):
        self.id, self.uci, self.fen_after, self.kids = id, uci, fen_after, []


def _when(value):
    if not value:
        return None
    dt = datetime.fromisoformat(str(value).replace(" ", "T"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class Command(BaseCommand):
    help = "Import the training puzzles of a chess-study-manager database (read from a copy)."

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
            f"imported {counts['puzzles']} puzzles ({counts['cards']} cards), skipped {counts['skipped']} already here, "
            f"{counts['failed']} could not be read"
        )

    def run(self, db, schedule, limit):
        rows = db.execute(
            "select p.id, p.solution, p.node_id, n.position_id from training_trainingpuzzle p "
            "join positions_variationnode n on n.id = p.node_id where p.active = 1 and n.position_id is not null order by p.id"
        ).fetchall()
        done = set(Puzzle.objects.filter(origin__startswith="csm:").values_list("origin", flat=True))
        counts = {"puzzles": 0, "cards": 0, "skipped": 0, "failed": 0}
        for row in rows:
            if limit and counts["puzzles"] >= limit:
                break
            origin = f"csm:{row['id']}"
            if origin in done:
                counts["skipped"] += 1
                continue
            try:
                with transaction.atomic():
                    counts["cards"] += self.import_puzzle(db, row, origin, schedule)
                counts["puzzles"] += 1
            except (ValueError, KeyError, IndexError) as e:
                counts["failed"] += 1
                self.stderr.write(f"puzzle {row['id']}: {e}")
        return counts

    def tree_nodes(self, db, position_id):
        nodes = {}
        for r in db.execute(
            "select id, parent_id, uci, fen_after from positions_variationnode where position_id = ? order by sort_order, id",
            (position_id,),
        ):
            nodes[r["id"]] = (Node(r["id"], r["uci"], r["fen_after"]), r["parent_id"])
        for node, parent in nodes.values():
            if parent in nodes:
                nodes[parent][0].kids.append(node)
        return {k: v[0] for k, v in nodes.items()}

    def solution(self, start, sol):
        ends, also, extra = set(sol.get("ends", [])), set(sol.get("also", [])), set(sol.get("replies", []))

        def end_below(node):
            stack = [node]
            while stack:
                cur = stack.pop()
                if cur.id in ends:
                    return True
                stack.extend(k for i, k in enumerate(cur.kids) if i == 0 or k.id in also or k.id in extra)
            return False

        def point(pos, count):
            options = []
            for mv in [pos.kids[0]] + [k for k in pos.kids[1:] if k.id in also]:
                limit = HARD_CAP if end_below(mv) else MAX_SOLVER_MOVES
                stop = mv.id in ends or not mv.kids or count + 1 >= limit
                replies = []
                if not stop:
                    for i, r in enumerate(mv.kids):
                        if (i == 0 or r.id in extra) and r.kids and r.id not in ends:
                            replies.append({"uci": r.uci, "next": point(r, count + 1)})
                options.append({"uci": mv.uci, "replies": replies})
            return {"moves": options}

        return point(start, 0)

    def old_line(self, start, sol, chosen_ids):
        """The UCI moves of an old card's line (its non-main answers by node id), as the old app walked it."""
        tree = self.solution(start, sol)
        nodes = {}

        def index(n):
            nodes[n.id] = n
            for k in n.kids:
                index(k)

        index(start)
        chosen = {nodes[i].uci for i in chosen_ids if i in nodes}
        out, p = [], tree
        while True:
            main = p["moves"][0]
            out.append(main["uci"])
            if not main["replies"]:
                return out
            reply = next((r for r in main["replies"] if r["uci"] in chosen), main["replies"][0])
            out.append(reply["uci"])
            p = reply["next"]

    def import_puzzle(self, db, row, origin, schedule):
        nodes = self.tree_nodes(db, row["position_id"])
        start = nodes[row["node_id"]]
        if not start.kids:
            raise ValueError("nothing to solve")
        pos = db.execute("select * from positions_position where id = ?", (row["position_id"],)).fetchone()
        start_fen = start.fen_after
        sol = json.loads(row["solution"] or "{}") if isinstance(row["solution"], str) else (row["solution"] or {})
        tree = self.solution(start, sol)
        puzzles.validate(start_fen, tree)
        check = chesslogic.check_fen(pos["fen"])
        position = Position.objects.create(
            fen=pos["fen"],
            canonical=check["canonical"] or chesslogic.canonical_fen(pos["fen"]),
            title=pos["title"] or f"Position {pos['id']}",
            source=self.source_text(db, pos),
            objective=self.objective(db, pos["id"]),
            difficulty=pos["difficulty"],
            tag_names=self.tag_names(db, pos["id"]),
            origin=f"csm-position:{pos['id']}",
        )
        puzzle = Puzzle.objects.create(position=position, start_fen=start_fen, solution=tree, origin=origin)
        cards = puzzles.sync_cards(puzzle)
        if schedule:
            by_key = {c.line_key: c for c in cards}
            for old in db.execute("select * from training_trainingcard where puzzle_id = ? and in_solution = 1", (row["id"],)):
                chosen = [int(x) for x in (old["line"] or "").split(",") if x.isdigit()]
                card = by_key.get(" ".join(self.old_line(start, sol, chosen)))
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

    def source_text(self, db, pos):
        parts = []
        if pos["book_id"]:
            book = db.execute("select title, authors from sources_book where id = ?", (pos["book_id"],)).fetchone()
            if book:
                parts.append(", ".join(x for x in (book["authors"], book["title"]) if x))
        if pos["website_id"]:
            site = db.execute("select name from sources_website where id = ?", (pos["website_id"],)).fetchone()
            if site:
                parts.append(site["name"])
        if pos["source_ref"]:
            parts.append(f"Nr. {pos['source_ref']}")
        if pos["source_page"]:
            parts.append(f"p. {pos['source_page']}")
        return " · ".join(parts)

    def objective(self, db, position_id):
        row = db.execute(
            "select t.name_en, t.name from positions_positiontag pt join positions_tag t on t.id = pt.tag_id "
            "join positions_tagfield f on f.id = t.field_id where pt.position_id = ? and f.key = 'goal' limit 1",
            (position_id,),
        ).fetchone()
        return (row["name_en"] or row["name"]) if row else ""

    def tag_names(self, db, position_id):
        rows = db.execute(
            "select t.name from positions_positiontag pt join positions_tag t on t.id = pt.tag_id "
            "join positions_tagfield f on f.id = t.field_id where pt.position_id = ? and f.key not in ('phase', 'level', 'custom', 'goal') "
            "order by f.\"order\", t.\"order\"",
            (position_id,),
        )
        return [r["name"] for r in rows][:8]
