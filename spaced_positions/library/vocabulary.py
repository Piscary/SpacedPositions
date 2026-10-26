"""The starter tag vocabulary (decision 18): fields and tags from data/tags.json, named in German (the base name),
English, French and Italian. Loading is idempotent: fields and tags that exist (by key) are left as the user has them."""

import json
from pathlib import Path

from .text import fold

DATA = Path(__file__).parent / "data" / "tags.json"
NAMES = ("name", "name_en", "name_fr", "name_it")
TASKS = ("task", "task_en", "task_fr", "task_it")


def search_of(tag) -> str:
    return " | ".join(fold(x) for x in [tag.key, *(getattr(tag, n, "") for n in NAMES), *tag.aliases] if x)


def _known(model, values: dict) -> dict:
    """Only the fields the model has (migrations load the vocabulary into earlier versions of the models)."""
    names = {f.name for f in model._meta.get_fields()}
    return {k: v for k, v in values.items() if k in names}


def load(TagField, Tag) -> int:
    """Create the missing fields and tags; works with the real models and with migration models. Returns the
    number of tags created."""
    data = json.loads(DATA.read_text(encoding="utf-8"))
    fields = {}
    for order, f in enumerate(data["fields"]):
        fields[f["key"]], _ = TagField.objects.get_or_create(
            key=f["key"],
            defaults=_known(TagField, {k: f.get(k, "") for k in (*NAMES, "selection", "on_positions", "on_moves", "color", "description")})
            | {"order": order},
        )
    created, by_key = 0, {t.key: t for t in Tag.objects.all()}
    order = {}
    for t in data["tags"]:
        if t["key"] in by_key:
            continue
        order[t["field"]] = order.get(t["field"], 0) + 1
        tag = Tag(field=fields[t["field"]], key=t["key"], order=order[t["field"]], **_known(Tag, {
            **{k: t.get(k, "") for k in (*NAMES, *TASKS, "description")}, "aliases": t["aliases"], "base_difficulty": t["base_difficulty"],
            "weight": t.get("weight", 1.0), "analysis_weight": t.get("analysis_weight", 0.0),
        }))
        tag.search = search_of(tag)  # migration models have no save()
        tag.save()
        by_key[tag.key] = tag
        created += 1
    for t in data["tags"]:
        if t["parent"] and by_key[t["key"]].parent_id is None and t["parent"] in by_key:
            Tag.objects.filter(pk=by_key[t["key"]].pk).update(parent=by_key[t["parent"]])
    return created


def translate(TagField, Tag) -> int:
    """Fill the French and Italian names of the built-in fields and tags where they are empty, and write the German
    names the Swiss way (ss, not ß) where the user hasn't renamed them. Returns the number of tags changed."""
    data = json.loads(DATA.read_text(encoding="utf-8"))
    for f in data["fields"]:
        for field in TagField.objects.filter(key=f["key"]):
            for k in ("name_fr", "name_it"):
                if not getattr(field, k):
                    setattr(field, k, f[k])
            if field.name.replace("ß", "ss") == f["name"]:
                field.name = f["name"]
            field.save()
    changed = 0
    for t in data["tags"]:
        tag = Tag.objects.filter(key=t["key"]).first()
        if tag is None:
            continue
        for k in ("name_fr", "name_it", "task_fr", "task_it"):
            if not getattr(tag, k):
                setattr(tag, k, t[k])
        if tag.name != t["name"] and tag.name.replace("ß", "ss") == t["name"]:
            if tag.name not in tag.aliases:
                tag.aliases = [*tag.aliases, tag.name]
            tag.name = t["name"]
        if tag.task and tag.task.replace("ß", "ss") == t["task"]:
            tag.task = t["task"]
        tag.search = search_of(tag)
        tag.save()
        changed += 1
    return changed
