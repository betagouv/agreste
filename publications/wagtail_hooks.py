from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.ui.tables import Column
from wagtail.admin.viewsets.pages import PageViewSet
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from publications.models import Collection, PublicationPage, Theme


class CollectionViewSet(SnippetViewSet):
    model = Collection
    icon = "folder-open-inverse"  # type: ignore


class ThemeViewSet(SnippetViewSet):
    model = Theme
    icon = "tag"  # type: ignore


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


@hooks.register("register_admin_viewset")
def register_publication_page_viewset():
    return PublicationPageViewSet()
