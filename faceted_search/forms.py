from django import forms
from django.http import QueryDict
from django.utils.translation import gettext_lazy as _
from dsfr.forms import DsfrBaseForm
from dsfr.widgets import InlineRadioSelect

from faceted_search.search import (
    RANK_BY_DATE,
    RANK_BY_RELEVANCE,
    get_rank_by_from_query_dict,
)

# Parameters to omit from the hidden fields when the ranking form is submitted.
# ``page`` is omitted so changing ranking returns to page 1.
_OMITTED_GET_PARAMS = frozenset({"rank_by", "page"})


class RankByForm(DsfrBaseForm):
    """GET form to switch search ranking; preserves other query params as hidden fields."""

    rank_by = forms.ChoiceField(
        label=_("Rank by:"),
        choices=(
            (RANK_BY_RELEVANCE, _("Relevance")),
            (RANK_BY_DATE, _("Date")),
        ),
        widget=InlineRadioSelect(attrs={"onchange": "this.form.submit()"}),
        required=False,
    )

    def __init__(self, *args, query_dict: QueryDict | None = None, **kwargs):
        query_dict = QueryDict() if query_dict is None else query_dict
        kwargs["initial"] = {"rank_by": get_rank_by_from_query_dict(query_dict)}
        super().__init__(*args, **kwargs)
        self.hidden_params = [
            (key, value) for key, values in query_dict.lists() for value in values if key not in _OMITTED_GET_PARAMS
        ]
