from publications.models import Collection, Theme
from sites_conformes.blog.taxonomy import Taxonomy

COLLECTION = Taxonomy(
    Collection,
    "collections",
    "filter_by_collection",
    "publications/collections_list_page.html",
    "collections_list",
    "collections",
)
THEME = Taxonomy(
    Theme,
    "themes",
    "filter_by_theme",
    "publications/themes_list_page.html",
    "themes_list",
    "themes",
)
