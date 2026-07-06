"""Taxonomy registry for index page filtering.

Adding a new taxonomy (example: ``Collection`` on publications)
================================================================

``TaxonomyRegistration`` only describes how an *existing* setup is wired. You must also
add models, fields, templates, and a migration. Below, ``slug`` is the URL /
query-param name (``collection`` → ``?collection=agriculture``). Derived names
come from ``TaxonomyRegistration`` properties unless you pass ``slug=`` explicitly.

**1. Taxonomy model** (snippet rows: Agriculture, Environment, …)

- Subclass ``AbstractTaxonomy`` (``sites_conformes.blog.abstract_taxonomy``).
- Run ``makemigrations``.

**2. Entry page** (e.g. ``PublicationPage``)

- Add a ``ParentalManyToManyField`` to the taxonomy model (``collections``), usually
  with a through ``Orderable`` table.
- Add the field to editor panels.
- Run ``makemigrations``.

**3. Index page** (subclass of ``BlogIndexPage``, e.g. ``PublicationIndexPage``)

- ``filter_by_{slug}`` boolean field — e.g. ``filter_by_collection``. This name
  is required: ``BlogIndexPage.show_filters`` reads it via
  ``taxonomy.filter_field``.
- Add ``FieldPanel("filter_by_collection")`` to the "Show filters" panel.
- Run ``makemigrations``.
- ``subpage_types`` must point at your entry page class.

**4. Register the taxonomy** (your app's ``taxonomies.py`` + ``apps.py``)

Pass ``filter_field``, ``list_template``, ``list_route_name``, and ``plural``
explicitly — they must match the index page field (step 3), list template
(step 6), route name (step 5), and template context key (step 6)::

    # publications/taxonomies.py
    COLLECTION = TaxonomyRegistration(
        Collection,
        "collections",
        "filter_by_collection",
        "publications/collections_list_page.html",
        "collections_list",
        "collections",
    )

    # publications/apps.py → ready()
    register_taxonomies(PublicationPage, [COLLECTION, THEME])

**5. List page route** (on the index page subclass)

``BlogIndexPage`` does not declare routes for you. Add one per taxonomy::

    @path("collections/", name="collections_list")
    def collections_list(self, request, *args, **kwargs):
        from publications.taxonomies import COLLECTION
        return self.render_taxonomy_list(request, COLLECTION)

The route ``name`` must match ``taxonomy.list_route_name`` (``collections_list``).

**6. Templates**

- **Index page** (e.g. ``publication_index_page.html``): filter sidebar using
  context keys ``collections``, ``current_collection``, and
  ``page.filter_by_collection``. ``BlogIndexPage.get_context`` fills those keys
  automatically.
- **List page**: create the template passed as ``list_template`` on
  ``TaxonomyRegistration`` (e.g. ``publications/collections_list_page.html``). Use dict keys
  ``collection_slug``, ``collection_name``, ``collection_count`` in the loop
  (see ``list_taxonomy_values``).

**7. Optional helpers**

- ``get_collections()`` on the index page, calling
  ``get_taxonomy_values(self, COLLECTION)`` — only needed if a block or template
  calls it by name (see ``PublicationIndexPage.get_collections``).

**Provided by ``BlogIndexPage`` once the above exists** — no extra code:

- ``get_context``: ``?collection=`` filtering, breadcrumbs, ``extra_title``
- ``show_filters``: checks ``filter_by_collection``
- ``feed_posts``: ``?collection=`` filtering
- ``posts``: prefetches the ``collections`` M2M field
- ``render_taxonomy_list``: renders the list page

**Naming conventions** (for ``slug="collection"``)

+----------------------+-------------------------------+
| Role                 | Name                          |
+======================+===============================+
| Query param          | ``collection``                |
| Index boolean field  | ``filter_by_collection``      |
| Context (all values) | ``collections`` (``plural``)    |
| Context (active)     | ``current_collection``        |
| List route name      | ``collections_list``          |
| List template        | ``publications/collections_list_page.html`` |
+----------------------+-------------------------------+
"""

