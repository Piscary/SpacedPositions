"""Bulk commands of the Library (spec 04 · Library, 11): tag, untag, trash, restore, empty the trash, save a query.

The client sends what they act on (`c` collection, `ids` short ids of the selection, else `q` the query) and pushes
the inverse the server returns onto its undo stack. Tag changes are undone through `library.relink`, which puts back
exactly the links a change added or removed, so undo never touches tags set before."""

import json

from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from spaced_positions.core.server_commands import CommandError, command
from spaced_positions.training.models import Attempt, Position

from .models import Game, GameTag, NodeTag, PositionTag, SavedQuery, Tag
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
        raise CommandError(f"{collection} can't be tagged")
    found = objects(collection, body.get("ids", []), body.get("q", ""))
    return collection, list(found.values_list("pk", flat=True))


def _tag(value: str) -> Tag:
    v = fold(value.lstrip("#"))
    tag = Tag.objects.filter(key=v).first()
    if tag is None:
        tag = next((t for t in Tag.objects.all() if v in t.search.split(" | ")), None)
    if tag is None:
        raise CommandError(f"no tag '{value}' (the Library's Tags, 6, lists them all)")
    return tag


def _apply(change: dict) -> dict:
    """Apply {"c", "add": [[id, tag, origin]], "remove": [[id, tag, origin]]}; returns the inverse."""
    Link, owner = LINKS[change["c"]]
    with transaction.atomic():
        for obj, tag, _origin in change.get("remove", []):
            Link.objects.filter(**{owner: obj, "tag_id": tag}).delete()
        for obj, tag, origin in change.get("add", []):
            Link.objects.get_or_create(**{owner: obj, "tag_id": tag}, defaults={"origin": origin})
    return {"c": change["c"], "add": change.get("remove", []), "remove": change.get("add", [])}


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
        raise CommandError("which tag? e.g. :tag gabel")
    t = _tag(args[0])
    collection, ids = _targets(body)
    if not ids:
        raise CommandError("nothing selected")
    Link, owner = LINKS[collection]
    have = set(Link.objects.filter(**{f"{owner}__in": ids, "tag": t}).exclude(origin="suggested").values_list(owner, flat=True))
    change = {"c": collection, "add": [[i, t.id, "manual"] for i in ids if i not in have], "remove": []}
    # a suggestion that is confirmed becomes a manual tag
    change["remove"] += [[i, t.id, "suggested"] for i in Link.objects.filter(**{f"{owner}__in": ids, "tag": t, "origin": "suggested"}).values_list(owner, flat=True)]
    if t.field.selection == "single":  # one tag of this field per object: the others go
        change["remove"] += [[getattr(link, owner), link.tag_id, link.origin]
                             for link in Link.objects.filter(**{f"{owner}__in": ids, "tag__field": t.field}).exclude(tag=t)]
    added = len(change["add"])
    return _relink_result(f"Tagged {added} {'item' if added == 1 else 'items'} {t.name}" + (f" ({len(have)} had it)" if have else ""), change)


@command("library.untag")
def untag(args, context, body):
    if not args:
        raise CommandError("which tag? e.g. :untag gabel")
    t = _tag(args[0])
    collection, ids = _targets(body)
    Link, owner = LINKS[collection]
    links = Link.objects.filter(**{f"{owner}__in": ids, "tag": t})
    change = {"c": collection, "add": [], "remove": [[getattr(link, owner), link.tag_id, link.origin] for link in links]}
    n = len(change["remove"])
    return _relink_result(f"Removed {t.name} from {n} {'item' if n == 1 else 'items'}", change)


@command("library.relink")
def relink(args, context, body):
    try:
        change = json.loads(args[0])
    except (IndexError, ValueError):
        raise CommandError("bad change") from None
    if change.get("c") not in LINKS:
        raise CommandError("bad change")
    return _relink_result("Tags restored", change)


def _ids_arg(args, body):
    """Ids from the first argument (undo, redo) or from the selection in the body."""
    if args and args[0]:
        return body.get("c", args[1] if len(args) > 1 else "positions"), [i for i in args[0].split(",") if i]
    return body.get("c", "positions"), body.get("ids", [])


@command("library.trash")
def trash(args, context, body):
    collection, ids = _ids_arg(args, body)
    if collection not in ("positions", "games"):
        raise CommandError("only positions and games go to the trash")
    found = objects(collection, ids, body.get("q", "") if not ids else "").filter(deleted_at=None)
    short = [f"{'p' if collection == 'positions' else 'g'}{pk}" for pk in found.values_list("pk", flat=True)]
    n = found.update(deleted_at=timezone.now())
    return {
        "message": f"Moved {n} to the trash · is:trash shows it",
        "effects": {"library": "changed"},
        "undo": {"command": "library.restore", "args": [",".join(short), collection]},
        "redo": {"command": "library.trash", "args": [",".join(short), collection]},
    }


@command("library.restore")
def restore(args, context, body):
    collection, ids = _ids_arg(args, body)
    if collection not in ("positions", "games"):
        raise CommandError("only positions and games are in the trash")
    found = objects(collection, ids, body.get("q", "") if not ids else "").exclude(deleted_at=None)
    short = [f"{'p' if collection == 'positions' else 'g'}{pk}" for pk in found.values_list("pk", flat=True)]
    n = found.update(deleted_at=None)
    return {
        "message": f"Restored {n} from the trash",
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
    message = f"Trash emptied: {n_positions} positions and {n_games} games deleted for good"
    if kept:
        message += f"; {kept} with training history stay in the trash"
    return {"message": message, "effects": {"library": "changed"}}


@command("library.savequery")
def save_query(args, context, body):
    name = " ".join(args).strip()
    if not name:
        raise CommandError("a name, e.g. :save-query hard forks")
    text = str(body.get("q", "")).strip()
    if not text:
        raise CommandError("the query is empty")
    key = slug(name) or "query"
    SavedQuery.objects.update_or_create(
        key=key, defaults={"name": name, "query": text, "collection": body.get("c", "positions")}
    )
    return {"message": f"Saved as q:{key} · use it with in:q:{key} or in a training session", "effects": {"library": "saved"}}



@command("library.trashmany")
def trash_many(args, context, body):
    """Undo and redo of an import: what it added goes to the trash, or comes back."""
    try:
        change = json.loads(args[0])
    except (IndexError, ValueError):
        raise CommandError("bad change") from None
    restore = bool(change.get("restore"))
    stamp = None if restore else timezone.now()
    n = 0
    for collection, model in (("games", Game), ("positions", Position)):
        pks = [int(i[1:]) for i in change.get(collection, []) if str(i)[1:].isdigit()]
        n += model.objects.filter(pk__in=pks).update(deleted_at=stamp)
    inverse = change | {"restore": not restore}
    return {
        "message": f"{'Restored' if restore else 'Moved to the trash'}: {n} imported",
        "effects": {"library": "changed"},
        "undo": {"command": "library.trashmany", "args": [json.dumps(inverse)]},
        "redo": {"command": "library.trashmany", "args": [json.dumps(change)]},
    }
