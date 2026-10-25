"""Library endpoints (spec 04 · Library, 11 §3): results for a query, completions for the QueryBar, the facets of the
filter pane, and what bulk commands need (the cards of a selection for training, PGN export)."""

import json

from django.db.models import Count, Exists, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_GET, require_POST

from spaced_positions.analysis.models import Node
from spaced_positions.core.templatetags.ui import stars
from spaced_positions.training.models import Card, Puzzle

from . import query as q
from .models import Player, PositionTag, SavedQuery, Source, Tag, TagField
from .text import fold

PAGE = 200
DISPLAYS = ("table", "list", "grid")
KEYS = {
    "positions": ["tag", "diff", "side", "src", "page", "ref", "has", "no", "is", "material", "pieces", "fen", "created",
                  "updated", "game", "in", "sort"],
    "games": ["tag", "white", "black", "player", "result", "eco", "event", "year", "elo", "src", "ref", "has", "no", "is",
              "created", "in", "sort"],
    "puzzles": ["tag", "diff", "side", "src", "due", "state", "lapses", "success", "last", "attempts", "has", "is", "in", "sort"],
    "players": ["role", "sort"],
    "sources": ["kind", "sort"],
    "tags": ["field", "sort"],
}
# What each key means, shown next to it in the completion (spec 11 §3)
KEY_NOTES = {
    "tag": gettext_lazy("a tag of any field"), "diff": gettext_lazy("difficulty 1–5: diff:3, diff:>=3, diff:2..4"),
    "side": gettext_lazy("who is to move: w or b"), "src": gettext_lazy("a source: its name, or words of it"),
    "page": gettext_lazy("page in the source"), "ref": gettext_lazy("diagram number in the source"),
    "has": gettext_lazy("has a solution, an analysis, a puzzle …"), "no": gettext_lazy("has no solution, analysis, puzzle …"),
    "is": gettext_lazy("is a diagram, flagged, a draft, in the trash"), "material": gettext_lazy("material: material:Q+R-R"),
    "pieces": gettext_lazy("number of pieces: pieces:<=7"), "fen": gettext_lazy("part of the position's FEN"),
    "created": gettext_lazy("added: created:today, created:<7d, created:2026-10"), "updated": gettext_lazy("changed: updated:<7d"),
    "game": gettext_lazy("from a game: game:yes"), "in": gettext_lazy("in a saved query: in:q:name"),
    "sort": gettext_lazy("order: sort:diagram, sort:-difficulty"), "white": gettext_lazy("the white player"),
    "black": gettext_lazy("the black player"), "player": gettext_lazy("either player"), "result": gettext_lazy("1-0, 0-1 or draw"),
    "eco": gettext_lazy("opening code: eco:B90"), "event": gettext_lazy("words of the event"), "year": gettext_lazy("year: year:>=1990"),
    "elo": gettext_lazy("either player's Elo: elo:>2500"), "due": gettext_lazy("due for review: due:today"),
    "state": gettext_lazy("card stage: new, learning, young, mature"), "lapses": gettext_lazy("times forgotten: lapses:>=2"),
    "success": gettext_lazy("success rate: success:<60%"), "last": gettext_lazy("last trained: last:>30d"),
    "attempts": gettext_lazy("times trained: attempts:0"), "role": gettext_lazy("me, student, model, opponent"),
    "kind": gettext_lazy("book, website, own analysis …"), "field": gettext_lazy("a tag field: field:motif"),
}
VALUE_NOTES = {
    "solution": gettext_lazy("a puzzle in training"), "analysis": gettext_lazy("moves analysed"), "puzzle": gettext_lazy("a puzzle, also a draft"),
    "comment": gettext_lazy("a comment in its analysis"), "source": gettext_lazy("a source"), "tags": gettext_lazy("any tag"),
    "game": gettext_lazy("from a game"), "positions": gettext_lazy("positions taken from it"), "diagram": gettext_lazy("may be illegal, not played"),
    "flagged": gettext_lazy("marked as broken in training"), "draft": gettext_lazy("a puzzle not yet in training"),
    "trash": gettext_lazy("in the trash"), "unlinked": gettext_lazy("a name without a player"),
}

