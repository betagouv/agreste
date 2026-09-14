from django.db import migrations


def disable_fuzzy_extensions(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP INDEX IF EXISTS modelsearch_title_text_trgm;")
        cursor.execute("DROP INDEX IF EXISTS modelsearch_body_text_trgm;")
        cursor.execute("DROP INDEX IF EXISTS modelsearch_title_text_unaccent_trgm;")
        cursor.execute("DROP INDEX IF EXISTS modelsearch_body_text_unaccent_trgm;")
        cursor.execute("DROP FUNCTION IF EXISTS f_unaccent(text);")
        cursor.execute("DROP EXTENSION IF EXISTS pg_trgm;")
        cursor.execute("DROP EXTENSION IF EXISTS unaccent;")


class Migration(migrations.Migration):

    dependencies = [
        ("faceted_search", "0001_enable_modelsearch_fuzzy"),
    ]

    operations = [
        migrations.RunPython(disable_fuzzy_extensions, migrations.RunPython.noop),
    ]
