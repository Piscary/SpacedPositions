"""Collect (spec 04 · Collect, 11 §2): saving positions entered from a book, diagram after diagram. A save creates
the position with its source, page, diagram number, tags and (when the solution was played) its analysis and a
puzzle; a duplicate is merged into the existing position only when asked."""

import json

from django.db import transaction
from django.http import JsonResponse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from spaced_positions import chesslogic
from spaced_positions.analysis import puzzles as analysis_puzzles
from spaced_positions.analysis import tree
from spaced_positions.training.models import Position

from .detect import run as run_detection
from .models import PositionTag, Source, Tag, TagPreset


def _body(request) -> dict:
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def duplicate_of(canonical: str):
    if not canonical:
        return None
    return Position.alive.filter(canonical=canonical).order_by("id").first()


def describe(p) -> dict:
    return {"id": str(p.uuid), "short": p.short_id, "title": p.title}


def _tags(keys) -> list[Tag]:
    return list(Tag.objects.filter(key__in=[str(k) for k in keys or []]))


def _make_puzzle(position, ready: bool) -> str:
    root = tree.root(position)
    if not root.kids.exists():
        return ""
    if not position.puzzles.filter(start_node=root).exists():
        analysis_puzzles.act(root, "start")
    if ready:
        position.puzzles.filter(start_node=root).update(active=True)
    analysis_puzzles.rebuild_all(position)
    return " · " + (_("puzzle in training") if ready else _("puzzle as a draft"))


@require_POST
def save(request):
    data = _body(request)
    start = str(data.get("start", ""))
    moves = [str(u) for u in data.get("moves", [])][:200]
    diagram = bool(data.get("diagram"))
    check = chesslogic.check_fen(start, diagram=diagram)
    if not check.get("readable", check.get("ok")):
        return JsonResponse({"ok": False, "message": _("not a position")}, status=422)
    if not check["ok"] and not diagram:
        return JsonResponse({"ok": False, "message": _("not legal: {problems} (D keeps it as a diagram)").format(problems="; ".join(p["message"] for p in check["problems"]))}, status=422)
    canonical = check.get("canonical") or chesslogic.canonical_fen(start)
    existing = duplicate_of(canonical)
    how = data.get("how")  # None: ask on a duplicate · "merge" · "new"
    if existing and how not in ("merge", "new"):
        # not an error: a question for the user (merge, save anyway, cancel)
        return JsonResponse({"ok": False, "duplicate": describe(existing), "message": _("duplicate of {id} {title}").format(id=existing.short_id, title=existing.title)})
    source = Source.objects.filter(pk=data.get("source")).first() if data.get("source") else None
    tags = _tags(data.get("tags"))
    with transaction.atomic():
        if existing and how == "merge":
            position = existing
            with tree.change(position, _("Collect: merge")):
                if moves:
                    tree.add_line(tree.root(position), moves)
            if source and not position.source_id:
                position.source, position.source_page, position.source_ref = source, str(data.get("page", ""))[:40], str(data.get("ref", ""))[:300]
                position.save()
            message = _("Merged into {id}").format(id=position.short_id)
        else:
            fen = check.get("fen") or start
            if diagram and not check["ok"]:
                position = Position.objects.create(fen=fen, canonical=canonical, diagram=True, origin="collect")
            else:
                position = tree.create_position(fen, moves, title="", origin="collect")
            position.title = str(data.get("title", ""))[:200]
            position.source = source
            position.source_page = str(data.get("page", ""))[:40]
            position.source_ref = str(data.get("ref", ""))[:300]
            position.diagram = diagram
            position.save()
            message = _("Saved {id}").format(id=position.short_id)
        for tag in tags:
            if tag.field.selection == "single":
                position.tag_links.filter(tag__field=tag.field).exclude(tag=tag).delete()
            PositionTag.objects.get_or_create(position=position, tag=tag)
        if not position.diagram:
            message += _make_puzzle(position, bool(data.get("ready")))
            detected = run_detection(position)  # tags from python-chess (library/detect.py), suggestions dashed
            if detected["added"] or detected["suggested"]:
                message += f" · detected {', '.join(detected['added'] + detected['suggested'])}"
    return JsonResponse({"ok": True, "position": describe(position), "message": message})


@require_POST
def save_many(request):
    """Pasted FEN lists (paste → c): each FEN a position with the entry session's source and tags; duplicates skipped."""
    data = _body(request)
    source = Source.objects.filter(pk=data.get("source")).first() if data.get("source") else None
    tags = _tags(data.get("tags"))
    saved, skipped, bad = [], 0, 0
    with transaction.atomic():
        for fen in [str(f) for f in data.get("fens", [])][:2000]:
            check = chesslogic.check_fen(fen)
            if not check["ok"]:
                bad += 1
                continue
            if duplicate_of(check["canonical"]):
                skipped += 1
                continue
            position = Position.objects.create(fen=check["fen"], canonical=check["canonical"], source=source, origin="collect")
            tree.root(position)
            run_detection(position, search=False)
            for tag in tags:
                PositionTag.objects.get_or_create(position=position, tag=tag)
            saved.append(position)
    parts = [ngettext("Saved {n} position", "Saved {n} positions", len(saved)).format(n=len(saved))]
    if skipped:
        parts.append(_("{n} already in the library").format(n=skipped))
    if bad:
        parts.append(_("{n} not legal").format(n=bad))
    return JsonResponse({"ok": True, "message": " · ".join(parts), "positions": [describe(p) for p in saved[-20:]]})


@require_POST
def new_source(request):
    data = _body(request)
    title = str(data.get("title", "")).strip()[:300]
    if not title:
        return JsonResponse({"ok": False, "message": _("a title")}, status=422)
    kind = data.get("kind") if data.get("kind") in Source.Kind.values else Source.Kind.BOOK
    source = Source.objects.filter(title=title).first() or Source.objects.create(title=title, kind=kind)
    return JsonResponse({"ok": True, "id": source.pk, "label": source.label})


@require_POST
def save_preset(request):
    """`:preset-save <name>`: the entry session's tags as a preset (1–9 in the entry session)."""
    data = _body(request)
    name = str(data.get("name", "")).strip()[:80]
    tags = _tags(data.get("tags"))
    if not name or not tags:
        return JsonResponse({"ok": False, "message": _("a name and at least one tag in the session")}, status=422)
    preset = TagPreset.objects.filter(name=name).first() or TagPreset.objects.create(name=name, order=TagPreset.objects.count())
    preset.tags.set(tags)
    return JsonResponse({"ok": True, "message": f"Preset {name}: {', '.join(t.name for t in tags)}", "presets": presets()})


def presets() -> list[dict]:
    return [
        {"name": p.name, "tags": [{"key": t.key, "name": t.label} for t in p.tags.all()],
         "keys": ",".join(t.key for t in p.tags.all()), "names": "|".join(t.label for t in p.tags.all())}
        for p in TagPreset.objects.prefetch_related("tags")[:9]
    ]
