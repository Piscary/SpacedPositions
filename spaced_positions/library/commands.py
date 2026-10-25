"""Bulk commands of the Library (spec 04 · Library, 11): tag, untag, trash, restore, empty the trash, save a query.

The client sends what they act on (`c` collection, `ids` short ids of the selection, else `q` the query) and pushes
the inverse the server returns onto its undo stack. Tag changes are undone through `library.relink`, which puts back
exactly the links a change added or removed, so undo never touches tags set before."""

import json

from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from spaced_positions.core.server_commands import CommandError, command
from spaced_positions.training.models import Attempt, Position

from .models import Game, GameTag, NodeTag, PositionTag, SavedQuery, Tag, TagDismissal
from .text import fold, slug
from .views import objects

LINKS = {"positions": (PositionTag, "position_id"), "games": (GameTag, "game_id"), "nodes": (NodeTag, "node_id")}


def _targets(body) -> tuple[str, list[int]]:
    collection = body.get("c", "positions")
    if collection == "nodes":  # move tags (Analyse `t`)
        return "nodes", [int(str(i)[1:]) for i in body.get("ids", []) if str(i)[1:].isdigit()]
    if collection == "puzzles":
        found = objects("puzzles", body.get("ids", []), body.get("q", ""))
        return "positions", list(found.values_list("position_id", flat=True).distinct())
    if collection not in LINKS:
        raise CommandError(_("{collection} can't be tagged").format(collection=collection))
    found = objects(collection, body.get("ids", []), body.get("q", ""))
    return collection, list(found.values_list("pk", flat=True))


def _tag(value: str) -> Tag:
    v = fold(value.lstrip("#"))
    tag = Tag.objects.filter(key=v).first()
    if tag is None:
        tag = next((t for t in Tag.objects.all() if v in t.search.split(" | ")), None)
    if tag is None:
        raise CommandError(_("no tag '{tag}' (the Library's Tags, 6, lists them all)").format(tag=value))
    return tag


def _apply(change: dict) -> dict:
    """Apply {"c", "add": [[id, tag, origin]], "remove": [[id, tag, origin]]}; returns the inverse. A tag the user
    takes away is remembered (detection won't add it again); one the user adds again is no longer dismissed."""
    Link, owner = LINKS[change["c"]]
    dismissal = {"positions": "position_id", "nodes": "node_id"}.get(change["c"])
    with transaction.atomic():
        for obj, tag, _origin in change.get("remove", []):
            Link.objects.filter(**{owner: obj, "tag_id": tag}).delete()
            if dismissal and not change.get("quiet"):
                TagDismissal.objects.get_or_create(**{dismissal: obj, "tag_id": tag})
        for obj, tag, origin in change.get("add", []):
            Link.objects.update_or_create(**{owner: obj, "tag_id": tag}, defaults={"origin": origin})
            if dismissal:
                TagDismissal.objects.filter(**{dismissal: obj, "tag_id": tag}).delete()
    _refresh_difficulty(change)
    # the inverse is an undo: taking a tag away again is not the user dismissing it
    return {"c": change["c"], "add": change.get("remove", []), "remove": change.get("add", []), "quiet": True}


def _refresh_difficulty(change: dict) -> None:
    from .detect import refresh_difficulty

    ids = {row[0] for row in change.get("add", []) + change.get("remove", [])}
    if change["c"] == "positions":
        positions = Position.objects.filter(pk__in=ids)
    elif change["c"] == "nodes":
        positions = Position.objects.filter(nodes__in=ids).distinct()
    else:
        return
    for p in positions:
        refresh_difficulty(p)


def _relink_result(message: str, change: dict) -> dict:
    inverse = _apply(change)
    return {
        "message": message,
        "effects": {"library": "changed"},
        "undo": {"command": "library.relink", "args": [json.dumps(inverse)]},
        "redo": {"command": "library.relink", "args": [json.dumps(change)]},
    }


@command("library.tag")
def tag(args, context, body):
    if not args:
        raise CommandError(_("which tag? e.g. :tag fork"))
    t = _tag(args[0])
    collection, ids = _targets(body)
    if not ids:
        raise CommandError(_("nothing selected"))
    Link, owner = LINKS[collection]
    have = set(Link.objects.filter(**{f"{owner}__in": ids, "tag": t}).exclude(origin="suggested").values_list(owner, flat=True))
    change = {"c": collection, "add": [[i, t.id, "manual"] for i in ids if i not in have], "remove": []}
    # a suggestion that is confirmed becomes a manual tag (added again as manual: update_or_create in _apply)
    change["add"] += [[i, t.id, "manual"] for i in Link.objects.filter(**{f"{owner}__in": ids, "tag": t, "origin": "suggested"}).values_list(owner, flat=True)]
    if t.field.selection == "single":  # one tag of this field per object: the others go
        change["remove"] += [[getattr(link, owner), link.tag_id, link.origin]
                             for link in Link.objects.filter(**{f"{owner}__in": ids, "tag__field": t.field}).exclude(tag=t)]
    added = len(change["add"])
    return _relink_result(ngettext("Tagged {n} item {tag}", "Tagged {n} items {tag}", added).format(n=added, tag=t.label)
                          + (" " + _("({n} had it)").format(n=len(have)) if have else ""), change)


@command("library.untag")
def untag(args, context, body):
    if not args:
        raise CommandError(_("which tag? e.g. :untag fork"))
    t = _tag(args[0])
    collection, ids = _targets(body)
    Link, owner = LINKS[collection]
    links = Link.objects.filter(**{f"{owner}__in": ids, "tag": t})
    change = {"c": collection, "add": [], "remove": [[getattr(link, owner), link.tag_id, link.origin] for link in links]}
    n = len(change["remove"])
    return _relink_result(ngettext("Removed {tag} from {n} item", "Removed {tag} from {n} items", n).format(n=n, tag=t.label), change)


