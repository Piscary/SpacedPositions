"""The starter tag vocabulary (decision 18)."""

from django.db import migrations


def load(apps, schema_editor):
    from spaced_positions.library import vocabulary

    vocabulary.load(apps.get_model("library", "TagField"), apps.get_model("library", "Tag"))


class Migration(migrations.Migration):
    dependencies = [("library", "0001_initial")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
