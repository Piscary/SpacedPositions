"""The migration from chess-study-manager (spec 10 · phase 7): everything the old app knows, added to this one.

Reads a snapshot *copy* of the old database (the original is only copied, never opened for writing) and adds, in
order: sources (books, websites), players, games with their trees, all positions with their trees, tags (manual and
detected, with their evidence; open suggestions; dismissed suggestions as dismissals), puzzles and cards, the
sessions with every attempt, and the old analysis activity for Stats. The old pipeline boards are left out: this
app's filters (has:analysis, has:solution …) tell what is analysed and solved.
Achievements are then found from the joined history (logged as seen: they are history).

Every object carries its origin (`csm-position:12`, `csm-attempt:5378` …), so the migration can run again: it adds
only what is new in the old app since. Nothing here is deleted or overwritten:
- a position already here keeps its analysis when it was changed in this app (its journal), else old moves that are
  missing are added; its text fields are filled only where empty;
- a tag the user removed here (a dismissal) is not brought back;
- a card trained in both apps takes the schedule of the app that saw it last; its counters (attempts, successes,
  times) are counted again from the joined attempt log.

`run(path)` backs up this app's database first (`<data folder>/backups/`) and returns a report; `dry_run=True` does
all of it in a transaction that is rolled back (and needs no backup)."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from django.db import transaction
from django.db.models import Count, Max, Min, Q, Sum
from django.utils import timezone

from spaced_positions import chesslogic

BRUSH = {"G": "green", "R": "red", "B": "blue", "Y": "yellow"}
CARD_SCHEDULE = ("state", "interval_days", "ease", "step", "reps", "lapses", "success_streak")
CARD_COUNTERS = ("attempts", "successes", "total_ms", "best_ms")  # counted again where there is an attempt log
ACTIVITY = {"analysis": "analyse", "annotation": "analyse", "drawing": "analyse", "stage": "collect"}  # the rest: other traces


class DryRun(Exception):
    pass


@dataclass
class Report:
    counts: Counter = field(default_factory=Counter)
    problems: list[str] = field(default_factory=list)
    dry_run: bool = False
    backup: str = ""

    def add(self, what: str, n: int = 1):
        self.counts[what] += n

    def problem(self, text: str):
        if len(self.problems) < 200:
            self.problems.append(text)

    def lines(self) -> list[str]:
        order = ["sources", "players", "games", "game moves", "positions", "positions filled in", "moves", "position tags",
                 "suggestions", "dismissals", "move tags", "puzzles", "cards", "cards rescheduled",
                 "sessions", "attempts", "activity", "achievements"]
        shown = [f"{self.counts[k]} {k}" for k in order if self.counts.get(k)]
        return shown + [f"{v} {k}" for k, v in self.counts.items() if k not in order and v]


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


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _shapes(old: dict) -> tuple[list, dict]:
    shapes = [{"orig": a["from"], "dest": a["to"], "brush": BRUSH.get(a.get("color"), "green")} for a in old.get("arrows", []) if a.get("from")]
    shapes += [{"orig": c["square"], "brush": BRUSH.get(c.get("color"), "green")} for c in old.get("circles", []) if c.get("square")]
    squares = {s["square"]: BRUSH.get(s.get("color"), "green") for s in old.get("squares", []) if s.get("square")}
    return shapes, squares


@contextmanager
def snapshot(path: Path):
    """A consistent copy of the old database (with what is still in its WAL), opened read-only."""
    path = Path(path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"{path} doesn't exist")
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "csm.sqlite3"
        for suffix in ("", "-wal", "-shm"):
            if Path(f"{path}{suffix}").exists():
                shutil.copy2(f"{path}{suffix}", f"{copy}{suffix}")
        db = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            db.execute("select count(*) from positions_position").fetchone()
        except sqlite3.DatabaseError as e:
            db.close()
            raise ValueError(f"{path} is not a chess-study-manager database ({e})") from None
        try:
            yield db
        finally:
            db.close()


def backup(label: str = "before-csm") -> Path:
    """A compressed copy of this app's database next to it, in backups/ (spaced_positions/backups.py)."""
    from django.db import connection

    from spaced_positions import backups

    return backups.make(Path(connection.settings_dict["NAME"]), label)


