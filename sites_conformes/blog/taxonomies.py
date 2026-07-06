from sites_conformes.blog.models import Category
from sites_conformes.blog.taxonomy import Taxonomy

CATEGORY = Taxonomy(Category, "blog_categories", "filter_by_category")
