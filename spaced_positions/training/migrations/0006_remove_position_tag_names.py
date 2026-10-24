from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("training", "0005_position_library_data")]
    operations = [migrations.RemoveField(model_name="position", name="tag_names")]