@command("library.relink")
def relink(args, context, body):
    try:
        change = json.loads(args[0])
    except (IndexError, ValueError):
        raise CommandError(_("bad change")) from None
    if change.get("c") not in LINKS:
        raise CommandError(_("bad change"))
    return _relink_result(_("Tags restored"), change)


def _ids_arg(args, body):
    """Ids from the first argument (undo, redo) or from the selection in the body."""
    if args and args[0]:
        return body.get("c", args[1] if len(args) > 1 else "positions"), [i for i in args[0].split(",") if i]
    return body.get("c", "positions"), body.get("ids", [])


@command("library.trash")
def trash(args, context, body):
    collection, ids = _ids_arg(args, body)
    if collection not in ("positions", "games"):
        raise CommandError(_("only positions and games go to the trash"))
    found = objects(collection, ids, body.get("q", "") if not ids else "").filter(deleted_at=None)
    short = [f"{'p' if collection == 'positions' else 'g'}{pk}" for pk in found.values_list("pk", flat=True)]
    n = found.update(deleted_at=timezone.now())
    return {
        "message": _("Moved {n} to the trash · is:trash shows it").format(n=n),
        "effects": {"library": "changed"},
        "undo": {"command": "library.restore", "args": [",".join(short), collection]},
        "redo": {"command": "library.trash", "args": [",".join(short), collection]},
    }


@command("library.restore")
def restore(args, context, body):
    collection, ids = _ids_arg(args, body)
    if collection not in ("positions", "games"):
        raise CommandError(_("only positions and games are in the trash"))
    found = objects(collection, ids, body.get("q", "") if not ids else "").exclude(deleted_at=None)
    short = [f"{'p' if collection == 'positions' else 'g'}{pk}" for pk in found.values_list("pk", flat=True)]
    n = found.update(deleted_at=None)
    return {
        "message": _("Restored {n} from the trash").format(n=n),
        "effects": {"library": "changed"},
        "undo": {"command": "library.trash", "args": [",".join(short), collection]},
        "redo": {"command": "library.restore", "args": [",".join(short), collection]},
    }


@command("library.emptytrash")
def empty_trash(args, context, body):
    """The only permanent delete (decision 19). Positions with training history stay: attempts are never deleted."""
    trained = Attempt.objects.filter(card__puzzle__position=OuterRef("pk"))
    positions = Position.objects.exclude(deleted_at=None)
    kept = positions.filter(Exists(trained)).count()
    gone = positions.exclude(Exists(trained))
    n_positions, n_games = gone.count(), Game.objects.exclude(deleted_at=None).count()
    with transaction.atomic():
        gone.delete()
        Game.objects.exclude(deleted_at=None).delete()
    message = _("Trash emptied: {positions} positions and {games} games deleted for good").format(positions=n_positions, games=n_games)
    if kept:
        message += "; " + _("{n} with training history stay in the trash").format(n=kept)
    return {"message": message, "effects": {"library": "changed"}}


@command("library.savequery")
def save_query(args, context, body):
    name = " ".join(args).strip()
    if not name:
        raise CommandError(_("a name, e.g. :save-query hard forks"))
    text = str(body.get("q", "")).strip()
    if not text:
        raise CommandError(_("the query is empty"))
    key = slug(name) or "query"
    SavedQuery.objects.update_or_create(
        key=key, defaults={"name": name, "query": text, "collection": body.get("c", "positions")}
    )
    return {"message": _("Saved as q:{key} · use it with in:q:{key} or in a training session").format(key=key), "effects": {"library": "saved"}}



@command("library.trashmany")
def trash_many(args, context, body):
    """Undo and redo of an import: what it added goes to the trash, or comes back."""
    try:
        change = json.loads(args[0])
    except (IndexError, ValueError):
        raise CommandError(_("bad change")) from None
    restore = bool(change.get("restore"))
    stamp = None if restore else timezone.now()
    n = 0
    for collection, model in (("games", Game), ("positions", Position)):
        pks = [int(i[1:]) for i in change.get(collection, []) if str(i)[1:].isdigit()]
        n += model.objects.filter(pk__in=pks).update(deleted_at=stamp)
    inverse = change | {"restore": not restore}
    return {
        "message": (_("Restored: {n} imported") if restore else _("Moved to the trash: {n} imported")).format(n=n),
        "effects": {"library": "changed"},
        "undo": {"command": "library.trashmany", "args": [json.dumps(inverse)]},
        "redo": {"command": "library.trashmany", "args": [json.dumps(change)]},
    }


@command("library.detect")
def detect_tags(args, context, body):
    """`:detect`: python-chess detection (library/detect.py) on the selection, the query, or the open position."""
    from .detect import run

    collection, ids = _targets(body)
    if collection != "positions":
        raise CommandError(_("detection works on positions"))
    added = suggested = moves = 0
    for position in Position.objects.filter(pk__in=ids[:2000]):
        result = run(position, search=len(ids) <= 50)
        added, suggested, moves = added + len(result["added"]), suggested + len(result["suggested"]), moves + result["moves"]
    n = len(ids)
    return {
        "message": ngettext("Detected on {n} position: {added} tags, {suggested} suggestions, {moves} move tags",
                            "Detected on {n} positions: {added} tags, {suggested} suggestions, {moves} move tags", n).format(
                                n=n, added=added, suggested=suggested, moves=moves),
        "effects": {"library": "changed"},
    }
