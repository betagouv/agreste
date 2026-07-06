from publications.models import Collection, Theme
from sites_conformes.blog.taxonomy_registration import TaxonomyRegistration

COLLECTION = TaxonomyRegistration(
    Collection,
    "collections",
    "filter_by_collection",
    "publications/collections_list_page.html",
    "collections_list",
    "collections",
)
THEME = TaxonomyRegistration(
    Theme,
    "themes",
    "filter_by_theme",
    "publications/themes_list_page.html",
    "themes_list",
    "themes",
)
