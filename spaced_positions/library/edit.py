"""Editing the vocabulary, sources and players (spec 04 · Library, 11 §1): `:edit name=value …` on the selection of
the Library's Players, Sources or Tags (or on `@player`, `#tag`, `s12` named first), `:new-tag`, `:new-player`,
`:new-source`, `:delete` for the ones nothing uses, and `:player-link` for names on games that match nobody.

Every change returns its inverse: an edit puts the old values back (`library.edit` with the values per object), a new
object is deleted again, a deleted one comes back with its id."""

from __future__ import annotations

import json
import shlex

from django.db import transaction
from django.db.models import Q
from django.forms.models import model_to_dict

from spaced_positions.core.server_commands import CommandError, command

from .models import Game, Player, Source, Tag, TagField
from .text import fold, slug

MODELS = {"players": Player, "sources": Source, "tags": Tag}

# name in `:edit` → (model field, kind); kinds: text, list (comma-separated), int, float, choice, tag, field
FIELDS = {
    "players": {"name": ("name", "text"), "key": ("key", "slug"), "aliases": ("aliases", "list"), "role": ("role", "choice"),
                "title": ("title", "text"), "federation": ("federation", "text"), "fide": ("fide_id", "text"),
                "born": ("born", "int"), "notes": ("notes", "text")},
    "sources": {"title": ("title", "text"), "short": ("short", "text"), "kind": ("kind", "choice"), "authors": ("authors", "text"),
                "year": ("year", "int"), "publisher": ("publisher", "text"), "isbn": ("isbn", "text"), "url": ("url", "text"),
                "notes": ("notes", "text")},
    "tags": {"name": ("name", "text"), "en": ("name_en", "text"), "aliases": ("aliases", "list"), "parent": ("parent", "tag"),
             "field": ("field", "field"), "difficulty": ("base_difficulty", "int"), "weight": ("weight", "float"),
             "analysis-weight": ("analysis_weight", "float"), "description": ("description", "text"), "task": ("task", "text"),
             "task-en": ("task_en", "text")},
}
RANGES = {"base_difficulty": (1, 5), "weight": (0, 10), "analysis_weight": (0, 10), "born": (1000, 2100), "year": (1000, 2100)}


def _words(args) -> list[str]:
    """The command line sends one text: `name="Tal, Mikhail" role=model` → words, quotes kept together."""
    try:
        return shlex.split(" ".join(args))
    except ValueError as e:
        raise CommandError(f"unbalanced quotes: {e}") from None


def find(collection: str, ref: str):
    """`@tal` a player, `#gabel` (or a tag's name) a tag, `s12` a source."""
    ref = ref.strip()
    if collection == "players":
        found = Player.objects.filter(key=ref.lstrip("@")).first()
    elif collection == "sources":
        found = Source.objects.filter(pk=int(ref[1:])).first() if ref[:1] == "s" and ref[1:].isdigit() else None
    else:
        from .commands import _tag

        found = _tag(ref)
    if found is None:
        raise CommandError(f"no {collection[:-1]} '{ref}'")
    return found


def _targets(body, words: list[str]) -> tuple[str, list, list[str]]:
    """What to edit: refs named before the values (`@tal role=model`), else the Library's selection."""
    refs = [w for w in words if "=" not in w]
    if refs:
        first = refs[0]
        collection = "players" if first.startswith("@") else "sources" if first[:1] == "s" and first[1:].isdigit() else "tags"
        return collection, [find(collection, r) for r in refs], [w for w in words if "=" in w]
    collection = body.get("c", "")
    if collection not in MODELS:
        raise CommandError("select players, sources or tags in the Library (4 5 6), or name one: :edit @tal role=model")
    objs = [find(collection, str(i)) for i in body.get("ids", [])]
    if not objs:
        raise CommandError("nothing selected")
    return collection, objs, words


