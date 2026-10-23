"""Analysis endpoints (spec 04 · Analyse, 09 §4–6). A change returns the whole tree as JSON (the client steps
through it without requests) and the move tree as HTML (the Moves pane swaps it in), plus the journal entry for undo."""

import json

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import render as render_template
from django.views.decorators.http import require_GET, require_POST

from spaced_positions.core.models import LOCAL_USER
from spaced_positions.training.models import Position

from . import puzzles as analysis_puzzles
from . import render, tree
from .models import JournalEntry, Node


def _json(request) -> dict:
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _position(pid) -> Position:
    try:
        return Position.objects.get(uuid=pid)
    except (Position.DoesNotExist, ValueError, ValidationError):
        raise Http404("no such position") from None


def _node(position, nid) -> Node:
    try:
        return position.nodes.get(id=int(nid))
    except (Node.DoesNotExist, ValueError, TypeError):
        raise Http404("no such move") from None


def _state(position, **extra) -> JsonResponse:
    entry = JournalEntry.objects.filter(user=LOCAL_USER, position=position, undone=False).first()
    return JsonResponse({"ok": True, "tree": tree.tree_json(position), "html": render.render(position),
                         "journal": {"id": entry.id, "label": entry.label} if entry and extra.pop("journaled", False) else None,
                         **extra})


def _fail(message, status=422):
    return JsonResponse({"ok": False, "message": message}, status=status)


@require_GET
def load(request, pid):
    position = _position(pid)
    tree.root(position)
    return _state(position)


@require_POST
def play(request, pid):
    position, data = _position(pid), _json(request)
    parent = _node(position, data.get("parent"))
    try:
        existing = parent.kids.filter(uci=str(data.get("uci", ""))).first()
        if existing:
            return _state(position, node=existing.id)
        with tree.change(position, f"Move {data.get('uci')}"):
            node, _ = tree.play(parent, str(data.get("uci", "")))
    except tree.TreeError as e:
        return _fail(str(e))
    return _state(position, node=node.id, journaled=True)


@require_POST
def line(request, pid):
    """Add a line (from the engine): the moves that exist are reused."""
    position, data = _position(pid), _json(request)
    parent = _node(position, data.get("parent"))
    ucis = [str(u) for u in data.get("ucis", [])][:60]
    try:
        with tree.change(position, "Add engine line"):
            node = tree.add_line(parent, ucis)
    except tree.TreeError as e:
        return _fail(str(e))
    return _state(position, node=node.id, journaled=True)


@require_POST
def edit(request, pid):
    position, data = _position(pid), _json(request)
    node = _node(position, data.get("node"))
    fields = {k: data[k] for k in ("comment", "nags", "mark", "color", "shapes", "squares") if k in data}
    label = {"comment": "Comment", "nags": "Annotation", "mark": "Mark", "color": "Line colour",
             "shapes": "Drawing", "squares": "Drawing"}.get(next(iter(fields), ""), "Edit")
    with tree.change(position, f"{label} {node.san or 'start'}"):
        tree.edit(node, fields)
    return _state(position, node=node.id, journaled=True)


@require_POST
def delete(request, pid):
    position, data = _position(pid), _json(request)
    node = _node(position, data.get("node"))
    try:
        with tree.change(position, f"Delete from {node.san}"):
            parent = tree.delete(node)
    except tree.TreeError as e:
        return _fail(str(e))
    return _state(position, node=parent.id, journaled=True)


@require_POST
def promote(request, pid):
    position, data = _position(pid), _json(request)
    node = _node(position, data.get("node"))
    with tree.change(position, f"Main line {node.san}"):
        tree.promote(node)
    return _state(position, node=node.id, journaled=True)


@require_POST
def reorder(request, pid):
    position, data = _position(pid), _json(request)
    node = _node(position, data.get("node"))
    with tree.change(position, f"Move variation {node.san}"):
        tree.reorder(node, -1 if data.get("step") == "up" else 1)
    return _state(position, node=node.id, journaled=True)


