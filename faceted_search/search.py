from wagtail.models import Page

from sites_conformes.blog.models import BlogEntryPage

RANK_BY_RELEVANCE = "relevance"
RANK_BY_DATE = "date"


def get_rank_by_from_query_dict(query_dict) -> str:
    """Return ``rank_by`` from a query dict; defaults to relevance. Invalid values default to relevance."""
    rank_by = query_dict.get("rank_by", RANK_BY_RELEVANCE)
    if rank_by not in (RANK_BY_RELEVANCE, RANK_BY_DATE):
        return RANK_BY_RELEVANCE
    return rank_by


def get_rank_by_from_querystring(request) -> str:
    """Return ``rank_by`` from the request query string; defaults to relevance."""
    return get_rank_by_from_query_dict(request.GET)


def searchable_pages(request, site):
    """Live pages under the site root, restricted to public pages for anonymous users.

    When ``rank_by=date``, only ``BlogEntryPage`` (and subclasses) are included,
    since ContentPages have no editorial date.
    """
    root = site.root_page.localized
    queryset = Page.objects.descendant_of(root, inclusive=True).live()
    if not request.user.is_authenticated:
        queryset = queryset.public()
    if get_rank_by_from_querystring(request) == RANK_BY_DATE:
        return BlogEntryPage.objects.filter(pk__in=queryset)  # includes PublicationPages (subclass of BlogEntryPage)
    return queryset
