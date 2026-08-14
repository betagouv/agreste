from modelsearch.query import Fuzzy


def fuzzy_unaccent(query: str) -> Fuzzy:
    """Accent-insensitive fuzzy query for faceted search (django-modelsearch).
    Uses modelsearch's default Fuzzy algorithm (trigram).
    """
    return Fuzzy(query, unaccent=True)
