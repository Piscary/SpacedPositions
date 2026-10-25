"""The difficulty weights of the starter tags (decision 18)."""

import json

from django.db import migrations

from spaced_positions.library.vocabulary import DATA


def forward(apps, schema_editor):
    Tag = apps.get_model("library", "Tag")
    for t in json.loads(DATA.read_text())["tags"]:
        Tag.objects.filter(key=t["key"]).update(weight=t.get("weight", 1.0), analysis_weight=t.get("analysis_weight", 0.0))


class Migration(migrations.Migration):
    dependencies = [("library", "0003_tag_weights")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