# Keys that compare numbers or dates (`diff:>=3`, `created:<7d`); the others name things
NUMERIC = {"diff", "page", "ref", "pieces", "year", "elo", "lapses", "success", "attempts", "created", "updated", "due", "last"}
VALUES = {
    "has": ["solution", "analysis", "puzzle", "comment", "source", "tags", "game", "positions"],
    "no": ["solution", "analysis", "puzzle", "comment", "source", "tags", "game"],
    "is": ["diagram", "flagged", "draft", "trash", "unlinked"],
    "side": ["w", "b"],
    "state": ["new", "learning", "young", "mature", "relearning"],
    "due": ["today"],
    "result": ["1-0", "0-1", "draw"],
    "diff": ["1", "2", "3", "4", "5"],
    "role": ["me", "student", "model", "opponent"],
    "kind": [k for k, _ in Source.Kind.choices],
}


def _collection(request) -> str:
    c = request.GET.get("c", "positions")
    return c if c in q.COLLECTIONS else "positions"


def _rows(collection, qs):
    if collection == "positions":
        return qs.select_related("source").prefetch_related("tag_links__tag__field").annotate(
            in_training=Exists(Puzzle.objects.filter(position=OuterRef("pk"), active=True)),
            has_puzzle=Exists(Puzzle.objects.filter(position=OuterRef("pk"))),
            has_analysis=Exists(Node.objects.filter(position=OuterRef("pk"), parent__isnull=False)),
        )
    if collection == "puzzles":
        cards = Card.objects.filter(puzzle=OuterRef("pk"), in_solution=True).order_by().values("puzzle").annotate(n=Count("pk")).values("n")
        return qs.select_related("position__source").prefetch_related("position__tag_links__tag__field").annotate(
            card_count=Coalesce(Subquery(cards), 0),  # for the shown rows only, not a count over every puzzle
        )
    if collection == "games":
        return qs.select_related("source")
    if collection == "players":
        return qs.annotate(game_count=Count("white_games", distinct=True) + Count("black_games", distinct=True))
    if collection == "sources":
        return qs.annotate(position_count=Count("positions", distinct=True), game_count=Count("games", distinct=True))
    if collection == "tags":
        return qs.annotate(position_count=Count("positions", distinct=True))
    return qs


@require_GET
def results(request):
    collection = _collection(request)
    display = request.GET.get("display", "table")
    display = display if display in DISPLAYS else "table"
    offset = max(0, int(request.GET.get("offset", 0) or 0))
    result = q.run(request.GET.get("q", ""), collection)
    total = result.queryset.count()
    rows = list(_rows(collection, result.queryset)[offset : offset + PAGE])
    if collection == "games":
        sparks = eval_sparks([r.pk for r in rows])
        for r in rows:
            r.spark = sparks.get(r.pk, "")
    sort = next((v for t in result.parsed.sort() for v in t.values), "")
    if sort.lstrip("-") in q.GROUPS[collection]:
        mark_groups(collection, sort.lstrip("-"), rows)
    info = {
        "sort": sort, "sorts": list(q.SORTS[collection]), "groups": list(q.GROUPS[collection]),
        "count": total,
        "shown": offset + len(rows),
        "terms": [{"start": t.start, "end": t.end, "key": t.key, "neg": t.neg} for t in result.parsed.terms()],
        "problems": [{"start": p.start, "end": p.end, "message": p.message} for p in result.problems],
    }
    return render(request, "library/results.html", {
        "collection": collection, "display": display, "rows": rows, "offset": offset, "info": info, "more": total - info["shown"],
        "query": request.GET.get("q", "").strip(),
    })


# ── Groups (sorted by a field with few values: the rows come in foldable groups) ────────────────────────────


def group_label(collection: str, key: str, r) -> str:
    if key == "difficulty":
        d = r.difficulty if collection == "positions" else r.position.difficulty
        return stars(d) if d else gettext("No difficulty")
    if key == "source":
        p = r if collection == "positions" else r.position
        return p.source.label if p.source_id else gettext("No source")
    if key == "year":
        return str(r.year) if r.year else gettext("No year")
    if key in ("white", "black"):
        return getattr(r, f"{key}_name") or "?"
    if key == "event":
        return r.event or gettext("No event")
    if key == "role":
        return r.get_role_display() if r.role else gettext("No role")
    if key == "kind":
        return r.get_kind_display()
    return r.field.label  # tags by field


