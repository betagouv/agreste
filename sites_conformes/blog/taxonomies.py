from sites_conformes.blog.models import Category
from sites_conformes.blog.taxonomy_registration import TaxonomyRegistration

CATEGORY = TaxonomyRegistration(
    Category,
    "blog_categories",
    "filter_by_category",
    "sites_conformes_blog/categories_list_page.html",
    "categories_list",
    "categories",
)
