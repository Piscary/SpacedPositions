"""Library endpoints (spec 04 · Library, 11 §3): results for a query, completions for the QueryBar, the facets of the
filter pane, and what bulk commands need (the cards of a selection for training, PGN export)."""

import json

from django.db.models import Count, Exists, OuterRef, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
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
VALUES = {
    "has": ["solution", "analysis", "puzzle", "comment", "source", "tags", "game", "positions"],
    "no": ["solution", "analysis", "puzzle", "comment", "source", "tags", "game"],
    "is": ["diagram", "flagged", "draft", "trash", "unlinked"],
    "side": ["w", "b"],
    "state": ["new", "learning", "young", "mature", "relearning"],
    "due": ["today"],
    "result": ["1-0", "0-1", "draw"],
    "role": ["me", "student", "model", "opponent"],
    "kind": [k for k, _ in Source.Kind.choices],
    "sort": ["created", "-created", "updated", "difficulty", "-difficulty", "title", "year", "success", "lapses", "-lapses"],
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
        return qs.select_related("position__source").prefetch_related("position__tag_links__tag__field").annotate(
            card_count=Count("cards", filter=Q(cards__in_solution=True), distinct=True),
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
    })


# ── Groups (sorted by a field with few values: the rows come in foldable groups) ────────────────────────────


def group_label(collection: str, key: str, r) -> str:
    if key == "difficulty":
        d = r.difficulty if collection == "positions" else r.position.difficulty
        return stars(d) if d else "No difficulty"
    if key == "source":
        return r.source.label if r.source_id else "No source"
    if key == "year":
        return str(r.year) if r.year else "No year"
    if key in ("white", "black"):
        return getattr(r, f"{key}_name") or "?"
    if key == "event":
        return r.event or "No event"
    if key == "role":
        return r.get_role_display() if r.role else "No role"
    if key == "kind":
        return r.get_kind_display()
    return r.field.name  # tags by field


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
            path.insert(0, parent.name)
            parent = parent.parent
        out.append({"value": tag.key, "label": " › ".join(path + [tag.name]), "note": tag.field.name})
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
    neg = word.startswith("-")
    body = word[1:] if neg else word
    items = []
    if body.startswith("#"):
        items = [{**i, "value": f"#{i['value']}"} for i in _tag_items(body[1:], None)]
    elif ":" in body:
        key, value = body.split(":", 1)
        key = key.lower()
        last = value.split(",")[-1].lstrip("><=")
        head = value[: len(value) - len(last)]
        fields = {f.key for f in TagField.objects.all()}
        if key in fields or key == "tag":
            items = [{**i, "value": f"{key}:{head}{i['value']}"} for i in _tag_items(last, key if key in fields else None)]
        elif key == "src":
            items = [{"value": f"src:{head}{fold(s.label).split()[0]}", "label": s.label, "note": s.authors}
                     for s in Source.objects.filter(search__contains=fold(last))[:12]]
        elif key in ("white", "black", "player"):
            items = [{"value": f"{key}:{head}@{p.key}", "label": p.name, "note": p.get_role_display() if p.role else ""}
                     for p in Player.objects.filter(search__contains=fold(last.lstrip("@")))[:12]]
        elif key == "in":
            items = [{"value": f"in:q:{s.key}", "label": s.name, "note": s.query} for s in SavedQuery.objects.all()[:12]]
        elif key in VALUES:
            items = [{"value": f"{key}:{head}{v}", "label": v, "note": ""} for v in VALUES[key] if v.startswith(last)]
    else:
        fields = [(f.key, f.name) for f in TagField.objects.all()] if collection in ("positions", "games", "puzzles") else []
        keys = [(f"{k}:", n) for k, n in fields] + [(f"{k}:", "") for k in KEYS[collection]]
        items = [{"value": k, "label": k, "note": n} for k, n in keys if k.startswith(body.lower())][:14]
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
    words = set(text.split())
    groups = []
    for f in TagField.objects.filter(on_positions=True).prefetch_related("tags"):
        tags = sorted((t for t in f.tags.all() if tag_counts.get(t.id)), key=lambda t: -tag_counts[t.id])[:12]
        if tags:
            groups.append({"label": f.name, "key": f.key, "items": [
                {"term": f"{f.key}:{t.key}", "label": t.name, "count": tag_counts[t.id], "on": f"{f.key}:{t.key}" in words}
                for t in tags
            ]})
    diffs = dict(result.queryset.order_by().values_list("difficulty").annotate(n=Count("id")))
    groups.append({"label": "Difficulty", "key": "diff", "items": [
        {"term": f"diff:{d}", "label": "★" * d, "count": diffs.get(d, 0), "on": f"diff:{d}" in words} for d in range(1, 6) if diffs.get(d)
    ]})
    sources = result.queryset.order_by().exclude(source=None).values_list("source", "source__title", "source__short").annotate(n=Count("id")).order_by("-n")[:8]
    groups.append({"label": "Source", "key": "src", "items": [
        {"term": f"src:{fold(short or title).split()[0]}", "label": short or title, "count": n, "on": f"src:{fold(short or title).split()[0]}" in words}
        for _, title, short, n in sources
    ]})
    status = []
    for term, label in [("has:solution", "In training"), ("no:solution", "No puzzle in training"), ("has:analysis", "Analysed"),
                        ("no:analysis", "Not analysed"), ("is:diagram", "Diagrams"), ("is:flagged", "Flagged"), ("is:trash", "Trash")]:
        n = result.queryset.count() if term in words else q.run(f"{text} {term}", "positions").queryset.count()
        status.append({"term": term, "label": label, "count": n, "on": term in words})
    groups.append({"label": "Status", "key": "status", "items": status})
    return render(request, "library/facets.html", {"groups": [g for g in groups if g["items"]], "total": result.queryset.count()})


# ── For bulk commands ─────────────────────────────────────────────────────────────────────────────────────────


def _body(request) -> dict:
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


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
        return HttpResponse("Only positions and games export as PGN", status=400)
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


def position_ids(collection, found) -> list[int]:
    if collection == "positions":
        return list(found.values_list("pk", flat=True))
    if collection == "puzzles":
        return list(found.values_list("position_id", flat=True).distinct())
    return []


@require_GET
def subject(request):
    """The positions (uuids) of the selection or the query, in order: Analyse's subject list (`a`)."""
    collection = _collection(request)
    ids = [i for i in request.GET.get("ids", "").split(",") if i]
    found = objects(collection, ids, request.GET.get("q", ""))
    if collection == "positions":
        uuids = [str(u) for u in found.values_list("uuid", flat=True)[:1000]]
    elif collection == "puzzles":
        uuids = list(dict.fromkeys(str(u) for u in found.values_list("position__uuid", flat=True)[:1000]))
    elif collection == "games":
        uuids = [str(u) for u in found.values_list("uuid", flat=True)[:1000]]
    else:
        uuids = []
    return JsonResponse({"ids": uuids})