def mark_groups(collection: str, key: str, rows: list) -> None:
    """Each row gets its group; the first of a group carries the header (label and how many rows on this page)."""
    sizes: dict[str, int] = {}
    for r in rows:
        r.group = group_label(collection, key, r)
        sizes[r.group] = sizes.get(r.group, 0) + 1
    previous = None
    for r in rows:
        r.group_start = r.group != previous
        r.group_size = sizes[r.group]
        previous = r.group


# ── EvalGraph thumbnails (05 · EvalGraph) ─────────────────────────────────────────────────────────────────────

SPARK_CLIP = 500  # centipawns: the graph's scale, as in graphs.js


def eval_sparks(game_ids: list[int], width: int = 64, height: int = 16) -> dict[int, str]:
    """A tiny eval graph of each game's main line (the evaluations `:evaluate` stored), as SVG points."""
    from django.utils.html import format_html

    nodes = Node.objects.filter(game_id__in=game_ids).values("id", "parent_id", "order", "game_id", "eval_cp", "eval_mate")
    kids, roots = {}, {}
    for n in sorted(nodes, key=lambda n: (n["order"], n["id"])):
        if n["parent_id"] is None:
            roots[n["game_id"]] = n
        else:
            kids.setdefault(n["parent_id"], []).append(n)
    out = {}
    for game_id, root in roots.items():
        values, node = [], root
        while kids.get(node["id"]):
            node = kids[node["id"]][0]
            if node["eval_mate"] is not None:
                values.append(SPARK_CLIP if node["eval_mate"] > 0 or (node["eval_mate"] == 0 and (node["eval_cp"] or 0) > 0) else -SPARK_CLIP)
            elif node["eval_cp"] is not None:
                values.append(max(-SPARK_CLIP, min(SPARK_CLIP, node["eval_cp"])))
        if len(values) < 2:
            continue
        step = width / (len(values) - 1)
        points = " ".join(f"{i * step:.1f},{height / 2 - v / SPARK_CLIP * height / 2:.1f}" for i, v in enumerate(values))
        out[game_id] = format_html(
            '<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="Evaluation over {n} moves">'
            '<line x1="0" y1="{m}" x2="{w}" y2="{m}"></line><polyline points="{p}"></polyline></svg>',
            w=width, h=height, m=height / 2, n=len(values), p=points,
        )
    return out


# ── Completions for the QueryBar ──────────────────────────────────────────────────────────────────────────────


def _word_at(text: str, at: int) -> tuple[int, int, str]:
    start = at
    while start > 0 and not text[start - 1].isspace() and text[start - 1] not in "()":
        start -= 1
    end = at
    while end < len(text) and not text[end].isspace() and text[end] not in "()":
        end += 1
    return start, end, text[start:end]


def _tag_items(prefix: str, field_key: str | None, limit=12):
    """Tags for a typed word: exact names, keys and aliases first, then those that start with it, then the rest that
    contain it."""
    v = fold(prefix)
    tags = Tag.objects.select_related("field", "parent__parent").order_by("field__order", "order")
    if field_key:
        tags = tags.filter(field__key=field_key)
    ranked = []
    for tag in tags:
        parts = tag.search.split(" | ")
        if not v:
            rank = 2
        elif v in parts:
            rank = 0
        elif any(part.startswith(v) for part in parts):
            rank = 1
        elif v in tag.search:
            rank = 2
        else:
            continue
        ranked.append((rank, tag))
    out = []
    for _, tag in sorted(ranked, key=lambda x: x[0])[:limit]:
        path, parent = [], tag.parent
        while parent is not None and len(path) < 3:
            path.insert(0, parent.label)
            parent = parent.parent
        out.append({"value": tag.key, "label": " › ".join(path + [tag.label]), "note": tag.field.label})
    return out


