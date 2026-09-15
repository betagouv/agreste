from sites_conformes.blog.models import Category
from sites_conformes.blog.taxonomy_registration import TaxonomyRegistration

CATEGORY = TaxonomyRegistration(
    Category,
    m2m_field="blog_categories",
    index_page_filter_display_switch="filter_by_category",
    list_template="sites_conformes_blog/categories_list_page.html",
    list_route_name="categories_list",
    plural="categories",
)
