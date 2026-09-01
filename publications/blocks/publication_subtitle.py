from django.utils.translation import gettext_lazy as _
from wagtail import blocks

PUBLICATION_SUBTITLE_BLOCK = "publication_subtitle"


class PublicationSubtitleBlock(blocks.StructBlock):
    subtitle = blocks.CharBlock(label=_("Subtitle"))

    class Meta:
        icon = "title"
        label = _("Publication subtitle")
        template = "publications/blocks/publication_subtitle.html"
        group = _("Agreste")
