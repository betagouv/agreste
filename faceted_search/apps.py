from django.apps import AppConfig


class FacetedSearchConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "faceted_search"
    label = "faceted_search"

    def ready(self):
        from faceted_search.blocks.search_link import register_search_link_type

        register_search_link_type()