def run(path, dry_run: bool = False, schedule: bool = True, make_backup: bool = True) -> Report:
    report = Report(dry_run=dry_run)
    with snapshot(path) as db:
        if make_backup and not dry_run:
            report.backup = str(backup())
        try:
            with transaction.atomic():
                Migration(db, report, schedule=schedule).run()
                if dry_run:
                    raise DryRun
        except DryRun:
            pass
    return report


class Migration:
    def __init__(self, db, report: Report, schedule: bool = True):
        self.db, self.report, self.schedule = db, report, schedule
        self.sources: dict[str, object] = {}  # "book:3" → Source
        self.players: dict[int, object] = {}
        self.games: dict[int, object] = {}
        self.positions: dict[int, object] = {}
        self.nodes: dict[int, object] = {}  # old node id → Node
        self.cards: dict[int, object] = {}  # old card id → Card
        self.sessions: dict[int, object] = {}
        self.touched_cards: set[int] = set()

    def rows(self, sql, *args):
        return self.db.execute(sql, args).fetchall()

    def run(self):
        self.import_sources()
        self.import_players()
        self.import_games()
        self.import_positions()
        self.import_tags()
        self.import_puzzles()
        self.import_sessions()
        self.import_attempts()
        self.recount_cards()
        self.import_activity()
        self.refresh()

    # ── Sources and players ─────────────────────────────────────────────────────────────────────────────────────

    def import_sources(self):
        from spaced_positions.library.models import Source

        for kind, table, title_col in (("book", "sources_book", "title"), ("website", "sources_website", "name")):
            for row in self.rows(f"select * from {table}"):
                origin = f"csm-{kind}:{row['id']}"
                title = row[title_col]
                cited = f"{row['authors']}, {title}" if kind == "book" and row["authors"] else None  # phase 4 made "Author, Title"
                source = (Source.objects.filter(origin=origin).first()
                          or Source.objects.filter(kind=kind, title=title, origin="").first()
                          or (Source.objects.filter(kind=kind, title=cited, origin="").first() if cited else None))
                if source is not None and cited and source.title == cited:
                    source.title = title  # the title, with the authors in their own field
                if source is None:
                    source = Source(kind=kind, title=title, created_at=_when(row["created_at"]) or timezone.now())
                    self.report.add("sources")
                values = ({"authors": row["authors"] or "", "year": row["year"], "publisher": row["publisher"] or "", "isbn": row["isbn"] or "",
                           "notes": row["notes"] or ""} if kind == "book" else {"url": row["base_url"] or "", "notes": row["notes"] or ""})
                for name, value in values.items():
                    if value and not getattr(source, name):
                        setattr(source, name, value)
                source.origin = origin
                source.save()
                self.sources[f"{kind}:{row['id']}"] = source

    def source_of(self, row):
        if row["book_id"]:
            return self.sources.get(f"book:{row['book_id']}")
        if row["website_id"]:
            return self.sources.get(f"website:{row['website_id']}")
        return None

    def import_players(self):
        from spaced_positions.library.models import Player
        from spaced_positions.library.text import fold, slug

        here = {fold(p.name): p for p in Player.objects.filter(origin="")}
        for row in self.rows("select * from positions_player"):
            origin = f"csm-player:{row['id']}"
            player = Player.objects.filter(origin=origin).first() or here.get(fold(row["name"]))
            if player is None:
                key, base, n = slug(row["name"]) or "player", slug(row["name"]) or "player", 2
                while Player.objects.filter(key=key).exists():
                    key, n = f"{base}-{n}", n + 1
                player = Player(key=key, name=row["name"], created_at=_when(row["created_at"]) or timezone.now())
                self.report.add("players")
            aliases = [a for a in _json(row["aliases"], []) if isinstance(a, str)]
            player.aliases = list(dict.fromkeys([*player.aliases, *aliases]))
            for name, value in (("role", row["role"]), ("title", row["title"]), ("federation", row["federation"]),
                                ("fide_id", row["fide_id"]), ("born", row["born"]), ("notes", row["notes"])):
                if value and not getattr(player, name):
                    setattr(player, name, value)
            player.origin = origin
            player.save()
            self.players[row["id"]] = player

    # ── Trees ───────────────────────────────────────────────────────────────────────────────────────────────────

    def import_tree(self, owner, old_rows, add_missing: bool):
        """Map the old nodes onto the owner's tree (by move from the same parent); add the missing ones if allowed."""
        from spaced_positions.analysis import tree
        from spaced_positions.analysis.models import Node

        root = tree.root(owner)
        kids: dict[int, dict[str, Node]] = {}
        for n in tree.nodes(owner):
            if n.parent_id is not None:
                kids.setdefault(n.parent_id, {})[n.uci] = n
        added = 0
        for old in old_rows:
            if old["parent_id"] is None:
                node = root
                if old["comment"] and not root.comment:
                    root.comment = old["comment"]
                    root.save(update_fields=["comment"])
            else:
                parent = self.nodes.get(old["parent_id"])
                if parent is None:
                    continue
                node = kids.get(parent.id, {}).get(old["uci"])
                if node is None:
                    if not add_missing:
                        continue
                    shapes, squares = _shapes(_json(old["shapes"], {}))
                    node = Node.objects.create(
                        parent=parent, order=old["sort_order"], uci=old["uci"], san=old["san"], ply=old["ply"], fen=old["fen_after"],
                        comment=old["comment"] or "", nags=[int(n) for n in _json(old["nags"], []) if str(n).isdigit()],
                        mark=old["quality"] if old["quality"] in ("good", "dubious", "bad") else "", color=(old["color"] or "")[:7],
                        shapes=shapes, squares=squares, **tree.owner_of(owner=owner),
                    )
                    kids.setdefault(parent.id, {})[node.uci] = node
                    added += 1
            self.nodes[old["id"]] = node
        return added

    def old_nodes(self, column: str, owner_id: int):
        return self.rows(f"select * from positions_variationnode where {column} = ? order by ply, sort_order, id", owner_id)

    # ── Games ───────────────────────────────────────────────────────────────────────────────────────────────────

    def import_games(self):
        from spaced_positions.library.models import Game

        for row in self.rows("select * from positions_game order by id"):
            origin = f"csm-game:{row['id']}"
            game = Game.objects.filter(origin=origin).first()
            if game is None:
                year = _int(str(row["date"] or "")[:4])
                game = Game.objects.create(
                    white=self.players.get(row["white_player_id"]), black=self.players.get(row["black_player_id"]),
                    white_name=row["white"] or "", black_name=row["black"] or "", white_elo=_int(row["white_elo"]), black_elo=_int(row["black_elo"]),
                    result=row["result"] or "*", date=row["date"] or "", year=year, event=row["event"] or "", site=row["site"] or "",
                    round=row["round"] or "", eco=row["eco"] or "", annotator=row["annotator"] or "", headers=_json(row["extra_headers"], {}),
                    start_fen=row["start_fen"] or chesslogic.START_FEN, pgn=row["pgn_original"] or "", source=self.source_of(row),
                    source_ref=(row["source_ref"] or "")[:300], notes="\n\n".join(x for x in (row["notes"], row["source_notes"]) if x),
                    deleted_at=_when(row["deleted_at"]), created_at=_when(row["created_at"]) or timezone.now(), origin=origin,
                )
                self.report.add("games")
            self.games[row["id"]] = game
            self.report.add("game moves", self.import_tree(game, self.old_nodes("game_id", row["id"]), add_missing=not game.journal.exists()))

    # ── Positions ───────────────────────────────────────────────────────────────────────────────────────────────

    def import_positions(self):
        from spaced_positions.training.models import Position

        here = {p.origin: p for p in Position.objects.filter(origin__startswith="csm-position:")}  # one read, no index needed
        for row in self.rows("select * from positions_position order by id"):
            origin = f"csm-position:{row['id']}"
            position = here.get(origin)
            if position is None:
                check = chesslogic.check_fen(row["fen"], diagram=bool(row["diagram"]))
                position = Position.objects.create(
                    fen=row["fen"], canonical=check.get("canonical") or chesslogic.canonical_fen(row["fen"]),
                    title=(row["title"] or f"Position {row['id']}")[:200], description=row["description"] or "", notes=row["notes"] or "",
                    source=self.source_of(row), source_page=(row["source_page"] or "")[:40],
                    source_ref=(f"Nr. {row['source_ref']}" if row["source_ref"] else "")[:300], source_text=(row["source_notes"] or "")[:300],
                    objective=self.objective(row["id"]), difficulty_override=row["difficulty_override"], diagram=bool(row["diagram"]),
                    deleted_at=_when(row["deleted_at"]), created_at=_when(row["created_at"]) or timezone.now(), origin=origin,
                )
                self.report.add("positions")
            else:
                changed = False
                for name, value in (("description", row["description"]), ("notes", row["notes"]), ("source_text", (row["source_notes"] or "")[:300])):
                    if value and not getattr(position, name):
                        setattr(position, name, value)
                        changed = True
                if position.source is None and self.source_of(row) is not None:
                    position.source, changed = self.source_of(row), True
                created = _when(row["created_at"])
                if created and position.created_at != created:  # the phase 2 import dated it by the import
                    position.created_at, changed = created, True
                if changed:
                    position.save()
                    self.report.add("positions filled in")
            self.positions[row["id"]] = position
            self.report.add("moves", self.import_tree(position, self.old_nodes("position_id", row["id"]), add_missing=not position.journal.exists()))
            if row["game_id"] and position.game_id is None and row["game_id"] in self.games:
                self.link_game(position, self.games[row["game_id"]], row["game_ply"])

    def link_game(self, position, game, ply):
        from spaced_positions.analysis import tree

        kids = tree.kids_map(tree.nodes(game))
        node = tree.root(game)
        while kids.get(node.id) and node.ply < (ply or 0):
            node = kids[node.id][0]
        position.game, position.game_node = game, node if node.ply == ply else None
        position.save(update_fields=["game", "game_node", "updated_at"])

    def objective(self, position_id):
        row = self.db.execute(
            "select t.name_en, t.name from positions_positiontag pt join positions_tag t on t.id = pt.tag_id "
            "join positions_tagfield f on f.id = t.field_id where pt.position_id = ? and f.key = 'goal' limit 1",
            (position_id,),
        ).fetchone()
        return (row["name_en"] or row["name"]) if row else ""

    # ── Tags ────────────────────────────────────────────────────────────────────────────────────────────────────

    def import_tags(self):
        from spaced_positions.library.models import NodeTag, PositionTag, Tag, TagDismissal

        tags = {t.key: t for t in Tag.objects.all()}
        old_tags = {r["id"]: r["slug"] for r in self.rows("select id, slug from positions_tag")}
        dismissed_positions = set(TagDismissal.objects.filter(node=None).values_list("position_id", "tag_id"))
        dismissed_nodes = set(TagDismissal.objects.filter(position=None).values_list("node_id", "tag_id"))
        unknown = Counter()
        for row in self.rows("select * from positions_positiontag"):
            position, tag = self.positions.get(row["position_id"]), tags.get(old_tags.get(row["tag_id"]))
            if tag is None:
                unknown[old_tags.get(row["tag_id"])] += 1
                continue
            if position is None or (position.id, tag.id) in dismissed_positions:
                continue
            origin = PositionTag.Origin.AUTO if row["source"] == "auto" else PositionTag.Origin.MANUAL
            link, made = PositionTag.objects.get_or_create(
                position=position, tag=tag,
                defaults={"origin": origin, "detector": (row["detector"] or "")[:40], "evidence": (row["evidence"] or "")[:200]},
            )
            if made:
                self.report.add("position tags")
            elif link.origin == origin and not link.evidence and row["evidence"]:
                link.evidence, link.detector = row["evidence"][:200], (row["detector"] or "")[:40]
                link.save(update_fields=["evidence", "detector"])
        for row in self.rows("select * from positions_tagsuggestion"):
            position, tag = self.positions.get(row["position_id"]), tags.get(old_tags.get(row["tag_id"]))
            if position is None or tag is None or (position.id, tag.id) in dismissed_positions:
                continue
            if row["status"] == "dismissed":
                if not PositionTag.objects.filter(position=position, tag=tag).exists():
                    _, made = TagDismissal.objects.get_or_create(position=position, tag=tag)
                    self.report.add("dismissals", made)
            elif row["status"] == "open":
                _, made = PositionTag.objects.get_or_create(
                    position=position, tag=tag,
                    defaults={"origin": PositionTag.Origin.SUGGESTED, "detector": (row["detector"] or "")[:40], "evidence": (row["evidence"] or "")[:200]},
                )
                self.report.add("suggestions", made)
        for row in self.rows("select * from positions_nodetag"):
            node, tag = self.nodes.get(row["node_id"]), tags.get(old_tags.get(row["tag_id"]))
            if node is None or tag is None or (node.id, tag.id) in dismissed_nodes:
                continue
            _, made = NodeTag.objects.get_or_create(
                node=node, tag=tag,
                defaults={"origin": "auto" if row["source"] == "auto" else "manual", "detector": (row["detector"] or "")[:40],
                          "evidence": (row["evidence"] or "")[:200]},
            )
            self.report.add("move tags", made)
        for key, n in unknown.items():
            self.report.problem(f"{n} position tags with the unknown tag '{key}' left out")

    # ── Puzzles and cards ───────────────────────────────────────────────────────────────────────────────────────

    def import_puzzles(self):
        from spaced_positions.analysis import puzzles as analysis_puzzles
        from spaced_positions.training import puzzles
        from spaced_positions.training.models import Puzzle

        here = {z.origin: z for z in Puzzle.objects.filter(origin__startswith="csm:")}
        for row in self.rows("select * from training_trainingpuzzle order by id"):
            origin = f"csm:{row['id']}"
            start = self.nodes.get(row["node_id"])
            if start is None or start.position_id is None:
                self.report.problem(f"puzzle {row['id']}: its position or move wasn't imported")
                continue
            puzzle = here.get(origin)
            if puzzle is None:
                sol = _json(row["solution"], {})
                marks = {key: [self.nodes[i].id for i in sol.get(key, []) if i in self.nodes] for key in ("ends", "also", "replies")}
                try:
                    with transaction.atomic():
                        puzzle = Puzzle.objects.create(position_id=start.position_id, start_node=start, start_fen=start.fen, marks=marks,
                                                       solution={"moves": []}, active=bool(row["active"]), origin=origin,
                                                       created_at=_when(row["created_at"]) or timezone.now())
                        analysis_puzzles.rebuild(puzzle)
                        puzzle.refresh_from_db()
                        puzzles.validate(puzzle.start_fen, puzzle.solution)
                except (ValueError, KeyError, IndexError) as e:
                    self.report.problem(f"puzzle {row['id']}: {e}")
                    continue
                self.report.add("puzzles")
                self.report.add("cards", puzzle.cards.filter(in_solution=True).count())
            self.map_cards(row, puzzle, start)

    def map_cards(self, row, puzzle, start):
        from spaced_positions.analysis import tree

        kids = tree.kids_map(tree.nodes(puzzle.position))
        by_key = {c.line_key: c for c in puzzle.cards.all()}
        for old in self.rows("select * from training_trainingcard where puzzle_id = ?", row["id"]):
            chosen = {self.nodes[int(x)].id for x in (old["line"] or "").split(",") if x.isdigit() and int(x) in self.nodes}
            try:
                card = by_key.get(" ".join(self.line(start, kids, puzzle.solution, chosen)))
            except (StopIteration, KeyError, IndexError):
                card = None
            if card is None:
                if old["attempts"]:
                    self.report.problem(f"card {old['id']} (puzzle {row['id']}): no line here matches it; its {old['attempts']} attempts are left out")
                continue
            self.cards[old["id"]] = card
            old_seen = _when(old["last_seen"])
            if self.schedule and old_seen and (card.last_seen is None or old_seen > card.last_seen):
                for name in CARD_SCHEDULE + CARD_COUNTERS:  # the old app saw it last: its schedule (counters: see recount_cards)
                    setattr(card, name, old[name])
                card.due, card.last_seen = _when(old["due"]) or timezone.now(), old_seen
                card.last_result = None if old["last_result"] is None else bool(old["last_result"])
                if card.introduced_at is None and card.state != "new":
                    card.introduced_at = old_seen  # counts as introduced (the daily limit of new cards)
                card.save()
                self.report.add("cards rescheduled")
            self.touched_cards.add(card.id)

    @staticmethod
    def line(start, kids, solution, chosen):
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

    # ── Sessions and attempts ───────────────────────────────────────────────────────────────────────────────────

    def import_sessions(self):
        from spaced_positions.training.models import Session

        have = {s.origin: s for s in Session.objects.filter(origin__startswith="csm-session:")}
        for row in self.rows("select * from training_trainingsession order by id"):
            origin = f"csm-session:{row['id']}"
            if origin in have:
                self.sessions[row["id"]] = have[origin]
                continue
            old = _json(row["options"], {})
            options = {"look": old.get("visual", "normal"), "first_move": bool(old.get("first_move")), "imported": "chess-study-manager"}
            if row["mode"] == "storm":
                options["minutes"] = row["minutes"] or 3
            if row["mode"] == "streak":
                options["lives"] = row["lives"] or 0
            if row["mode"] == "custom":
                options["custom"] = old
            self.sessions[row["id"]] = Session.objects.create(
                mode="review" if row["mode"] == "custom" else row["mode"], options=options,
                started_at=_when(row["started_at"]) or timezone.now(), ended_at=_when(row["ended_at"]),
                solved=row["solved"] or 0, failed=row["failed"] or 0, best_combo=row["best_combo"] or 0, streak=row["streak"] or 0,
                duration_s=row["duration_s"], origin=origin,
            )
            self.report.add("sessions")

    def import_attempts(self):
        from spaced_positions.training.models import Attempt

        have = set(Attempt.objects.filter(origin__startswith="csm-attempt:").values_list("origin", flat=True))
        new, left_out = [], 0
        for row in self.rows("select * from training_trainingattempt order by id"):
            origin = f"csm-attempt:{row['id']}"
            if origin in have:
                continue
            card = self.cards.get(row["card_id"])
            if card is None:
                left_out += 1
                continue
            new.append(Attempt(
                card=card, session=self.sessions.get(row["session_id"]), at=_when(row["at"]), success=bool(row["success"]), ms=row["ms"] or 0,
                wrong_move=row["wrong_move"] or "", mode="review" if row["mode"] == "custom" else (row["mode"] or ""),
                look=row["visual"] or "normal", first_move_only=bool(row["first_move_only"]), counted=bool(row["counted"]),
                state_before=row["state_before"] or "", interval_before=row["interval_before"], interval_after=row["interval_after"] or 0,
                due_before=_when(row["due_before"]), solved_as=row["solved_as"] or "", mirrored=bool(row["mirrored"]),
                flipped=bool(row["flipped"]), origin=origin,
            ))
            self.touched_cards.add(card.id)
        Attempt.objects.bulk_create(new, batch_size=500)
        self.report.add("attempts", len(new))
        if left_out:
            self.report.problem(f"{left_out} attempts on cards that aren't here left out")

    def recount_cards(self):
        """Counters of every card with history, from the joined attempt log (both apps)."""
        from spaced_positions.training.models import Attempt, Card

        stats = Attempt.objects.filter(card_id__in=self.touched_cards).values("card_id").annotate(
            n=Count("id"), ok=Count("id", filter=Q(success=True)), total=Sum("ms"), first=Min("at"), last=Max("at"),
            best=Min("ms", filter=Q(success=True)),
        )
        for s in stats:
            card = Card.objects.get(pk=s["card_id"])
            latest = Attempt.objects.filter(card=card).order_by("-at").first()
            card.attempts, card.successes, card.total_ms, card.best_ms = s["n"], s["ok"], s["total"] or 0, s["best"]
            card.introduced_at = s["first"]
            card.last_seen, card.last_result = latest.at, latest.success
            card.save(update_fields=["attempts", "successes", "total_ms", "best_ms", "introduced_at", "last_seen", "last_result"])

    # ── Activity, achievements, difficulty ──────────────────────────────────────────────────────────────────────

    def import_activity(self):
        from spaced_positions.stats.models import ActivityLog

        have = set(ActivityLog.objects.filter(origin__startswith="csm-activity:").values_list("origin", flat=True))
        new = [ActivityLog(kind=ACTIVITY[r["kind"]], points=r["points"] or 1, at=_when(r["created_at"]), label=(r["label"] or "")[:200],
                           origin=f"csm-activity:{r['id']}")
               for r in self.rows("select * from core_activityevent order by id")
               if r["kind"] in ACTIVITY and f"csm-activity:{r['id']}" not in have]
        ActivityLog.objects.bulk_create(new, batch_size=500)
        self.report.add("activity", len(new))

    def refresh(self):
        from spaced_positions.library.detect import refresh_difficulty
        from spaced_positions.stats import metrics
        from spaced_positions.stats.models import Achievement

        for position in self.positions.values():
            refresh_difficulty(position)
        before = set(Achievement.objects.values_list("id", flat=True))
        metrics.sync_achievements()
        found = Achievement.objects.exclude(id__in=before)
        self.report.add("achievements", found.count())
        found.update(seen=True)  # history, not news
