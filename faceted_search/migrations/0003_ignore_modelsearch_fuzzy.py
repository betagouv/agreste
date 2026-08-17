from django.db import migrations


class Migration(migrations.Migration):
    initial = True  # it replaces the app's initial migration

    dependencies = [
        ("wagtailsearch", "0010_add_text_fields"),
    ]

    operations = []

    replaces = [
        ("faceted_search", "0001_enable_modelsearch_fuzzy"),
        ("faceted_search", "0002_disable_modelsearch_fuzzy"),
    ]
