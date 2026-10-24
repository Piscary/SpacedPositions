"""The query language of the Library (spec 11 §3).

    motif:gabel,spiess diff:>=3 -is:diagram "back rank" (src:polgar or src:nunn) sort:-difficulty

`parse` turns the string into a tree of terms with their places in the string (for the QueryBar's chips and
underlines) and never fails: what it can't read becomes a problem. `compile` turns the tree into a Django filter for
one collection; terms it can't use become problems too, and are left out, so a half-typed query still shows results.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.db.models import Exists, F, Max, OuterRef, Q, Sum
from django.utils import timezone

from .text import fold

COLLECTIONS = ("positions", "games", "puzzles", "players", "sources", "tags")
NUMBER = re.compile(r"^(?P<op>>=|<=|>|<|=)?(?P<a>-?\d+(?:\.\d+)?)(?:\.\.(?P<b>-?\d+(?:\.\d+)?))?(?P<pct>%)?$")
RELATIVE = re.compile(r"^(?P<n>\d+)(?P<unit>[dwmy])$")
DATE_FORMS = ("%Y-%m-%d", "%Y-%m", "%Y")


# ── Parsing ───────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass
class Term:
    start: int
    end: int
    neg: bool = False
    key: str = ""  # "" = free text, "#" = a tag
    op: str = ""
    values: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.values[0] if self.values else ""


@dataclass
class Group:
    """Alternatives (OR) of conjunctions (AND)."""

    start: int
    end: int
    alternatives: list[list] = field(default_factory=list)
    neg: bool = False


@dataclass
class Problem:
    start: int
    end: int
    message: str


@dataclass
class Parsed:
    text: str
    root: Group
    problems: list[Problem] = field(default_factory=list)

    def terms(self):
        """Every term, in order (for the QueryBar)."""
        def walk(group):
            for conj in group.alternatives:
                for item in conj:
                    if isinstance(item, Group):
                        yield from walk(item)
                    else:
                        yield item
        return list(walk(self.root))

    def sort(self) -> list[Term]:
        return [t for t in self.terms() if t.key == "sort"]


def _tokens(text: str):
    """(kind, value, start, end): kinds are word, open, close."""
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c in "()":
            yield ("open" if c == "(" else "close", c, i, i + 1)
            i += 1
            continue
        if c == "-" and i + 1 < n and text[i + 1] == "(":
            yield ("not", "-", i, i + 1)
            i += 1
            continue
        start, buf, quoted = i, [], False
        while i < n:
            c = text[i]
            if c == '"':
                quoted = not quoted
                buf.append(c)
            elif not quoted and (c.isspace() or c in "()"):
                break
            else:
                buf.append(c)
            i += 1
        yield ("word", "".join(buf), start, i)


def _term(word: str, start: int, end: int, problems: list[Problem]) -> Term:
    neg = word.startswith("-") and len(word) > 1
    body = word[1:] if neg else word
    if body.startswith("#") and len(body) > 1:
        return Term(start, end, neg, "#", "", [_unquote(body[1:])])
    m = re.match(r"^([a-z]+):(.*)$", body, re.I)
    if not m:
        return Term(start, end, neg, "", "", [_unquote(body)])
    key, rest = m.group(1).lower(), m.group(2)
    op = ""
    for candidate in (">=", "<=", ">", "<", "="):
        if rest.startswith(candidate):
            op, rest = candidate, rest[len(candidate):]
            break
    values = [_unquote(v) for v in _split_values(rest)]
    values = [v for v in values if v != ""]
    if not values:
        problems.append(Problem(start, end, f"{key}: needs a value"))
    return Term(start, end, neg, key, op, values)


def _split_values(rest: str) -> list[str]:
    out, buf, quoted = [], [], False
    for c in rest:
        if c == '"':
            quoted = not quoted
            buf.append(c)
        elif c == "," and not quoted:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(c)
    out.append("".join(buf))
    return out


def _unquote(v: str) -> str:
    v = v.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] == '"' else v.replace('"', "")


def parse(text: str) -> Parsed:
    problems: list[Problem] = []
    tokens = list(_tokens(text or ""))
    pos = 0

    def group(start, neg=False, depth=0):
        nonlocal pos
        g = Group(start, start, [[]], neg)
        while pos < len(tokens):
            kind, value, s, e = tokens[pos]
            if kind == "close":
                if depth == 0:
                    problems.append(Problem(s, e, "no ( for this )"))
                    pos += 1
                    continue
                pos += 1
                g.end = e
                return g
            pos += 1
            if kind == "word" and value.lower() == "or":
                g.alternatives.append([])
            elif kind == "open" or kind == "not":
                negate = kind == "not"
                if negate:
                    if pos < len(tokens) and tokens[pos][0] == "open":
                        pos += 1
                    else:
                        continue
                g.alternatives[-1].append(group(s, negate, depth + 1))
            else:
                g.alternatives[-1].append(_term(value, s, e, problems))
            g.end = e
        if depth:
            problems.append(Problem(start, start + 1, "this ( isn't closed"))
        return g

    root = group(0)
    root.alternatives = [conj for conj in root.alternatives if conj] or [[]]
    return Parsed(text or "", root, problems)


# ── Values ────────────────────────────────────────────────────────────────────────────────────────────────────


def _number_q(name: str, op: str, value: str, scale: float = 1) -> Q | None:
    m = NUMBER.match(value if not op else op + value)
    if not m:
        return None
    a = float(m.group("a")) * scale
    if m.group("b") is not None:
        return Q(**{f"{name}__gte": a, f"{name}__lte": float(m.group("b")) * scale})
    lookup = {">": "gt", ">=": "gte", "<": "lt", "<=": "lte", "=": "exact", None: "exact"}[m.group("op")]
    return Q(**{f"{name}__{lookup}": a})


def _when(value: str, now: datetime) -> tuple[datetime, bool] | None:
    """A date value: (moment, relative). '7d' is 7 days ago; '2026-10' the start of October."""
    m = RELATIVE.match(value)
    if m:
        days = int(m.group("n")) * {"d": 1, "w": 7, "m": 30, "y": 365}[m.group("unit")]
        return now - timedelta(days=days), True
    if value == "today":
        return timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0), True
    for form in DATE_FORMS:
        try:
            d = datetime.strptime(value, form)
        except ValueError:
            continue
        return timezone.make_aware(d) if timezone.is_naive(d) else d, False
    return None


def _date_q(name: str, op: str, value: str, now: datetime) -> Q | None:
    found = _when(value, now)
    if found is None:
        return None
    moment, relative = found
    if relative and op in ("<", "<=", ""):  # created:<7d = less than 7 days ago = after that moment
        return Q(**{f"{name}__gte": moment})
    if relative:  # created:>30d = longer ago
        return Q(**{f"{name}__lt": moment})
    if op in (">", ">="):
        return Q(**{f"{name}__gte": moment})
    if op in ("<", "<="):
        return Q(**{f"{name}__lt": moment})
    nxt = moment + timedelta(days=1 if len(value) == 10 else 31 if len(value) == 7 else 366)
    return Q(**{f"{name}__gte": moment, f"{name}__lt": nxt})


# ── Compiling ─────────────────────────────────────────────────────────────────────────────────────────────────


class Compiler:
    """Turns a parsed query into a queryset for one collection."""

    def __init__(self, collection: str, now: datetime | None = None, depth: int = 0):
        from .models import Tag, TagField

        self.collection = collection if collection in COLLECTIONS else "positions"
        self.now = now or timezone.now()
        self.depth = depth
        self.problems: list[Problem] = []
        self.fields = {f.key: f for f in TagField.objects.all()}
        self._tags = None
        self.Tag = Tag

    # Tags ───────────────────────────────────────────────────────────────────────────────────────────────────

    def tags(self):
        if self._tags is None:
            self._tags = list(self.Tag.objects.select_related("field"))
        return self._tags

    def tag_ids(self, value: str, field_key: str | None, exact: bool) -> set[int]:
        """Tags a value names (key, name, English name or alias; else a part of one), with descendants unless exact."""
        v = fold(value)
        pool = [t for t in self.tags() if field_key is None or t.field.key == field_key]
        found = [t for t in pool if v in t.search.split(" | ")]
        if not found:
            found = [t for t in pool if v and v in t.search]
        ids = {t.id for t in found}
        if not exact:
            children = {}
            for t in self.tags():
                children.setdefault(t.parent_id, []).append(t.id)
            stack = list(ids)
            while stack:
                for kid in children.get(stack.pop(), []):
                    if kid not in ids:
                        ids.add(kid)
                        stack.append(kid)
        return ids

    def tag_q(self, term: Term, field_key: str | None) -> Q | None:
        from .models import GameTag, PositionTag

        ids = set()
        for value in term.values:
            found = self.tag_ids(value, field_key, term.op == "=")
            if not found:
                self.problem(term, f"no tag '{value}'" + (f" in {field_key}" if field_key else ""))
            ids |= found
        if not ids:
            return None
        if self.collection == "games":
            return Q(Exists(GameTag.objects.filter(game=OuterRef("pk"), tag__in=ids).exclude(origin="suggested")))
        ref = OuterRef("pk") if self.collection == "positions" else OuterRef("position_id")
        return Q(Exists(PositionTag.objects.filter(position=ref, tag__in=ids).exclude(origin="suggested")))

    # Helpers ────────────────────────────────────────────────────────────────────────────────────────────────

    def problem(self, term, message):
        self.problems.append(Problem(term.start, term.end, message))

    def any_of(self, term: Term, make) -> Q | None:
        out = None
        for value in term.values:
            q = make(value)
            if q is None:
                self.problem(term, f"{term.key}: can't read '{value}'")
                continue
            out = q if out is None else out | q
        return out

    def p(self, path: str) -> str:
        """A position field from the collection's rows (positions: itself; puzzles: their position)."""
        return path if self.collection == "positions" else f"position__{path}"

    # Terms ──────────────────────────────────────────────────────────────────────────────────────────────────

    def term(self, t: Term) -> Q | None:
        if t.key == "sort":
            return None
        if t.key == "":
            return self.text(t.text)
        handler = getattr(self, f"k_{self.collection}", None)
        q = handler(t) if handler else None
        if q is NotImplemented:
            self.problem(t, f"{t.key}: not a key for {self.collection}")
            return None
        return q

    def k_positions(self, t: Term):
        return self.position_term(t)

    def k_puzzles(self, t: Term):
        from spaced_positions.training.models import Card

        now = self.now
        cards = Card.objects.filter(puzzle=OuterRef("pk"), in_solution=True)
        if t.key == "due":
            def due(v):
                if v in ("today", "now"):
                    end = timezone.localtime(now).replace(hour=23, minute=59, second=59)
                    return Q(Exists(cards.exclude(state="new").filter(due__lte=end)))
                found = _when(v, now)
                return Q(Exists(cards.exclude(state="new").filter(due__lte=now + (now - found[0])))) if found and found[1] else None
            return self.any_of(t, due)
        if t.key == "state":
            states = {"new", "learning", "review", "relearning", "young", "mature"}
            def state(v):
                if v not in states:
                    return None
                if v == "young":
                    return Q(Exists(cards.filter(state="review", interval_days__lt=21)))
                if v == "mature":
                    return Q(Exists(cards.filter(state="review", interval_days__gte=21)))
                return Q(Exists(cards.filter(state=v)))
            return self.any_of(t, state)
        if t.key in ("lapses", "attempts"):
            name = {"lapses": "lapse_sum", "attempts": "attempt_sum"}[t.key]
            return self.any_of(t, lambda v: _number_q(name, t.op, v))
        if t.key == "success":
            return self.any_of(t, lambda v: _number_q("success_rate", t.op, v.rstrip("%"), 1))
        if t.key == "last":
            return self.any_of(t, lambda v: _date_q("last_seen_at", t.op, v, now))
        return self.position_term(t, puzzle=True)

    def position_term(self, t: Term, puzzle: bool = False):
        from spaced_positions.analysis.models import Node
        from spaced_positions.training.models import Puzzle

        p, key = self.p, t.key
        if key in self.fields:
            return self.tag_q(t, key)
        if key in ("tag", "#"):
            return self.tag_q(t, None)
        if key == "diff":
            return self.any_of(t, lambda v: _number_q(p("difficulty"), t.op, v))
        if key == "side":
            sides = {"w": "w", "white": "w", "weiss": "w", "b": "b", "black": "b", "schwarz": "b"}
            return self.any_of(t, lambda v: Q(**{p("side"): sides[fold(v)]}) if fold(v) in sides else None)
        if key == "src":
            return self.any_of(t, lambda v: Q(**{f"{p('source__search')}__contains": fold(v)}) | Q(**{f"{p('source_text')}__icontains": v}))
        if key == "page":
            return self.any_of(t, lambda v: Q(**{f"{p('source_page')}__iexact": v}))
        if key == "ref":
            return self.any_of(t, lambda v: Q(**{f"{p('source_ref')}__icontains": v}))
        if key == "material":
            return self.any_of(t, lambda v: Q(**{p("material"): _material(v)}) if _material(v) else None)
        if key == "pieces":
            return self.any_of(t, lambda v: _number_q(p("pieces"), t.op, v))
        if key == "fen":
            return self.any_of(t, lambda v: Q(**{f"{p('fen')}__startswith": v.split()[0]}) if "/" in v else None)
        if key in ("created", "updated"):
            name = "created_at" if puzzle and key == "created" else p(f"{key}_at")
            return self.any_of(t, lambda v: _date_q(name, t.op, v, self.now))
        if key == "game":
            return self.any_of(t, lambda v: Q(**{p("game_id"): int(v.lstrip("gG"))}) if v.lstrip("gG").isdigit() else None)
        pos_ref = OuterRef("pk") if not puzzle else OuterRef("position_id")
        checks = {
            "solution": Q(Exists(Puzzle.objects.filter(position=pos_ref, active=True))),
            "analysis": Q(Exists(Node.objects.filter(position=pos_ref, parent__isnull=False))),
            "puzzle": Q(Exists(Puzzle.objects.filter(position=pos_ref))),
            "comment": Q(Exists(Node.objects.filter(position=pos_ref).exclude(comment=""))),
            "source": Q(**{f"{p('source')}__isnull": False}) | ~Q(**{p("source_text"): ""}),
            "tags": Q(Exists(self._position_tags(pos_ref))),
            "game": Q(**{f"{p('game')}__isnull": False}),
        }
        if key in ("has", "no"):
            def has(v):
                q = checks.get(v)
                return q if key == "has" or q is None else ~q
            return self.any_of(t, has)
        if key == "is":
            states = {
                "diagram": Q(**{p("diagram"): True}),
                "flagged": Q(flagged=True) if puzzle else Q(Exists(Puzzle.objects.filter(position=pos_ref, flagged=True))),
                "draft": Q(active=False) if puzzle else Q(Exists(Puzzle.objects.filter(position=pos_ref, active=False))),
                "trash": Q(**{f"{p('deleted_at')}__isnull": False}),
            }
            return self.any_of(t, lambda v: states.get(v))
        if key == "in":
            return self.any_of(t, self.saved)
        return NotImplemented

    def _position_tags(self, ref):
        from .models import PositionTag

        return PositionTag.objects.filter(position=ref).exclude(origin="suggested")

    def k_games(self, t: Term):
        key = t.key
        if key in self.fields or key in ("tag", "#"):
            return self.tag_q(t, key if key in self.fields else None)
        def player(side):
            def make(v):
                if v.startswith("@"):
                    return Q(**{f"{side}__key": v[1:]})
                return Q(**{f"{side}_name__icontains": v}) | Q(**{f"{side}__search__contains": fold(v)})
            return make
        if key in ("white", "black"):
            return self.any_of(t, player(key))
        if key == "player":
            return self.any_of(t, lambda v: player("white")(v) | player("black")(v))
        if key == "result":
            results = {"1-0": "1-0", "0-1": "0-1", "1/2": "1/2-1/2", "1/2-1/2": "1/2-1/2", "draw": "1/2-1/2", "*": "*"}
            return self.any_of(t, lambda v: Q(result=results[v]) if v in results else None)
        if key == "eco":
            return self.any_of(t, lambda v: Q(eco__istartswith=v))
        if key == "event":
            return self.any_of(t, lambda v: Q(event__icontains=v))
        if key == "year":
            return self.any_of(t, lambda v: _number_q("year", t.op, v))
        if key == "elo":
            def elo(v):
                white, black = _number_q("white_elo", t.op, v), _number_q("black_elo", t.op, v)
                return white | black if white else None
            return self.any_of(t, elo)
        if key == "src":
            return self.any_of(t, lambda v: Q(source__search__contains=fold(v)))
        if key == "ref":
            return self.any_of(t, lambda v: Q(source_ref__icontains=v))
        if key in ("created", "updated"):
            return self.any_of(t, lambda v: _date_q(f"{key}_at", t.op, v, self.now))
        if key in ("has", "no"):
            from spaced_positions.analysis.models import Node

            checks = {
                "analysis": Q(Exists(Node.objects.filter(game=OuterRef("pk"), parent__isnull=False, comment__gt=""))),
                "comment": Q(Exists(Node.objects.filter(game=OuterRef("pk")).exclude(comment=""))),
                "positions": Q(Exists(self._game_positions())),
            }
            return self.any_of(t, lambda v: (checks[v] if key == "has" else ~checks[v]) if v in checks else None)
        if key == "is":
            unlinked = Q(white__isnull=True, white_name__gt="") | Q(black__isnull=True, black_name__gt="")  # :player-link
            return self.any_of(t, lambda v: {"trash": Q(deleted_at__isnull=False), "unlinked": unlinked}.get(v))
        if key == "in":
            return self.any_of(t, self.saved)
        return NotImplemented

    def _game_positions(self):
        from spaced_positions.training.models import Position

        return Position.objects.filter(game=OuterRef("pk"))

    def k_players(self, t):
        if t.key == "role":
            return self.any_of(t, lambda v: Q(role=v))
        return NotImplemented

    def k_sources(self, t):
        if t.key == "kind":
            return self.any_of(t, lambda v: Q(kind=v))
        return NotImplemented

    def k_tags(self, t):
        if t.key == "field":
            return self.any_of(t, lambda v: Q(field__key=v))
        return NotImplemented

    def saved(self, value: str) -> Q | None:
        from .models import SavedQuery

        key = value[2:] if value.startswith("q:") else value
        saved = SavedQuery.objects.filter(key=key).first()
        if saved is None or self.depth > 3:
            return None
        inner = Compiler(self.collection, self.now, self.depth + 1)
        return inner.where(parse(saved.query))

    def text(self, text: str) -> Q | None:
        if not text:
            return None
        v, folded = text, fold(text)
        if self.collection in ("positions", "puzzles"):
            p = self.p
            from .models import PositionTag

            ref = OuterRef("pk") if self.collection == "positions" else OuterRef("position_id")
            return (
                Q(**{f"{p('title')}__icontains": v}) | Q(**{f"{p('description')}__icontains": v})
                | Q(**{f"{p('notes')}__icontains": v}) | Q(**{f"{p('objective')}__icontains": v})
                | Q(**{f"{p('source_text')}__icontains": v}) | Q(**{f"{p('source__search')}__contains": folded})
                | Q(Exists(PositionTag.objects.filter(position=ref, tag__search__contains=folded).exclude(origin="suggested")))
            )
        if self.collection == "games":
            return (Q(white_name__icontains=v) | Q(black_name__icontains=v) | Q(event__icontains=v) | Q(site__icontains=v)
                    | Q(notes__icontains=v) | Q(eco__iexact=v))
        if self.collection in ("players", "sources", "tags"):
            return Q(search__contains=folded)
        return None

    # The whole query ────────────────────────────────────────────────────────────────────────────────────────

    def where(self, parsed: Parsed) -> Q:
        def group(g: Group) -> Q:
            alternatives = []
            for conj in g.alternatives:
                q = Q()
                for item in conj:
                    part = group(item) if isinstance(item, Group) else self.term(item)
                    if part is None:
                        continue
                    q &= ~part if getattr(item, "neg", False) and not isinstance(item, Group) else part
                alternatives.append(q)
            out = Q()
            for i, q in enumerate(alternatives):
                out = q if i == 0 else out | q
            return ~out if g.neg else out
        return group(parsed.root)

    def queryset(self, parsed: Parsed):
        base = base_queryset(self.collection)
        terms = parsed.terms()
        trash = any(t.key == "is" and "trash" in t.values and not t.neg for t in terms)
        if self.collection in ("positions", "games") and not trash:
            base = base.filter(deleted_at=None)
        if self.collection == "puzzles":
            if not trash:
                base = base.filter(position__deleted_at=None)
            base = base.annotate(
                lapse_sum=Sum("cards__lapses", filter=Q(cards__in_solution=True)),
                attempt_sum=Sum("cards__attempts", filter=Q(cards__in_solution=True)),
                success_sum=Sum("cards__successes", filter=Q(cards__in_solution=True)),
                last_seen_at=Max("cards__last_seen"),
            ).annotate(success_rate=100.0 * F("success_sum") / F("attempt_sum"))
        qs = base.filter(self.where(parsed))
        return qs.order_by(*self.order(parsed))

    def order(self, parsed: Parsed) -> list[str]:
        names = {
            "positions": {"created": "created_at", "updated": "updated_at", "difficulty": "difficulty", "title": "title", "id": "id"},
            "games": {"created": "created_at", "year": "year", "white": "white_name", "event": "event", "id": "id"},
            "puzzles": {"created": "created_at", "difficulty": "position__difficulty", "title": "position__title",
                        "success": "success_rate", "lapses": "lapse_sum", "id": "id"},
            "players": {"name": "name", "created": "created_at"},
            "sources": {"title": "title", "created": "created_at"},
            "tags": {"name": "name", "field": "field__order"},
        }[self.collection]
        out = []
        for term in parsed.sort():
            for value in term.values:
                desc = value.startswith("-")
                name = names.get(value.lstrip("-"))
                if name is None:
                    self.problem(term, f"sort: not '{value}' here ({', '.join(names)})")
                    continue
                if self.collection == "puzzles" and value.lstrip("-") == "due":
                    continue
                if term.neg:
                    desc = not desc
                out.append(F(name).desc(nulls_last=True) if desc else F(name).asc(nulls_last=True))
        defaults = {"positions": ["-created_at", "-id"], "games": ["-created_at", "-id"], "puzzles": ["-created_at", "-id"],
                    "players": ["name"], "sources": ["title"], "tags": ["field__order", "order", "id"]}
        return out + defaults[self.collection]


def _material(value: str) -> str | None:
    v = value.upper().replace("V", "v") if value else ""
    if "v" not in v:
        return None
    white, black = v.split("v", 1)
    order = "KQRBNP"
    if any(c not in order for c in white + black):
        return None
    return "".join(sorted(white, key=order.index)) + "v" + "".join(sorted(black, key=order.index))


def base_queryset(collection: str):
    from spaced_positions.training.models import Position, Puzzle

    from .models import Game, Player, Source, Tag

    return {
        "positions": Position.objects.all(),
        "games": Game.objects.all(),
        "puzzles": Puzzle.objects.all(),
        "players": Player.objects.all(),
        "sources": Source.objects.all(),
        "tags": Tag.objects.select_related("field"),
    }[collection]


@dataclass
class Result:
    parsed: Parsed
    queryset: object
    problems: list[Problem]


def run(text: str, collection: str = "positions", now: datetime | None = None) -> Result:
    parsed = parse(text)
    compiler = Compiler(collection, now)
    qs = compiler.queryset(parsed)
    return Result(parsed, qs, parsed.problems + compiler.problems)
