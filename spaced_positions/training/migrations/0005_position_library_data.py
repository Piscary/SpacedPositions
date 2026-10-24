"""Positions into the library model (spec 11 §5), additive only: the citation text becomes a Source with page and
reference (the text stays in `source_text`), tag names become tags (names that aren't in the vocabulary become free
tags), the difficulty becomes an override, and side, material and piece count are derived."""

import re

from django.db import migrations

from spaced_positions.library.text import fold, slug

PIECES = "KQRBNP"


def material_of(fen):
    placement = fen.split()[0] if fen else ""
    white = sorted((c for c in placement if c in PIECES), key=PIECES.index)
    black = sorted((c.upper() for c in placement if c in PIECES.lower()), key=PIECES.index)
    return f"{''.join(white)}v{''.join(black)}", len(white) + len(black)


PAGE = re.compile(r"^(?:p\.|S\.|page|Seite)\s*(?P<page>.+)$", re.I)


def forward(apps, schema_editor):
    Position = apps.get_model("training", "Position")
    Source = apps.get_model("library", "Source")
    Tag = apps.get_model("library", "Tag")
    TagField = apps.get_model("library", "TagField")
    PositionTag = apps.get_model("library", "PositionTag")

    names = {}
    for tag in Tag.objects.all():
        for name in [tag.name, tag.name_en, *tag.aliases]:
            names.setdefault(fold(name), tag)
    custom = TagField.objects.filter(key="custom").first()
    sources = {}
    for p in Position.objects.all():
        stem, _, rest = p.source_text.partition(" · ")
        if stem.strip():
            source = sources.get(stem)
            if source is None:
                source = Source.objects.filter(title=stem).first() or Source.objects.create(title=stem, search=fold(stem))
                sources[stem] = source
            p.source = source
            refs = []
            for part in (x.strip() for x in rest.split(" · ") if x.strip()):
                m = PAGE.match(part)
                if m and not p.source_page:
                    p.source_page = m.group("page")[:40]
                else:
                    refs.append(part)
            p.source_ref = " · ".join(refs)[:300]
        parts = p.fen.split()
        p.side = parts[1] if len(parts) > 1 and parts[1] in "wb" else "w"
        p.material, p.pieces = material_of(p.fen)
        p.difficulty_override = p.difficulty
        p.save()
        for name in p.tag_names or []:
            tag = names.get(fold(name))
            if tag is None and custom is not None:
                key, n = slug(name) or "tag", 2
                while Tag.objects.filter(key=key).exists():
                    key, n = f"{slug(name)}-{n}", n + 1
                tag = Tag.objects.create(field=custom, key=key, name=name[:100], search=fold(name))
                names[fold(name)] = tag
            if tag is not None:
                PositionTag.objects.get_or_create(position=p, tag=tag)


class Migration(migrations.Migration):
    dependencies = [("training", "0004_position_library"), ("library", "0002_vocabulary")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
