from django.contrib.postgres.operations import UnaccentExtension
from django.db import migrations

CREATE_FRENCH_UNACCENT_CONFIG = """
CREATE TEXT SEARCH CONFIGURATION french_unaccent (COPY = french);
ALTER TEXT SEARCH CONFIGURATION french_unaccent
    ALTER MAPPING FOR hword, hword_part, word
    WITH unaccent, french_stem;
"""

DROP_FRENCH_UNACCENT_CONFIG = "DROP TEXT SEARCH CONFIGURATION IF EXISTS french_unaccent;"


def create_french_unaccent_config(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(CREATE_FRENCH_UNACCENT_CONFIG)


def drop_french_unaccent_config(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(DROP_FRENCH_UNACCENT_CONFIG)


class Migration(migrations.Migration):

    dependencies = [
        ("faceted_search", "0003_ignore_modelsearch_fuzzy"),
    ]

    operations = [
        UnaccentExtension(),
        migrations.RunPython(create_french_unaccent_config, drop_french_unaccent_config),
    ]
