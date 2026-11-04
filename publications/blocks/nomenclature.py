"""Publication nomenclature rows, edited as a code and name table and checked as a numeric tree."""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext, gettext_lazy as _
from wagtail import blocks
from wagtail.admin.telepath import register
from wagtail.blocks.stream_block import StreamBlockValidationError
from wagtail.blocks.struct_block import StructBlockValidationError
from wagtail.contrib.typed_table_block.blocks import (
    TypedTable,
    TypedTableBlock,
    TypedTableBlockAdapter,
    TypedTableBlockValidationError,
)

NAME_MAX_LENGTH = 150
CODE_MAX_LENGTH = 64
MODALITY_NAME_MAX_LENGTH = 255
CODE_COLUMN = "code"
NAME_COLUMN = "name"
CODE_OLD_COLUMN = "code_old"


class NomenclatureModalitiesBlock(TypedTableBlock):
    """Code and name columns, plus a former code that is stored and not shown."""

    code = blocks.CharBlock(label=_("Code"), max_length=CODE_MAX_LENGTH, search_index=False)
    name = blocks.CharBlock(label=_("Name"), max_length=MODALITY_NAME_MAX_LENGTH, search_index=False)
    code_old = blocks.CharBlock(required=False, max_length=CODE_MAX_LENGTH, search_index=False)

    class Meta:
        icon = "table"
        label = _("Modalities")

    def get_default(self):
        return self._empty_table()

    def normalize(self, value):
        if isinstance(value, TypedTable):
            return self._locked(value)
        return self.to_python(value)

    def to_python(self, value):
        if isinstance(value, list):
            return TypedTable(
                columns=self._fixed_columns(),
                row_data=[
                    {
                        "values": [
                            _cell(item, CODE_COLUMN),
                            _cell(item, NAME_COLUMN),
                            _cell(item, CODE_OLD_COLUMN),
                        ]
                    }
                    for item in value
                ],
                caption="",
            )
        if isinstance(value, dict) and "columns" in value:
            return self._locked(super().to_python(value))
        if not value:
            return self._empty_table()
        return self._locked(super().to_python(value))

    def value_from_datadict(self, data, files, prefix):
        return self._locked(super().value_from_datadict(data, files, prefix))

    def clean(self, value):
        table = value if isinstance(value, TypedTable) else self.to_python(value)
        cleaned = super().clean(self._locked(table))
        errors = {}
        seen = {}
        previous = None
        for index, row in enumerate(cleaned.row_data):
            code = _text(row["values"][0])
            name = _text(row["values"][1])
            parsed = _parse_code(code)
            line = index + 1
            if not name:
                # Draft saves skip CharBlock's required check, so an empty name has to be rejected here.
                errors.setdefault(index, {})[1] = ValidationError(gettext("This field is required."))
            if parsed is None:
                errors.setdefault(index, {})[0] = ValidationError(
                    gettext("Line %(line)s: code “%(code)s” must be dot-separated numbers.")
                    % {"line": line, "code": code}
                )
                continue
            if parsed in seen:
                errors.setdefault(index, {})[0] = ValidationError(
                    gettext("Line %(line)s: code “%(code)s” is already used on line %(earlier)s.")
                    % {"line": line, "code": code, "earlier": seen[parsed]}
                )
                continue
            if len(parsed) > 1 and parsed[:-1] not in seen:
                errors.setdefault(index, {})[0] = ValidationError(
                    gettext("Line %(line)s: code “%(code)s” has no parent “%(parent)s” above it.")
                    % {"line": line, "code": code, "parent": _format_code(parsed[:-1])}
                )
                continue
            if previous is not None and parsed <= previous[0]:
                errors.setdefault(index, {})[0] = ValidationError(
                    gettext(
                        "Line %(line)s: code “%(code)s” is out of order. "
                        "It should come before “%(earlier_code)s” (line %(earlier)s)."
                    )
                    % {"line": line, "code": code, "earlier": previous[1], "earlier_code": previous[2]}
                )
                continue
            seen[parsed] = line
            previous = (parsed, line, code)

        if errors:
            raise TypedTableBlockValidationError(cell_errors=errors)
        return cleaned

    def _empty_table(self):
        return TypedTable(columns=self._fixed_columns(), row_data=[], caption="")

    def _fixed_columns(self):
        return [
            {"block": self.child_blocks[CODE_COLUMN], "heading": gettext("Code")},
            {"block": self.child_blocks[NAME_COLUMN], "heading": gettext("Name")},
            {"block": self.child_blocks[CODE_OLD_COLUMN], "heading": ""},
        ]

    def _locked(self, table):
        """Keep cell values and force the columns to code, name, and code_old."""
        indexes = {}
        for index, column in enumerate(table.columns):
            indexes.setdefault(column["block"].name, index)
        code_index = indexes.get(CODE_COLUMN)
        name_index = indexes.get(NAME_COLUMN)
        code_old_index = indexes.get(CODE_OLD_COLUMN)
        row_data = []
        for row in table.row_data:
            values = row["values"]
            row_data.append(
                {
                    "values": [
                        _value_at(values, code_index),
                        _value_at(values, name_index),
                        _value_at(values, code_old_index),
                    ]
                }
            )
        return TypedTable(columns=self._fixed_columns(), row_data=row_data, caption="")


class NomenclatureModalitiesBlockAdapter(TypedTableBlockAdapter):
    def js_args(self, block):
        args = super().js_args(block)
        args[3]["classname"] = "nomenclature-modalities"
        return args


register(NomenclatureModalitiesBlockAdapter(), NomenclatureModalitiesBlock)


class NomenclatureBlock(blocks.StructBlock):
    name = blocks.CharBlock(label=_("Nomenclature name"), max_length=NAME_MAX_LENGTH, search_index=False)
    modalities = NomenclatureModalitiesBlock(label=_("Modalities"), search_index=False)

    class Meta:
        icon = "list-ul"
        label = _("Nomenclature")
        label_format = "{name}"


class NomenclatureStreamBlock(blocks.StreamBlock):
    nomenclature = NomenclatureBlock(search_index=False)

    def clean(self, value):
        cleaned = super().clean(self.normalize(value))
        errors = {}
        seen = {}
        for index, child in enumerate(cleaned):
            name = child.value["name"]
            name = name.strip() if isinstance(name, str) else ""
            earlier = seen.get(name)
            if earlier is not None:
                errors[index] = StructBlockValidationError(
                    block_errors={
                        "name": ValidationError(
                            gettext("Line %(line)s: nomenclature name “%(name)s” is already used on line %(earlier)s.")
                            % {"line": index + 1, "name": name, "earlier": earlier}
                        )
                    }
                )
                continue
            seen[name] = index + 1
        if errors:
            raise StreamBlockValidationError(block_errors=errors)
        return cleaned


def _cell(item, key):
    if isinstance(item, dict):
        return _text(item.get(key, ""))
    return ""


def _value_at(values, index):
    if index is None or index >= len(values):
        return ""
    return values[index]


def _text(value):
    if not isinstance(value, str):
        return ""
    return value.strip()


def _parse_code(code):
    """Return the integer path, or None when the code is not dot-separated unsigned integers."""
    if not code:
        return None
    parts = code.split(".")
    parsed = []
    for part in parts:
        if not part.isascii() or not part.isdigit():
            return None
        parsed.append(int(part, 10))
    return tuple(parsed)


def _format_code(parsed):
    return ".".join(str(part) for part in parsed)