from django.db.models import Count
from django.db.models.expressions import F
from django.utils.translation import gettext_lazy as _

_taxonomies = {}

DEFAULT_FILTERED_TITLE = _("Posts in %(type)s %(name)s")


class TaxonomyRegistration:
    """Binding between a taxonomy model, an entry page M2M field, and an index page.

    See the module docstring above for the full checklist of what to implement
    alongside a ``TaxonomyRegistration`` instance.
    """

    def __init__(
        self,
        model,
        m2m_field,
        filter_field,
        list_template,
        list_route_name,
        plural,
        *,
        slug=None,
        filtered_title=None,
    ):
        self.model = model
        self.m2m_field = m2m_field
        self.filter_field = filter_field
        self.list_template = list_template
        self.list_route_name = list_route_name
        self.plural = plural
        self.slug = slug or model._meta.model_name
        self._custom_filtered_title = filtered_title

    def format_filtered_title(self, name):
        if self._custom_filtered_title is None:
            return DEFAULT_FILTERED_TITLE % {
                "type": self.model._meta.verbose_name,
                "name": name,
            }
        return self._custom_filtered_title % {self.slug: name}

    @property
    def filter_heading(self):
        return _("Filter by %(name)s") % {"name": self.model._meta.verbose_name}

    @property
    def list_label_plural(self):
        return self.model._meta.verbose_name_plural

    @property
    def current_context_key(self):
        return f"current_{self.slug}"

    @property
    def list_slug_path(self):
        return f"{self.m2m_field}__slug"

    @property
    def list_name_path(self):
        return f"{self.m2m_field}__name"


def register_taxonomies(entry_page_class, taxonomies):
    """Associate taxonomy definitions with an entry page class.

    Example: ``register_taxonomies(BlogEntryPage, [CATEGORY])`` in ``BlogConfig.ready()``.
    """
    _taxonomies[entry_page_class] = taxonomies


def get_taxonomy_types(entry_page_class):
    """Return taxonomy *definitions* registered for an entry page class.

    This is metadata (slug, model, template, …), not database rows.

    Example::

        get_taxonomy_types(BlogEntryPage)
        # → [CATEGORY]   # the TaxonomyRegistration object from taxonomies.py

        get_taxonomy_types(PublicationPage)
        # → [COLLECTION, THEME]

    ``BlogIndexPage.get_context`` loops over this list to know which filters
    to apply and which context keys to fill (``categories``, ``collections``, …).
    """
    return _taxonomies.get(entry_page_class, [])


def get_taxonomy_values(index_page, taxonomy):
    """Return taxonomy *instances* present on posts under an index page.

    This is the data shown in filter sidebars — the same as the old
    ``BlogIndexPage.get_categories()`` method.

    Example::

        get_taxonomy_values(my_blog_index_page, CATEGORY)
        # → <QuerySet [<Category: Agriculture>, <Category: Climate>]>

    Only values linked to at least one live post under ``index_page`` are
    returned, ordered by name.
    """
    ids = index_page.posts.specific().values_list(
        taxonomy.m2m_field,
        flat=True,
    )
    return taxonomy.model.objects.filter(id__in=ids).order_by("name")


def list_taxonomy_values(index_page, taxonomy):
    """Return taxonomy values with post counts, for a taxonomy list page.

    Example::

        list_taxonomy_values(my_blog_index_page, CATEGORY)
        # → [
        #     {"category_slug": "agriculture", "category_name": "Agriculture", ...},
        #   ]

    Used by ``BlogIndexPage.categories_list`` (via ``render_taxonomy_list``).
    """
    posts = index_page.posts.specific()
    slug_key = f"{taxonomy.slug}_slug"
    name_key = f"{taxonomy.slug}_name"
    count_key = f"{taxonomy.slug}_count"
    return (
        posts.values(
            **{
                slug_key: F(taxonomy.list_slug_path),
                name_key: F(taxonomy.list_name_path),
            },
        )
        .annotate(**{count_key: Count(slug_key)})
        .filter(**{f"{count_key}__gte": 1})
        .order_by(f"-{count_key}")
    )
