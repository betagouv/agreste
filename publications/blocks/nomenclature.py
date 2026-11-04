"""Publication nomenclature rows, edited as a Wagtail list and checked as a numeric tree."""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext, gettext_lazy as _
from wagtail import blocks
from wagtail.blocks.list_block import ListBlockValidationError
from wagtail.blocks.stream_block import StreamBlockValidationError
from wagtail.blocks.struct_block import StructBlockValidationError

NAME_MAX_LENGTH = 150
CODE_MAX_LENGTH = 64
MODALITY_NAME_MAX_LENGTH = 255


class NomenclatureEntryBlock(blocks.StructBlock):
    code = blocks.CharBlock(label=_("Code"), max_length=CODE_MAX_LENGTH, search_index=False)
    name = blocks.CharBlock(label=_("Name"), max_length=MODALITY_NAME_MAX_LENGTH, search_index=False)

    class Meta:
        icon = "list-ul"
        label_format = "{code} — {name}"
        collapsed = False
        form_classname = "struct-block nomenclature-entry"


class NomenclatureEntryListBlock(blocks.ListBlock):
    """Rows of code and name. Wagtail supplies add, insert, and move."""

    class Meta:
        default = []
        min_num = 0
        form_classname = "nomenclature-entries"

    def clean(self, value):
        cleaned = super().clean(value)
        errors = {}
        seen = {}
        previous = None
        for index, child in enumerate(cleaned):
            code = _row_code(child)
            parsed = _parse_code(code)
            line = index + 1
            if parsed is None:
                errors[index] = _code_error(
                    gettext("Line %(line)s: code “%(code)s” must be dot-separated numbers.")
                    % {"line": line, "code": code}
                )
                continue
            if parsed in seen:
                errors[index] = _code_error(
                    gettext("Line %(line)s: code “%(code)s” is already used on line %(earlier)s.")
                    % {"line": line, "code": code, "earlier": seen[parsed]}
                )
                continue
            if len(parsed) > 1 and parsed[:-1] not in seen:
                errors[index] = _code_error(
                    gettext("Line %(line)s: code “%(code)s” has no parent “%(parent)s” above it.")
                    % {"line": line, "code": code, "parent": _format_code(parsed[:-1])}
                )
                continue
            if previous is not None and parsed <= previous[0]:
                errors[index] = _code_error(
                    gettext(
                        "Line %(line)s: code “%(code)s” is out of order. "
                        "It should come before line %(earlier)s (“%(earlier_code)s”)."
                    )
                    % {"line": line, "code": code, "earlier": previous[1], "earlier_code": previous[2]}
                )
                continue
            seen[parsed] = line
            previous = (parsed, line, code)

        if errors:
            raise ListBlockValidationError(block_errors=errors)
        return cleaned


class NomenclatureBlock(blocks.StructBlock):
    name = blocks.CharBlock(label=_("Nomenclature name"), max_length=NAME_MAX_LENGTH, search_index=False)
    modalities = NomenclatureEntryListBlock(
        NomenclatureEntryBlock(), label=_("Modalities : code and name"), search_index=False
    )

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


def _code_error(message):
    return StructBlockValidationError(block_errors={"code": ValidationError(message)})


def _row_code(child):
    code = child["code"]
    if not isinstance(code, str):
        return ""
    return code.strip()


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
