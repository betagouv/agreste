from django.core.management import call_command
from django.db import migrations


def enable_fuzzy_extensions(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    call_command("enable_unaccent", verbosity=0)
    call_command("enable_trigram", verbosity=0)


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("wagtailsearch", "0010_add_text_fields"),
    ]

    operations = [
        migrations.RunPython(enable_fuzzy_extensions, migrations.RunPython.noop),
    ]
