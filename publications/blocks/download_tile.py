from django.utils.html import escape
from django.utils.translation import gettext_lazy as _
from wagtail import blocks
from wagtail.documents.blocks import DocumentChooserBlock

from sites_conformes.core.blocks.cards import TileBlock

DOWNLOAD_TILE_BLOCK = "download_tile"

DOWNLOAD_TYPE_CHOICES = [
    ("publication", _("Publication")),
    ("data", _("Data")),
]

DOWNLOAD_TYPE_TITLES = {
    "publication": _("Download publication"),
    "data": _("Download data"),
}

DOWNLOAD_TILE_LINK_PLACEHOLDER = "#"
DOWNLOAD_TILE_DOCUMENT_PLACEHOLDER = _("Your document will appear here")


class DownloadTileBlock(blocks.StructBlock):
    download_type = blocks.ChoiceBlock(
        label=_("Type"),
        choices=DOWNLOAD_TYPE_CHOICES,
        default="publication",
    )
    document = DocumentChooserBlock(label=_("Document to download"))

    def get_context(self, value, parent_context=None):
        context = super().get_context(value, parent_context=parent_context)
        document = value.get("document")
        download_type = value.get("download_type")

        tile_data = {
            "title": DOWNLOAD_TYPE_TITLES.get(download_type, DOWNLOAD_TYPE_TITLES["publication"]),
            "heading_tag": "h3",
        }
        if document:
            tile_data["description"] = f"<p>{escape(document.title)}</p>"
            tile_data["link"] = {"link_type": "document", "document": document.pk}
        else:
            tile_data["description"] = f"<p><em>{escape(DOWNLOAD_TILE_DOCUMENT_PLACEHOLDER)}</em></p>"
            tile_data["link"] = {
                "link_type": "external_url",
                "external_url": DOWNLOAD_TILE_LINK_PLACEHOLDER,
            }

        context["value"] = TileBlock().to_python(tile_data)
        return context

    class Meta:
        icon = "download"
        label = _("Download tile")
        template = "publications/blocks/download_tile.html"
        group = _("Agreste")
