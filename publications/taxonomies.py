from publications.models import Collection, Theme
from sites_conformes.blog.taxonomy import Taxonomy

COLLECTION = Taxonomy(Collection, "collections", "filter_by_collection")
THEME = Taxonomy(Theme, "themes", "filter_by_theme")
