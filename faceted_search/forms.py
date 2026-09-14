from django import forms
from django.http import QueryDict
from django.utils.translation import gettext_lazy as _
from dsfr.forms import DsfrBaseForm

from faceted_search.search import RANK_BY_DATE, RANK_BY_RELEVANCE
from publications.models import Collection, Theme
from sites_conformes.blog.models import Category, Organization, Person
from sites_conformes.core.models import Tag

# Facets whose values are scoped to the site locale.
_LOCALIZED_FACETS = ("category", "collection", "theme")


def _facet_field(queryset, to_field_name: str | None = "slug") -> forms.ModelMultipleChoiceField:
    """Checkbox field for one facet, selected by ``to_field_name`` (slug, or pk when None)."""
    return forms.ModelMultipleChoiceField(
        queryset=queryset,
        to_field_name=to_field_name,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )


class RankBySelect(forms.Select):
    """Select widget defaulting to relevance when ``rank_by`` is missing or unknown.

    Django reads a bound value through ``value_from_datadict`` both to render the
    field and to clean it, so the default applies to the selected option and to
    ``cleaned_data`` alike.
    """

    def value_from_datadict(self, data, files, name):
        value = super().value_from_datadict(data, files, name)
        return value if value in dict(self.choices) else RANK_BY_RELEVANCE


class DateInput(forms.DateInput):
    """Native date picker bound to the search form.

    ``format`` is ISO so the ``value`` attribute matches ``type="date"``.
    """

    def __init__(self, attrs=None):
        super().__init__(
            format="%Y-%m-%d",
            attrs={
                "type": "date",
                "form": "faceted-search-form",
                "onchange": "this.form.submit()",
                "class": "fr-input",
                **(attrs or {}),
            },
        )


class FacetedSearchForm(DsfrBaseForm):
    """GET form holding every input of the search results page.

    The search bar and the facet checkboxes are rendered by hand in the templates
    (the facet trees need nesting and result counts that stock widgets cannot
    produce), so this form is mostly here to bind and validate the query string.

    Unknown facet values raise a validation error, which the view turns into a 404.
    ``page`` is deliberately not a field, so submitting the form resets pagination.
    """

    q = forms.CharField(required=False)

    category = _facet_field(Category.objects.all())
    collection = _facet_field(Collection.objects.all())
    theme = _facet_field(Theme.objects.all())
    tag = _facet_field(Tag.objects.all())
    source = _facet_field(Organization.objects.all())
    author = _facet_field(Person.objects.all(), to_field_name=None)
    date_from = forms.DateField(
        label=_("Start date"),
        required=False,
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        widget=DateInput(attrs={"aria-describedby": "id_date_from-messages"}),
    )
    date_to = forms.DateField(
        label=_("End date"),
        required=False,
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        widget=DateInput(attrs={"aria-describedby": "id_date_to-messages"}),
    )

    rank_by = forms.ChoiceField(
        label=_("Rank by:"),
        choices=(
            (RANK_BY_RELEVANCE, _("Relevance")),
            (RANK_BY_DATE, _("Date")),
        ),
        widget=RankBySelect(
            attrs={
                "onchange": "this.form.submit()",
                "form": "faceted-search-form",
                "class": "fr-select fr-mt-0",
            }
        ),
        required=True,
    )

    def __init__(self, query_dict: QueryDict | None = None, *, locale=None, **kwargs):
        super().__init__(data=QueryDict() if query_dict is None else query_dict, **kwargs)
        if locale is not None:
            for name in _LOCALIZED_FACETS:
                field = self.fields[name]
                field.queryset = field.queryset.model.objects.filter(locale=locale)
