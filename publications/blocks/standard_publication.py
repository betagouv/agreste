from django.utils.translation import gettext_lazy as _
from wagtail import blocks
from wagtail.rich_text import get_text_for_indexing

from publications.blocks.downloadable_document import DownloadableDocumentBlock
from sites_conformes.core.constants import LIMITED_RICHTEXTFIELD_FEATURES

STANDARD_PUBLICATION_BLOCK = "standard_publication"

_RAW_HTML_HELP_TEXT = _(
    "Warning: Use HTML block with caution. Malicious code can compromise the security of the site."
)


class StandardPublicationValue(blocks.StructValue):
    def has_notes(self):
        # Draftail saves an untouched field as an empty paragraph, which is still truthy.
        notes = self.get("notes")
        source = getattr(notes, "source", "") or ""
        return bool(get_text_for_indexing(str(source)))


class StandardPublicationBlock(blocks.StructBlock):
    subtitle = blocks.CharBlock(label=_("Subtitle"), required=False)
    summary = blocks.RichTextBlock(
        label=_("Summary"),
        features=LIMITED_RICHTEXTFIELD_FEATURES,
        required=False,
    )
    presentation = blocks.RawHTMLBlock(
        label=_("Presentation"),
        help_text=_RAW_HTML_HELP_TEXT,
        required=False,
    )
    additional_information = blocks.RawHTMLBlock(
        label=_("Additional information"),
        help_text=_RAW_HTML_HELP_TEXT,
        required=False,
    )
    notes = blocks.RichTextBlock(
        label=_("Notes"),
        features=LIMITED_RICHTEXTFIELD_FEATURES,
        required=False,
    )
    downloadable_documents = blocks.ListBlock(
        DownloadableDocumentBlock(label=_("Document to download")),
        label=_("Documents to download"),
    )

    class Meta:
        icon = "doc-full"
        label = _("Standard publication")
        template = "publications/blocks/standard_publication.html"
        group = _("Agreste")
        value_class = StandardPublicationValue
