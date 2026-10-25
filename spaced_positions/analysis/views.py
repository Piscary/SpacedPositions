"""Analysis endpoints (spec 04 · Analyse, 09 §4–6). A change returns the whole tree as JSON (the client steps
through it without requests) and the move tree as HTML (the Moves pane swaps it in), plus the journal entry for undo."""

import json

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import render as render_template
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_GET, require_POST

from spaced_positions.core.models import LOCAL_USER
from spaced_positions.library.text import fold
from spaced_positions.library.models import Game
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


def _position(pid):
    """The owner of a tree: a position, or a game (spec 11 §1)."""
    try:
        return Position.objects.filter(uuid=pid).first() or Game.objects.get(uuid=pid)
    except (Game.DoesNotExist, ValueError, ValidationError):
        raise Http404("no such position or game") from None


def _node(position, nid) -> Node:
    try:
        return position.nodes.get(id=int(nid))
    except (Node.DoesNotExist, ValueError, TypeError):
        raise Http404("no such move") from None


def _state(position, **extra) -> JsonResponse:
    entry = JournalEntry.objects.filter(user=LOCAL_USER, undone=False, **tree.owner_of(owner=position)).first()
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
        with tree.change(position, _("Add engine line")):
            node = tree.add_line(parent, ucis)
    except tree.TreeError as e:
        return _fail(str(e))
    return _state(position, node=node.id, journaled=True)


@require_POST
def edit(request, pid):
    position, data = _position(pid), _json(request)
    node = _node(position, data.get("node"))
    fields = {k: data[k] for k in ("comment", "nags", "mark", "color", "shapes", "squares") if k in data}
    label = {"comment": _("Comment"), "nags": _("Annotation"), "mark": _("Mark"), "color": _("Line colour"),
             "shapes": _("Drawing"), "squares": _("Drawing")}.get(next(iter(fields), ""), _("Edit"))
    with tree.change(position, f"{label} {node.san or _('start')}"):
        tree.edit(node, fields)
    return _state(position, node=node.id, journaled=True)


@require_POST
def delete(request, pid):
    position, data = _position(pid), _json(request)
    node = _node(position, data.get("node"))
    try:
        with tree.change(position, _("Delete from {move}").format(move=node.san)):
            parent = tree.delete(node)
    except tree.TreeError as e:
        return _fail(str(e))
    return _state(position, node=parent.id, journaled=True)


@require_POST
def promote(request, pid):
    position, data = _position(pid), _json(request)
    node = _node(position, data.get("node"))
    with tree.change(position, _("Main line {move}").format(move=node.san)):
        tree.promote(node)
    return _state(position, node=node.id, journaled=True)


@require_POST
def reorder(request, pid):
    position, data = _position(pid), _json(request)
    node = _node(position, data.get("node"))
    with tree.change(position, _("Move variation {move}").format(move=node.san)):
        tree.reorder(node, -1 if data.get("step") == "up" else 1)
    return _state(position, node=node.id, journaled=True)


@require_POST
def set_position(request, pid):
    """Correct the start position (the board editor in Analyse)."""
    position, data = _position(pid), _json(request)
    try:
        with tree.change(position, _("Correct the position")):
            dropped = tree.change_root(position, str(data.get("fen", "")), force=bool(data.get("force")))
    except tree.TreeError as e:
        # a conflict is a question for the user (drop the moves?), not an error
        return JsonResponse({"ok": False, "message": str(e), "conflict": e.conflict}, status=200 if e.conflict else 422)
    message = (ngettext("Position corrected; {n} move of the analysis was dropped", "Position corrected; {n} moves of the analysis were dropped", dropped).format(n=dropped)
               if dropped else _("Position corrected; the analysis is kept"))
    return _state(position, node=tree.root(position).id, message=message, journaled=True)


@require_POST
def replace(request, pid):
    """Replace the moves with a pasted game (spec 06 §6: needs a confirmation in the client)."""
    position, data = _position(pid), _json(request)
    ucis = [str(u) for u in data.get("moves", [])]
    try:
        with tree.change(position, _("Replace the moves")):
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
    if tree.is_game(position):
        return render_template(request, "analysis/inspector_game.html", {
            "game": position, "node": node,
            "nags": [(n, s, n in node.nags) for n, s in tree.NAGS.items() if n in tree.MOVE_NAGS],
            "headers": [(k, v) for k, v in [(_("White"), position.white_name), (_("Black"), position.black_name), (_("Result"), position.result),
                        (_("Date"), position.date), (_("Event"), position.event), (_("Site"), position.site), (_("Round"), position.round),
                        ("ECO", position.eco), (_("White Elo"), position.white_elo), (_("Black Elo"), position.black_elo),
                        *position.headers.items()] if v],
            "positions": position.positions.filter(deleted_at=None)[:20],
        })
    context = {
        "position": position,
        "node": node,
        "nags": [(n, s, n in node.nags) for n, s in tree.NAGS.items() if n in tree.MOVE_NAGS],
        "puzzle": p,
        "puzzle_cards": p.cards.filter(in_solution=True).count() if p else 0,
        "is_start": bool(p and p.start_node_id == node.id),
        "move_count": position.nodes.exclude(parent=None).count(),
        "position_tags": position.tag_links.select_related("tag__field").order_by("tag__field__order", "tag__order"),
        "move_tags": node.tag_links.select_related("tag__field").order_by("tag__field__order", "tag__order") if node.parent_id else [],
    }
    return render_template(request, "analysis/inspector.html", context)


