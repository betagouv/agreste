from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from publications.blocks.downloadable_document import DownloadableDocumentBlock
from sites_conformes.core.blocks.layout import ColumnBlock

FREEFORM_PUBLICATION_BLOCK = "freeform_publication"


class FreeformPublicationBlock(blocks.StructBlock):
    content = ColumnBlock(label=_("Content"), required=False)
    downloadable_documents = blocks.ListBlock(
        DownloadableDocumentBlock(label=_("Document to download")),
        label=_("Documents to download"),
    )

    class Meta:
        icon = "doc-full"
        label = _("Free-form publication")
        template = "publications/blocks/freeform_publication.html"
        group = _("Agreste")
