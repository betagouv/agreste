from django.utils.html import escape
from django.utils.translation import gettext_lazy as _
from wagtail import blocks
from wagtail.documents.blocks import DocumentChooserBlock

from sites_conformes.core.blocks.cards import TileBlock

DOWNLOAD_TILE_BLOCK = "download_tile"


class DownloadTileBlock(blocks.StructBlock):
    document = DocumentChooserBlock(label=_("Document"))

    def get_context(self, value, parent_context=None):
        context = super().get_context(value, parent_context=parent_context)
        document = value["document"]
        context["value"] = TileBlock().to_python(
            {
                "title": _("Download publication"),
                "heading_tag": "h3",
                "description": f"<p>{escape(document.title)}</p>",
                "link": {"link_type": "document", "document": document.pk},
            }
        )
        return context

    class Meta:
        icon = "doc-full"
        label = _("Download tile")
        template = "sites_conformes_core/blocks/tile.html"
        group = _("Agreste")