@require_GET
def search(request):
    """Positions for `:analyse <text>` (searched like the Library's query)."""
    q = request.GET.get("q", "").strip()
    rows = Position.alive.all()
    if q:
        rows = rows.filter(Q(title__icontains=q) | Q(source_text__icontains=q) | Q(source__search__contains=fold(q)) | Q(fen__startswith=q))
    rows = rows.select_related("source").order_by("-created_at")[:20]
    return JsonResponse({"positions": [{"id": str(p.uuid), "title": p.title or p.fen, "source": p.citation} for p in rows]})


@require_GET
def journal(request):
    rows = JournalEntry.objects.filter(user=LOCAL_USER, undone=False).select_related("position", "game").order_by("-id")[:50]
    return JsonResponse({"entries": [{"id": e.id, "label": e.label, "position": str((e.position or e.game).uuid) if (e.position or e.game) else None}
                                     for e in reversed(rows)]})


def _apply(request, eid, undo: bool):
    try:
        entry = JournalEntry.objects.select_related("position", "game").get(id=eid, user=LOCAL_USER)
    except JournalEntry.DoesNotExist:
        raise Http404("no such journal entry") from None
    if entry.undone == undo:
        return _fail("already " + ("undone" if undo else "redone"), status=409)
    owner = entry.position or entry.game
    tree.restore(owner, entry.before if undo else entry.after)
    entry.undone = undo
    entry.save(update_fields=["undone"])
    return _state(owner, message=("Undone: " if undo else "Redone: ") + entry.label)


@require_POST
def undo(request, eid):
    return _apply(request, eid, True)


@require_POST
def redo(request, eid):
    return _apply(request, eid, False)


@require_POST
def new_position(request, pid):
    """`:new-position`: the position after this move becomes a position of its own (linked to the game it came from);
    with `moves`, the continuation (the main line, up to 40 plies) becomes its main line."""
    owner, data = _position(pid), _json(request)
    node = _node(owner, data.get("node"))
    ucis = []
    if data.get("moves"):
        n = node
        while len(ucis) < 40:
            kid = n.kids.order_by("order", "id").first()
            if kid is None:
                break
            ucis.append(kid.uci)
            n = kid
    title = f"{owner.title}, after {node.ply // 2 + node.ply % 2}{'.' if node.ply % 2 else '…'}{node.san}" if node.parent_id else owner.title
    try:
        position = tree.create_position(node.fen, ucis, title=title, origin="game" if tree.is_game(owner) else "position")
    except tree.TreeError as e:
        return _fail(str(e))
    if tree.is_game(owner):
        position.game, position.game_node = owner, node
        position.save(update_fields=["game", "game_node"])
    return JsonResponse({"ok": True, "position": str(position.uuid), "message": _("New position {id}").format(id=position.short_id)})


@require_POST
def evals(request, pid):
    """Engine evaluations of moves (`:evaluate`), from white's side: {"evals": {node id: {cp, mate, depth}}}. Not a
    change of the analysis (no journal entry): the engine can always compute them again."""
    owner, data = _position(pid), _json(request)
    rows = data.get("evals") or {}
    nodes = {n.id: n for n in owner.nodes.filter(id__in=[int(k) for k in rows if str(k).isdigit()])}
    for key, value in rows.items():
        node = nodes.get(int(key)) if str(key).isdigit() else None
        if node is None or not isinstance(value, dict):
            continue
        node.eval_cp = int(value["cp"]) if value.get("cp") is not None else None
        node.eval_mate = int(value["mate"]) if value.get("mate") is not None else None
        node.eval_depth = int(value.get("depth") or 0) or None
        node.save(update_fields=["eval_cp", "eval_mate", "eval_depth"])
    return _state(owner, message=ngettext("Evaluated {n} move", "Evaluated {n} moves", len(nodes)).format(n=len(nodes)))


@require_POST
def moments(request, pid):
    """`:moments`: the key moments of the main line as move tags (library/moments.py)."""
    from spaced_positions.library import moments as found

    owner = _position(pid)
    result = found.run(owner)
    how = {"local": _("with the local engine"), "stored": _("with the stored evaluations"),
           "": _("without evaluations (:evaluate, or a local engine)")}[result["engine"]]
    message = _("Moments {how}: {tags} on {moves}").format(
        how=how, tags=ngettext("{n} new tag", "{n} new tags", result["tags"]).format(n=result["tags"]),
        moves=ngettext("{n} move", "{n} moves", result["moves"]).format(n=result["moves"]))
    if result["withdrawn"]:
        message += " · " + _("{n} withdrawn").format(n=result["withdrawn"])
    return _state(owner, message=message)