def _value(collection: str, obj, name: str, raw: str):
    if name not in FIELDS[collection]:
        raise CommandError(f"{collection[:-1]}s have {', '.join(FIELDS[collection])}; not '{name}'")
    attr, kind = FIELDS[collection][name]
    model = type(obj)
    if kind == "text":
        limit = model._meta.get_field(attr).max_length
        return attr, raw[:limit] if limit else raw
    if kind == "slug":
        value = slug(raw)
        if not value or model.objects.filter(key=value).exclude(pk=obj.pk).exists():
            raise CommandError(f"'{raw}' is taken (or empty)")
        return attr, value
    if kind == "list":
        return attr, [a.strip() for a in raw.split(",") if a.strip()]
    if kind in ("int", "float"):
        if raw == "" and model._meta.get_field(attr).null:
            return attr, None
        try:
            value = int(raw) if kind == "int" else float(raw)
        except ValueError:
            raise CommandError(f"{name} is a number") from None
        low, high = RANGES.get(attr, (None, None))
        if low is not None and not low <= value <= high:
            raise CommandError(f"{name} is {low}–{high}")
        return attr, value
    if kind == "choice":
        raw = "" if raw == "none" else raw
        choices = [c for c, _ in model._meta.get_field(attr).choices]
        if raw not in choices:
            shown = ", ".join(c or "none" for c in choices)
            raise CommandError(f"{name} is one of {shown}")
        return attr, raw
    if kind == "tag":
        if raw in ("", "none", "-"):
            return attr, None
        from .commands import _tag

        parent = _tag(raw)
        ancestor = parent
        while ancestor is not None:  # no loops in the hierarchy
            if ancestor.pk == obj.pk:
                raise CommandError(f"{parent.name} is below {obj.name}: that would make a loop")
            ancestor = ancestor.parent
        return attr, parent
    field = TagField.objects.filter(Q(key=raw) | Q(name__iexact=raw) | Q(name_en__iexact=raw)).first()  # kind == "field"
    if field is None:
        raise CommandError(f"no field '{raw}' ({', '.join(TagField.objects.values_list('key', flat=True))})")
    return attr, field


def _stored(obj, attr: str):
    value = getattr(obj, attr)
    return value.pk if hasattr(value, "pk") else value


def _assign(obj, attr: str, value) -> None:
    if attr in ("parent", "field") and not hasattr(value, "pk"):
        setattr(obj, f"{attr}_id", value)
    else:
        setattr(obj, attr, value)


@command("library.edit")
def edit(args, context, body):
    """`:edit role=student`; undo and redo send `{"c": …, "values": {pk: {attr: value}}}` as JSON."""
    if args and str(args[0]).startswith("{"):
        change = json.loads(args[0])
        return _write(change["c"], {int(pk): values for pk, values in change["values"].items()}, "Edit undone")
    words = _words(args)
    collection, objs, pairs = _targets(body, words)
    if not pairs:
        raise CommandError(f"what to change? {', '.join(f'{n}=…' for n in FIELDS[collection])}")
    values = {}
    for obj in objs:
        values[obj.pk] = {}
        for pair in pairs:
            name, _, raw = pair.partition("=")
            attr, value = _value(collection, obj, name.strip().lower(), raw.strip())
            values[obj.pk][attr] = value.pk if hasattr(value, "pk") else value
    names = ", ".join(pair.partition("=")[0] for pair in pairs)
    label = objs[0].name if len(objs) == 1 and hasattr(objs[0], "name") else f"{len(objs)} {collection}" if len(objs) > 1 else str(objs[0])
    return _write(collection, values, f"Changed {names} of {label}")


def _write(collection: str, values: dict, message: str) -> dict:
    Model = MODELS[collection]
    before = {}
    with transaction.atomic():
        for obj in Model.objects.filter(pk__in=values):
            before[obj.pk] = {attr: _stored(obj, attr) for attr in values[obj.pk]}
            for attr, value in values[obj.pk].items():
                _assign(obj, attr, value)
            obj.save()
    if collection == "tags":
        _refresh_tagged(list(values))
    return {
        "message": message,
        "effects": {"library": "changed"},
        "undo": {"command": "library.edit", "args": [json.dumps({"c": collection, "values": before})]},
        "redo": {"command": "library.edit", "args": [json.dumps({"c": collection, "values": values})]},
    }


def _refresh_tagged(tag_ids: list[int]) -> None:
    """A tag's weight or difficulty changed: the automatic difficulty of its positions follows."""
    from spaced_positions.training.models import Position

    from .detect import refresh_difficulty

    for p in Position.objects.filter(tag_links__tag_id__in=tag_ids).distinct():
        refresh_difficulty(p)


# ── New ───────────────────────────────────────────────────────────────────────────────────────────────────────


def _split_new(args) -> tuple[str, list[str]]:
    words = _words(args)
    name = " ".join(w for w in words if "=" not in w).strip()
    if not name:
        raise CommandError("a name first, then any field=value")
    return name, [w for w in words if "=" in w]


