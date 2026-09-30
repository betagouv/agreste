from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("publications", "0004_publication_add_disaron_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="publicationpage",
            name="disaron_id",
            field=models.CharField(
                help_text="Unique publication identifier. Shown at the bottom of the page.",
                max_length=255,
                unique=True,
                verbose_name="Disaron identifier (former Agreste)",
            ),
        ),
    ]
