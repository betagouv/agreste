from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.ui.tables import Column
from wagtail.admin.viewsets.pages import PageViewSet
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from publications.models import (
    Collection,
    GeographicLevel,
    Modality,
    PublicationPage,
    ReferenceYear,
    StatisticalSource,
    Theme,
)


class CollectionViewSet(SnippetViewSet):
    model = Collection
    icon = "folder-open-inverse"  # type: ignore


class ThemeViewSet(SnippetViewSet):
    model = Theme
    icon = "tag"  # type: ignore


class StatisticalSourceViewSet(SnippetViewSet):
    model = StatisticalSource
    icon = "doc-full-inverse"  # type: ignore


class ReferenceYearViewSet(SnippetViewSet):
    model = ReferenceYear
    icon = "date"  # type: ignore


class GeographicLevelViewSet(SnippetViewSet):
    model = GeographicLevel
    icon = "site"  # type: ignore


class ModalityViewSet(SnippetViewSet):
    model = Modality
    icon = "list-ul"  # type: ignore


class PublicationPageViewSet(PageViewSet):
    """Explorer listing used when opening a publication index."""

    model = PublicationPage
    list_display = PageViewSet.columns.copy()
    list_display.insert(
        2,
        Column("disaron_id", label=_("Disaron identifier"), sort_key="disaron_id"),
    )


register_snippet(CollectionViewSet)
register_snippet(ThemeViewSet)
register_snippet(StatisticalSourceViewSet)
register_snippet(ReferenceYearViewSet)
register_snippet(GeographicLevelViewSet)
register_snippet(ModalityViewSet)


@hooks.register("register_admin_viewset")
def register_publication_page_viewset():
    return PublicationPageViewSet()


@hooks.register("insert_global_admin_css")
def nomenclature_editor_css():
    return format_html('<link rel="stylesheet" href="{}">', static("publications/css/nomenclature_entries.css"))


@hooks.register("insert_global_admin_js")
def nomenclature_editor_js():
    return format_html('<script src="{}"></script>', static("publications/js/nomenclature_modalities.js"))
