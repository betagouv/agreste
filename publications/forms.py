from django import forms
from django.utils.translation import gettext_lazy as _
from wagtail.admin.forms.pages import CopyForm


class PublicationPageCopyForm(CopyForm):
    """Ask for a new Disaron identifier, the same way the copy form asks for a slug."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_disaron_id"] = forms.CharField(
            initial=self.page.specific.disaron_id,
            label=_("New Disaron identifier"),
            max_length=255,
            strip=False,
        )

    def clean(self):
        cleaned_data = super().clean()
        new_id = cleaned_data.get("new_disaron_id")
        if not isinstance(new_id, str):
            return cleaned_data
        new_id = new_id.strip()
        cleaned_data["new_disaron_id"] = new_id
        if not new_id:
            self.add_error("new_disaron_id", _("This field cannot be blank."))
            return cleaned_data

        from publications.models import PublicationPage

        if PublicationPage.objects.filter(disaron_id=new_id).exists():
            self.add_error(
                "new_disaron_id",
                _("A publication with this Disaron identifier already exists."),
            )
            return cleaned_data

        self.page.specific._copy_disaron_id = new_id
        return cleaned_data
