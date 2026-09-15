# Generated manually for PublicationPage.disaron_id

from django.db import migrations, models

from publications.migrations.data_migrations.extract_disaron_id import (
    extract_disaron_id_from_stream_data,
)


def backfill_disaron_ids(apps, schema_editor):
    PublicationPage = apps.get_model("publications", "PublicationPage")
    BlogEntryPage = apps.get_model("sites_conformes_blog", "BlogEntryPage")

    # body/hero live on BlogEntryPage (SitesFacilesBasePage is abstract); historical
    # PublicationPage MTI models do not expose those parent columns.
    entries_by_pk = {
        entry.pk: entry
        for entry in BlogEntryPage.objects.filter(
            pk__in=PublicationPage.objects.values_list("pk", flat=True)
        ).only("pk", "body", "hero")
    }

    for page in PublicationPage.objects.all().iterator():
        entry = entries_by_pk.get(page.pk)
        body = entry.body if entry is not None else None
        hero = entry.hero if entry is not None else None
        extracted = extract_disaron_id_from_stream_data(body, hero)
        page.disaron_id = extracted if extracted else f"pending-{page.pk}"
        page.save(update_fields=["disaron_id"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("publications", "0003_alter_collection_colophon_alter_theme_colophon"),
    ]

    operations = [
        migrations.AddField(
            model_name="publicationpage",
            name="disaron_id",
            field=models.CharField(
                blank=True,
                help_text="The identifier of the publication in the old Agreste website",
                max_length=255,
                null=True,
                verbose_name="Disaron identifier",
            ),
        ),
        migrations.RunPython(backfill_disaron_ids, noop_reverse),
        migrations.AlterField(
            model_name="publicationpage",
            name="disaron_id",
            field=models.CharField(
                help_text="The identifier of the publication in the old Agreste website",
                max_length=255,
                unique=True,
                verbose_name="Disaron identifier",
            ),
        ),
    ]