@require_GET
def complete(request):
    """Completions for the word at the cursor (`at`), or for one kind (`kind=tag|source|player`)."""
    kind = request.GET.get("kind")
    text = request.GET.get("q", "")
    if kind == "tag":
        return JsonResponse({"items": _tag_items(text, None, 20)})
    if kind == "source":
        found = Source.objects.filter(search__contains=fold(text)) if text else Source.objects.all()
        return JsonResponse({"items": [{"value": str(s.pk), "label": s.label, "note": s.authors} for s in found[:20]]})
    collection = _collection(request)
    at = int(request.GET.get("at", len(text)) or 0)
    start, end, word = _word_at(text, max(0, min(at, len(text))))
    neg = word[:1] in "-!" and len(word) > 0
    body = word[1:] if neg else word
    items = []
    if body.startswith("#"):
        items = [{**i, "value": f"#{i['value']}"} for i in _tag_items(body[1:], None)]
    elif ":" in body or "!=" in body or "<>" in body:
        if ":" not in body:  # key!=value
            body = body.replace("!=", ":!=", 1).replace("<>", ":<>", 1)
        key, value = body.split(":", 1)
        key = key.lower()
        for form in q.NOT_FORMS:  # key:!=value, key:<>value, key:!value: completed as -key:value
            if value.startswith(form):
                neg, value = not neg, value[len(form):]
                break
        last = value.split(",")[-1]
        if key in NUMERIC:
            last = last.lstrip("><=")  # diff:>=3: the comparison stays
        else:
            value = value.lstrip("><=")  # no comparisons on names
            last = last.lstrip("><=")
        head = value[: len(value) - len(last)]
        fields = {f.key for f in TagField.objects.all()}
        if key in fields or key == "tag":
            items = [{**i, "value": f"{key}:{head}{i['value']}"} for i in _tag_items(last, key if key in fields else None)]
        elif key == "src":
            found = Source.objects.all()
            for word in fold(last.strip('"')).split():
                found = found.filter(search__contains=word)
            items = [{"value": f"{source_term(s.label).replace('src:', f'src:{head}', 1)}", "label": s.label, "note": s.authors}
                     for s in found[:12]]
        elif key in ("white", "black", "player"):
            items = [{"value": f"{key}:{head}@{p.key}", "label": p.name, "note": p.get_role_display() if p.role else ""}
                     for p in Player.objects.filter(search__contains=fold(last.lstrip("@")))[:12]]
        elif key == "in":
            items = [{"value": f"in:q:{s.key}", "label": s.name, "note": s.query} for s in SavedQuery.objects.all()[:12]]
        elif key in VALUES or key == "sort":
            values = [v for name in q.SORTS[collection] for v in (name, f"-{name}")] if key == "sort" else VALUES[key]
            items = [{"value": f"{key}:{head}{v}", "label": v,
                      "note": gettext("in groups") if key == "sort" and v.lstrip("-") in q.GROUPS[collection] else str(VALUE_NOTES.get(v, ""))}
                     for v in values if v.startswith(last)]
    else:
        fields = [(f.key, f.label) for f in TagField.objects.all()] if collection in ("positions", "games", "puzzles") else []
        keys = [(f"{k}:", n) for k, n in fields] + [(f"{k}:", str(KEY_NOTES.get(k, ""))) for k in KEYS[collection]]
        items = [{"value": k, "label": k, "note": n} for k, n in keys if k.startswith(body.lower())][:14]
        if not body and not neg:  # an empty word: the grammar first
            items = [{"value": "-", "label": "-", "note": gettext("not: -is:diagram excludes diagrams")},
                     {"value": "or", "label": "or", "note": gettext("either: motif:fork or motif:pin")},
                     {"value": "(", "label": "( )", "note": gettext("a group: -(motif:fork or motif:pin)")}] + items
        if body and collection in ("positions", "games", "puzzles"):
            items += [{**i, "value": f"#{i['value']}"} for i in _tag_items(body, None, 6)]
    if neg:
        items = [{**i, "value": f"-{i['value']}"} for i in items]
    return JsonResponse({"start": start, "end": end, "items": items})


# ── Facets for the filter pane ────────────────────────────────────────────────────────────────────────────────


