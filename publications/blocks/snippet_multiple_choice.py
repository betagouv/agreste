from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Model
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from wagtail.blocks import FieldBlock
from wagtail.coreutils import resolve_model_string
from wagtail.models import Locale
from wagtail.models.i18n import TranslatableMixin

from publications.taxonomy import flatten_taxonomy_tree


class ScrollableCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    template_name = "publications/widgets/scrollable_checkbox_select_multiple.html"

    class Media:
        css = {"all": ("publications/css/snippet_multiple_choice.css",)}

    def __init__(self, *args, hierarchical=False, **kwargs):
        self.hierarchical = hierarchical
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        # Django ChoiceWidget hook: one checkbox's template context.
        depth = 0
        if attrs:
            attrs = dict(attrs)
            depth = attrs.pop("data-depth", 0)
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        option["depth"] = depth
        return option

    def optgroups(self, name, value, attrs=None):
        # Django ChoiceWidget hook: ordered options for the widget template.
        selected = {str(item) for item in (value or [])}
        groups = []
        for index, (obj, depth) in enumerate(self._options_with_depth()):
            option_attrs = {**(attrs or {}), "data-depth": depth}
            option = self.create_option(
                name,
                obj.pk,
                str(obj),
                str(obj.pk) in selected,
                index,
                attrs=option_attrs,
            )
            groups.append((None, [option], index))
        return groups

    def _options_with_depth(self):
        queryset = self.choices.queryset
        if self.hierarchical:
            return flatten_taxonomy_tree(queryset)
        return [(obj, 0) for obj in queryset.order_by("name")]

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        model = self.choices.queryset.model
        context["widget"]["empty_message"] = _("No %(name)s found.") % {
            "name": str(model._meta.verbose_name).lower(),
        }
        return context


class SnippetMultipleChoiceBlock(FieldBlock):
    """Multi-select snippet checkboxes, optionally rendered as an indented tree."""

    def __init__(self, target_model, hierarchical=False, required=False, help_text=None, **kwargs):
        self._target_model = target_model
        self.hierarchical = hierarchical
        self._required = required
        self._help_text = help_text
        super().__init__(**kwargs)

    @cached_property
    def model_class(self):
        return resolve_model_string(self._target_model)

    def get_queryset(self):
        queryset = self.model_class.objects.all()
        if issubclass(self.model_class, TranslatableMixin):
            locale = Locale.get_active()
            if locale is not None:
                queryset = queryset.filter(locale=locale)
        return queryset.order_by("name")

    @property
    def field(self):
        return forms.ModelMultipleChoiceField(
            queryset=self.get_queryset(),
            required=self._required,
            help_text=self._help_text,
            widget=ScrollableCheckboxSelectMultiple(hierarchical=self.hierarchical),
        )

    def _as_list(self, value):
        if value in (None, ""):
            return []
        if isinstance(value, (str, bytes)):
            return [value]
        try:
            return list(value)
        except TypeError:
            return [value]

    def to_python(self, value):
        items = self._as_list(value)
        if not items:
            return []
        if all(isinstance(item, self.model_class) for item in items):
            return items
        # Checkbox POST sends string PKs; in_bulk keys by the native PK type.
        pk_field = self.model_class._meta.pk
        pks = []
        for item in items:
            raw = item.pk if isinstance(item, Model) else item
            try:
                pks.append(pk_field.to_python(raw))
            except (TypeError, ValueError, ValidationError):
                continue
        objects = self.model_class.objects.in_bulk(pks)
        return [objects[pk] for pk in pks if pk in objects]

    def normalize(self, value):
        return self.to_python(value)

    def get_prep_value(self, value):
        return [item.pk if isinstance(item, Model) else item for item in self._as_list(value)]

    def value_for_form(self, value):
        return self.get_prep_value(value)

    def value_from_form(self, value):
        return self.to_python(value)

    def extract_references(self, value):
        for item in self._as_list(value):
            if isinstance(item, self.model_class):
                yield self.model_class, str(item.pk), "", ""

    class Meta:
        default = []
        icon = "list-ul"
