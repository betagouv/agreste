from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from publications.blocks.download_tile import DownloadTileBlock
from sites_conformes.core.constants import LIMITED_RICHTEXTFIELD_FEATURES

STANDARD_PUBLICATION_BLOCK = "standard_publication"


class StandardPublicationBlock(blocks.StructBlock):
    subtitle = blocks.CharBlock(label=_("Subtitle"))
    summary = blocks.RichTextBlock(
        label=_("Summary"),
        features=LIMITED_RICHTEXTFIELD_FEATURES,
    )
    download_tiles = blocks.ListBlock(
        DownloadTileBlock(label=_("Document to download")),
        label=_("Documents to download"),
    )

    class Meta:
        icon = "doc-full"
        label = _("Standard publication")
        template = "publications/blocks/standard_publication.html"
        group = _("Agreste")