@require_GET
def facets(request):
    text = request.GET.get("q", "")
    result = q.run(text, "positions")
    ids = result.queryset.values("pk")
    tag_counts = dict(
        PositionTag.objects.filter(position__in=ids).order_by().exclude(origin="suggested").values_list("tag").annotate(n=Count("id"))
    )
    words = {w for kind, w, _, _ in q._tokens(text) if kind == "word"}  # quoted terms stay whole
    groups = []
    for f in TagField.objects.filter(on_positions=True).prefetch_related("tags"):
        tags = sorted((t for t in f.tags.all() if tag_counts.get(t.id)), key=lambda t: -tag_counts[t.id])[:12]
        tags += [t for t in f.tags.all() if f"-{f.key}:{t.key}" in words and t not in tags]  # excluded: shown, to bring back
        if tags:
            groups.append({"label": f.label, "key": f.key, "items": [
                {"term": f"{f.key}:{t.key}", "label": t.label, "count": tag_counts.get(t.id, 0), "on": f"{f.key}:{t.key}" in words}
                for t in tags
            ]})
    diffs = dict(result.queryset.order_by().values_list("difficulty").annotate(n=Count("id")))
    groups.append({"label": gettext("Difficulty"), "key": "diff", "items": [
        {"term": f"diff:{d}", "label": "★" * d, "count": diffs.get(d, 0), "on": f"diff:{d}" in words} for d in range(1, 6) if diffs.get(d)
    ]})
    sources = result.queryset.order_by().exclude(source=None).values_list("source", "source__title", "source__short").annotate(n=Count("id")).order_by("-n")[:12]
    groups.append({"label": gettext("Source"), "key": "src", "items": [
        {"term": source_term(short or title), "label": short or title, "count": n, "on": source_term(short or title) in words}
        for _, title, short, n in sources
    ]})
    labels = [("has:solution", gettext("In training")), ("no:solution", gettext("No puzzle in training")), ("has:analysis", gettext("Analysed")),
              ("no:analysis", gettext("Not analysed")), ("is:diagram", gettext("Diagrams")), ("is:flagged", gettext("Flagged"))]
    compiler = q.Compiler("positions")  # one query counts them all: each status is a filtered count of the results
    counts = result.queryset.order_by().aggregate(**{f"n{i}": Count("pk", filter=compiler.where(q.parse(term))) for i, (term, _) in enumerate(labels)})
    status = [{"term": term, "label": label, "count": counts[f"n{i}"], "on": term in words} for i, (term, label) in enumerate(labels)]
    trash = "is:trash"  # the trash isn't in the results unless asked for: counted on its own
    n = result.queryset.count() if trash in words else q.run(f"{text} {trash}", "positions").queryset.count()
    status.append({"term": trash, "label": gettext("Trash"), "count": n, "on": trash in words})
    groups.append({"label": gettext("Status"), "key": "status", "items": status})
    for item in (i for g in groups for i in g["items"]):
        item["off"] = f"-{item['term']}" in words  # excluded: ↵ takes the exclusion out again
    return render(request, "library/facets.html", {
        "groups": [g for g in groups if g["items"]], "total": result.queryset.count(), "active": active_terms(text),
    })


def active_terms(text: str) -> list[dict]:
    """What the query asks for, one row per term or group at its top level: each can be taken out on its own."""
    parsed = q.parse(text)
    if not text.strip():
        return []
    if len(parsed.root.alternatives) != 1:  # `a or b` at the top: one whole
        return [{"start": 0, "end": len(text), "text": text.strip(), "note": gettext("either side of “or”")}]
    fields = {f.key: f for f in TagField.objects.all()}
    out = []
    for item in parsed.root.alternatives[0]:
        piece = text[item.start:item.end]
        if isinstance(item, q.Group):
            note = gettext("a group in brackets")
        else:
            note = describe_term(item, fields)
        if item.neg:
            note = gettext("not: {what}").format(what=note)
        out.append({"start": item.start, "end": item.end, "text": piece, "note": note})
    return out


def describe_term(term, fields) -> str:
    """A term in words, for the filter pane: `motif:pin` → “Motif: Pin”, `no:solution` → “no: a puzzle in training”."""
    value = term.values[0] if term.values else ""
    if term.key == "":
        return gettext("words: {text}").format(text=" ".join(term.values))
    if term.key in ("#", "tag") or term.key in fields:
        tag = Tag.objects.filter(key=value).select_related("field").first()
        name = tag.label if tag else value
        field_label = fields[term.key].label if term.key in fields else gettext("Tag")
        return f"{field_label}: {name}"
    if term.key in ("has", "no", "is") and value in VALUE_NOTES:
        return f"{term.key}: {VALUE_NOTES[value]}"
    if term.key == "sort":
        return gettext("order: {by}").format(by=value)
    note = KEY_NOTES.get(term.key)
    return f"{note.split(':')[0]}: {term.op}{', '.join(term.values)}" if note else f"{term.key}: {term.op}{', '.join(term.values)}"


def source_term(name: str) -> str:
    """The query term for exactly one source: its whole name, quoted when it has spaces."""
    clean = name.replace('"', "")
    return f'src:"{clean}"' if " " in clean else f"src:{clean}"


