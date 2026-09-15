from publications.models import Collection, Theme
from sites_conformes.blog.taxonomy_registration import TaxonomyRegistration

COLLECTION = TaxonomyRegistration(
    Collection,
    m2m_field="collections",
    index_page_filter_display_switch="filter_by_collection",
    list_template="publications/collections_list_page.html",
    list_route_name="collections_list",
    plural="collections",
)
THEME = TaxonomyRegistration(
    Theme,
    m2m_field="themes",
    index_page_filter_display_switch="filter_by_theme",
    list_template="publications/themes_list_page.html",
    list_route_name="themes_list",
    plural="themes",
)