@require_POST
def set_position(request, pid):
    """Correct the start position (the board editor in Analyse)."""
    position, data = _position(pid), _json(request)
    try:
        with tree.change(position, "Correct the position"):
            dropped = tree.change_root(position, str(data.get("fen", "")), force=bool(data.get("force")))
    except tree.TreeError as e:
        return JsonResponse({"ok": False, "message": str(e), "conflict": "moves would go" in str(e)}, status=409)
    message = f"Position corrected; {dropped} moves of the analysis were dropped" if dropped else "Position corrected; the analysis is kept"
    return _state(position, node=tree.root(position).id, message=message, journaled=True)


@require_POST
def replace(request, pid):
    """Replace the moves with a pasted game (spec 06 §6: needs a confirmation in the client)."""
    position, data = _position(pid), _json(request)
    ucis = [str(u) for u in data.get("moves", [])]
    try:
        with tree.change(position, "Replace the moves"):
            if data.get("start") and data["start"] != position.fen:
                tree.change_root(position, data["start"], force=True)
            r = tree.root(position)
            r.kids.all().delete()
            node = tree.add_line(r, ucis)
    except tree.TreeError as e:
        return _fail(str(e))
    return _state(position, node=node.id, journaled=True)


@require_POST
def puzzle(request, pid):
    position, data = _position(pid), _json(request)
    node = _node(position, data.get("node"))
    try:
        with tree.change(position, f"Puzzle: {data.get('action')}"):
            message = analysis_puzzles.act(node, str(data.get("action")))
    except tree.TreeError as e:
        return _fail(str(e))
    return _state(position, node=node.id, message=message, journaled=True)


@require_POST
def create(request):
    """A new position to analyse, from a pasted FEN/PGN or a board line."""
    data = _json(request)
    try:
        position = tree.create_position(str(data.get("start", "")), [str(u) for u in data.get("moves", [])],
                                        title=str(data.get("title", "")), origin=str(data.get("origin", "analysis"))[:40])
    except tree.TreeError as e:
        return _fail(str(e))
    return JsonResponse({"ok": True, "position": str(position.uuid)})


@require_GET
def inspector(request, pid):
    position = _position(pid)
    node = _node(position, request.GET.get("node")) if request.GET.get("node") else tree.root(position)
    p = analysis_puzzles.puzzle_at(node)
    context = {
        "position": position,
        "node": node,
        "nags": [(n, s, n in node.nags) for n, s in tree.NAGS.items() if n in tree.MOVE_NAGS],
        "puzzle": p,
        "puzzle_cards": p.cards.filter(in_solution=True).count() if p else 0,
        "is_start": bool(p and p.start_node_id == node.id),
        "move_count": position.nodes.exclude(parent=None).count(),
    }
    return render_template(request, "analysis/inspector.html", context)


@require_GET
def search(request):
    """Positions for `:analyse <text>` (the library and its query language arrive in phase 4)."""
    q = request.GET.get("q", "").strip()
    rows = Position.objects.all()
    if q:
        rows = rows.filter(Q(title__icontains=q) | Q(source__icontains=q) | Q(fen__startswith=q))
    rows = rows.order_by("-created_at")[:20]
    return JsonResponse({"positions": [{"id": str(p.uuid), "title": p.title or p.fen, "source": p.source} for p in rows]})


@require_GET
def journal(request):
    rows = JournalEntry.objects.filter(user=LOCAL_USER, undone=False).select_related("position").order_by("-id")[:50]
    return JsonResponse({"entries": [{"id": e.id, "label": e.label, "position": str(e.position.uuid) if e.position else None} for e in reversed(rows)]})


def _apply(request, eid, undo: bool):
    try:
        entry = JournalEntry.objects.select_related("position").get(id=eid, user=LOCAL_USER)
    except JournalEntry.DoesNotExist:
        raise Http404("no such journal entry") from None
    if entry.undone == undo:
        return _fail("already " + ("undone" if undo else "redone"), status=409)
    tree.restore(entry.position, entry.before if undo else entry.after)
    entry.undone = undo
    entry.save(update_fields=["undone"])
    return _state(entry.position, message=("Undone: " if undo else "Redone: ") + entry.label)


@require_POST
def undo(request, eid):
    return _apply(request, eid, True)


@require_POST
def redo(request, eid):
    return _apply(request, eid, False)