# ── For bulk commands ─────────────────────────────────────────────────────────────────────────────────────────


def _body(request) -> dict:
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def ordered(collection: str, ids: list, text: str = ""):
    """Like objects(), in the query's order also for a selection (Analyse's subject list, training in order)."""
    if not ids:
        return objects(collection, ids, text)
    chosen = objects(collection, ids, text).values("pk")
    return q.run(text, collection).queryset.filter(pk__in=chosen) if text else objects(collection, ids, text)


def objects(collection: str, ids: list, text: str = ""):
    """The objects a bulk command acts on: the given short ids (`p12`, `z3` …), else everything the query finds."""
    if ids:
        pks = [int(str(i)[1:]) for i in ids if str(i)[1:].isdigit()]
        uuids = [str(i) for i in ids if "-" in str(i)]
        return q.base_queryset(collection).filter(Q(pk__in=pks) | Q(uuid__in=uuids) if uuids else Q(pk__in=pks))
    return q.run(text, collection).queryset


@require_POST
def cards(request):
    """The cards to train for a selection or a query (`T`): puzzles in training of the positions or puzzles."""
    data = _body(request)
    collection = data.get("c", "positions")
    found = objects(collection, data.get("ids", []), data.get("q", ""))
    cards = Card.objects.filter(in_solution=True, puzzle__active=True, puzzle__position__deleted_at=None)
    if collection == "puzzles":
        cards = cards.filter(puzzle__in=found)
    elif collection == "positions":
        cards = cards.filter(puzzle__position__in=found)
    else:
        cards = cards.none()
    if data.get("count"):  # the launcher's "86 cards match"
        return JsonResponse({"count": cards.count()})
    text = data.get("q", "")
    if q.parse(text).sort():  # in the query's order (a source in the order of its diagrams); else the easiest first
        rank = {pk: i for i, pk in enumerate(ordered(collection, data.get("ids", []), text).values_list("pk", flat=True)[:2000])}
        key = "puzzle_id" if collection == "puzzles" else "puzzle__position_id"
        rows = sorted(cards.values_list("uuid", key, "id")[:2000], key=lambda r: (rank.get(r[1], len(rank)), r[2]))
        ids = [str(u) for u, _, _ in rows[:500]]
    else:
        ids = [str(u) for u in cards.order_by("puzzle__position__difficulty", "id").values_list("uuid", flat=True)[:500]]
    return JsonResponse({"cards": ids})


@require_GET
def export(request):
    """PGN of the selection or the query: positions with their analysis, games as they are."""
    from spaced_positions.analysis.pgn import export_position, export_game

    collection = _collection(request)
    ids = [i for i in request.GET.get("ids", "").split(",") if i]
    found = objects(collection, ids, request.GET.get("q", ""))[:2000]
    if collection == "positions":
        text = "\n\n".join(export_position(p) for p in found)
    elif collection == "games":
        text = "\n\n".join(export_game(g) for g in found)
    else:
        return HttpResponse(gettext("Only positions and games export as PGN"), status=400)
    response = HttpResponse(text, content_type="application/x-chess-pgn; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="spaced-positions-{collection}.pgn"'
    return response


@require_GET
def fens(request):
    collection = _collection(request)
    ids = [i for i in request.GET.get("ids", "").split(",") if i]
    found = objects(collection, ids, request.GET.get("q", ""))[:2000]
    if collection == "puzzles":
        return JsonResponse({"fens": [p.start_fen for p in found]})
    if collection == "positions":
        return JsonResponse({"fens": [p.fen for p in found]})
    return JsonResponse({"fens": []})


@require_GET
def subject(request):
    """The positions (uuids) of the selection or the query, in order: Analyse's subject list (`a`)."""
    collection = _collection(request)
    ids = [i for i in request.GET.get("ids", "").split(",") if i]
    found = ordered(collection, ids, request.GET.get("q", ""))
    if collection == "positions":
        uuids = [str(u) for u in found.values_list("uuid", flat=True)[:1000]]
    elif collection == "puzzles":
        uuids = list(dict.fromkeys(str(u) for u in found.values_list("position__uuid", flat=True)[:1000]))
    elif collection == "games":
        uuids = [str(u) for u in found.values_list("uuid", flat=True)[:1000]]
    else:
        uuids = []
    return JsonResponse({"ids": uuids})
