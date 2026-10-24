"""The starter tag vocabulary (decision 18): the old app's fields and tags, from data/tags.json. Loading is
idempotent: fields and tags that exist (by key) are left as the user has them."""

import json
from pathlib import Path

from .text import fold

DATA = Path(__file__).parent / "data" / "tags.json"


def load(TagField, Tag) -> int:
    """Create the missing fields and tags; works with the real models and with migration models. Returns the
    number of tags created."""
    data = json.loads(DATA.read_text())
    fields = {}
    for order, f in enumerate(data["fields"]):
        fields[f["key"]], _ = TagField.objects.get_or_create(
            key=f["key"],
            defaults={k: f[k] for k in ("name", "name_en", "selection", "on_positions", "on_moves", "color", "description")} | {"order": order},
        )
    created, by_key = 0, {t.key: t for t in Tag.objects.all()}
    has_weights = "weight" in {f.name for f in Tag._meta.get_fields()}  # migration 0002 runs before 0003 adds them
    order = {}
    for t in data["tags"]:
        if t["key"] in by_key:
            continue
        order[t["field"]] = order.get(t["field"], 0) + 1
        weights = {"weight": t.get("weight", 1.0), "analysis_weight": t.get("analysis_weight", 0.0)} if has_weights else {}
        tag = Tag(
            field=fields[t["field"]], key=t["key"], name=t["name"], name_en=t["name_en"], aliases=t["aliases"],
            description=t["description"], task=t["task"], task_en=t["task_en"], base_difficulty=t["base_difficulty"],
            order=order[t["field"]], **weights,
        )
        tag.search = " | ".join(fold(x) for x in [tag.key, tag.name, tag.name_en, *tag.aliases] if x)  # migration models have no save()
        tag.save()
        by_key[tag.key] = tag
        created += 1
    for t in data["tags"]:
        if t["parent"] and by_key[t["key"]].parent_id is None and t["parent"] in by_key:
            Tag.objects.filter(pk=by_key[t["key"]].pk).update(parent=by_key[t["parent"]])
    return created
