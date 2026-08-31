from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from sites_conformes.core.constants import LIMITED_RICHTEXTFIELD_FEATURES

PUBLICATION_SUMMARY_BLOCK = "publication_summary"


class PublicationSummaryBlock(blocks.StructBlock):
    summary = blocks.RichTextBlock(label=_("Summary"), features=LIMITED_RICHTEXTFIELD_FEATURES)

    class Meta:
        icon = "doc-full"
        label = _("Publication summary")
        template = "publications/blocks/publication_summary.html"
        group = _("Agreste")