def _fill(collection: str, obj, pairs: list[str]) -> None:
    for pair in pairs:
        name, _, raw = pair.partition("=")
        attr, value = _value(collection, obj, name.strip().lower(), raw.strip())
        _assign(obj, attr, value)


def _new_result(collection: str, obj, noun: str) -> dict:
    return {
        "message": f"New {noun}: {obj}",
        "effects": {"library": "changed"},
        "undo": {"command": "library.delete", "args": [json.dumps({"c": collection, "pks": [obj.pk]})]},
        "redo": {"command": "library.recreate", "args": [json.dumps({"c": collection, "objects": [_snapshot(obj)]})]},
    }


@command("tag.new")
def tag_new(args, context, body):
    """`:new-tag Springergabel parent=fork en="Knight fork"`: the key comes from the English name, the field from the
    parent (else field=…, else custom)."""
    name, pairs = _split_new(args)
    tag = Tag(name=name[:100], field=TagField.objects.filter(key="custom").first() or TagField.objects.first())
    _fill("tags", tag, pairs)
    tag.key = slug(tag.name_en or name)  # keys are English, like the starter vocabulary's
    if not tag.key or Tag.objects.filter(key=tag.key).exists():
        raise CommandError(f"there is a tag '{tag.key}' already (#{tag.key})")
    if tag.parent and not any(p.startswith("field=") for p in pairs):
        tag.field = tag.parent.field
    tag.save()
    return _new_result("tags", tag, "tag")


def _make_player(name: str, pairs: list[str]) -> Player:
    key = slug(name.split(",")[0]) or "player"
    base, n = key, 2
    while Player.objects.filter(key=key).exists():
        key, n = f"{base}-{n}", n + 1
    player = Player(key=key, name=name[:150])
    _fill("players", player, pairs)
    player.save()
    return player


@command("player.new")
def player_new(args, context, body):
    """`:new-player "Tal, Mikhail" role=model title=GM`."""
    name, pairs = _split_new(args)
    return _new_result("players", _make_player(name, pairs), "player")


@command("source.new")
def source_new(args, context, body):
    """`:new-source "Polgár: Chess" short="Polgár" year=1994`."""
    title, pairs = _split_new(args)
    source = Source(title=title[:300])
    _fill("sources", source, pairs)
    source.save()
    return _new_result("sources", source, "source")


# ── Delete (only what nothing uses) and recreate (its undo) ───────────────────────────────────────────────────


def _uses(collection: str, obj) -> str:
    if collection == "players":
        n = Game.objects.filter(Q(white=obj) | Q(black=obj)).count()
        return f"{n} game{'s' if n != 1 else ''}" if n else ""
    if collection == "sources":
        n, g = obj.positions.count(), obj.games.count()
        return " and ".join(x for x in [f"{n} position{'s' if n != 1 else ''}" if n else "", f"{g} game{'s' if g != 1 else ''}" if g else ""] if x)
    from .models import GameTag, NodeTag, PositionTag, TagDismissal

    n = sum(M.objects.filter(tag=obj).count() for M in (PositionTag, NodeTag, GameTag, TagDismissal))
    if n:
        return f"{n} position{'s' if n != 1 else ''} or moves"
    if obj.children.exists():
        return f"the tags below it ({', '.join(obj.children.values_list('name', flat=True)[:3])})"
    if obj.presets.exists():
        return "a Collect preset"
    return ""


def _snapshot(obj) -> dict:
    data = model_to_dict(obj, exclude=["search", "presets"])
    data["id"] = obj.pk
    if "created_at" in [f.name for f in obj._meta.fields]:
        data["created_at"] = obj.created_at.isoformat()
    return data


