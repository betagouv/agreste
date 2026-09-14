from django.utils.html import escape
from django.utils.translation import gettext_lazy as _
from wagtail import blocks
from wagtail.documents.blocks import DocumentChooserBlock

from sites_conformes.core.blocks.cards import TileBlock

DOWNLOADABLE_DOCUMENT_BLOCK = "downloadable_document"

DOWNLOAD_TYPE_CHOICES = [
    ("publication", _("Publication")),
    ("data", _("Data")),
]

DOWNLOAD_TYPE_TITLES = {
    "publication": _("Download publication"),
    "data": _("Download data"),
}

DOWNLOADABLE_DOCUMENT_LINK_PLACEHOLDER = "#"
DOWNLOADABLE_DOCUMENT_PLACEHOLDER = _("Your document will appear here")


class DownloadableDocumentBlock(blocks.StructBlock):
    download_type = blocks.ChoiceBlock(
        label=_("Type"),
        choices=DOWNLOAD_TYPE_CHOICES,
        default="publication",
    )
    document = DocumentChooserBlock(label=_("Document"))

    """ Index only the document title """

    def get_searchable_content(self, value):
        content = []
        document = value.get("document")
        if document:
            content.append(document.title)
        return content

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
            tile_data["description"] = f"<p><em>{escape(DOWNLOADABLE_DOCUMENT_PLACEHOLDER)}</em></p>"
            tile_data["link"] = {
                "link_type": "external_url",
                "external_url": DOWNLOADABLE_DOCUMENT_LINK_PLACEHOLDER,
            }

        context["value"] = TileBlock().to_python(tile_data)
        return context

    class Meta:
        icon = "download"
        label = _("Downloadable document")
        template = "publications/blocks/downloadable_document.html"
        group = _("Agreste")