@command("library.delete")
def delete(args, context, body):
    """`:delete` the selected players, sources or tags that nothing uses (used ones are named, not deleted)."""
    if args and str(args[0]).startswith("{"):  # undo of a new one, redo of a delete
        ref = json.loads(args[0])
        collection, objs = ref["c"], list(MODELS[ref["c"]].objects.filter(pk__in=ref["pks"]))
    else:
        collection, objs, pairs = _targets(body, _words(args))
        if pairs:
            raise CommandError(":delete takes no values")
    used = [(o, _uses(collection, o)) for o in objs]
    blocked = [(o, why) for o, why in used if why]
    free = [o for o, why in used if not why]
    if not free:
        o, why = blocked[0]
        raise CommandError(f"{o} is used by {why}: it stays" + (" (:player-link moves games to another player)" if collection == "players" else ""))
    snapshots = [_snapshot(o) for o in free]
    with transaction.atomic():
        MODELS[collection].objects.filter(pk__in=[o.pk for o in free]).delete()
    message = f"Deleted {', '.join(str(o) for o in free)}" + (f" · {len(blocked)} in use stay" if blocked else "")
    change = json.dumps({"c": collection, "objects": snapshots})
    return {
        "message": message,
        "effects": {"library": "changed"},
        "undo": {"command": "library.recreate", "args": [change]},
        "redo": {"command": "library.delete", "args": [json.dumps({"c": collection, "pks": [o["id"] for o in snapshots]})]},
    }


@command("library.recreate")
def recreate(args, context, body):
    try:
        change = json.loads(args[0])
    except (IndexError, ValueError):
        raise CommandError("bad change") from None
    collection = change.get("c")
    if collection not in MODELS:
        raise CommandError("bad change")
    Model = MODELS[collection]
    snapshots = change.get("objects") or []
    with transaction.atomic():
        for data in snapshots:
            data = dict(data)
            pk = data.pop("id")
            for fk in ("parent", "field"):
                if fk in data:
                    data[f"{fk}_id"] = data.pop(fk)
            if Model.objects.filter(pk=pk).exists():
                continue
            obj = Model(pk=pk, **{k: v for k, v in data.items() if k in {f.attname for f in Model._meta.fields} | {"created_at"}})
            obj.save()
    return {
        "message": f"Restored {len(snapshots)} {collection if len(snapshots) != 1 else collection[:-1]}",
        "effects": {"library": "changed"},
        "undo": {"command": "library.delete", "args": [json.dumps({"c": collection, "pks": [o["id"] for o in snapshots]})]},
        "redo": {"command": "library.recreate", "args": [args[0]]},
    }


# ── Linking names on games to a player ────────────────────────────────────────────────────────────────────────


@command("player.link")
def player_link(args, context, body):
    """`:player-link "Tal, M." @tal`: games where that name matches nobody get the player (its aliases learn the
    name). Without `@player` a new player is made from the name."""
    if args and str(args[0]).startswith("{"):
        return _unlink(json.loads(args[0]))
    words = _words(args)
    refs = [w for w in words if w.startswith("@")]
    name = " ".join(w for w in words if not w.startswith("@")).strip()
    if not name:
        raise CommandError('the name as it is on the games: :player-link "Tal, M." @tal')
    folded = fold(name)
    white = [g.pk for g in Game.objects.filter(white__isnull=True).exclude(white_name="") if fold(g.white_name) == folded]
    black = [g.pk for g in Game.objects.filter(black__isnull=True).exclude(black_name="") if fold(g.black_name) == folded]
    if not white and not black:
        raise CommandError(f"no game has '{name}' without a player (is:unlinked in Games lists them)")
    made = False
    player = find("players", refs[0]) if refs else _make_player(name, [])
    made = not refs
    alias_added = False
    if folded not in {fold(player.name), *(fold(a) for a in player.aliases)}:
        player.aliases = [*player.aliases, name]
        player.save()
        alias_added = True
    with transaction.atomic():
        Game.objects.filter(pk__in=white).update(white=player)
        Game.objects.filter(pk__in=black).update(black=player)
    n = len(set(white) | set(black))
    change = {"player": player.pk, "white": white, "black": black, "alias": name if alias_added else None, "made": made}
    return {
        "message": f"{name} → {player.name}: {n} game{'s' if n != 1 else ''}" + (" (new player)" if made else ""),
        "effects": {"library": "changed"},
        "undo": {"command": "player.link", "args": [json.dumps(change)]},
        "redo": {"command": "player.link", "args": [shlex.join([name, *refs])]},
    }


def _unlink(change: dict) -> dict:
    with transaction.atomic():
        Game.objects.filter(pk__in=change["white"]).update(white=None)
        Game.objects.filter(pk__in=change["black"]).update(black=None)
        player = Player.objects.filter(pk=change["player"]).first()
        if player and change.get("made"):
            player.delete()
        elif player and change.get("alias"):
            player.aliases = [a for a in player.aliases if a != change["alias"]]
            player.save()
    return {"message": "Link undone", "effects": {"library": "changed"}}
