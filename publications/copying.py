def install_disaron_id_copy():
    """Set the typed Disaron identifier on the unsaved copy.

    ``disaron_id`` is excluded from the copy, like ``id``. Wagtail's ``_copy``
    ignores ``update_attrs`` for excluded fields, so the value typed on the copy
    form would otherwise be lost and the new row saved blank. The revision loop
    then copies whatever was saved into every revision.
    """
    import wagtail.actions.copy_page as copy_page
    import wagtail.actions.create_alias as create_alias

    copy_page._copy = _wrap_copy(copy_page._copy)
    create_alias._copy = _wrap_copy(create_alias._copy)


def _wrap_copy(original):
    if getattr(original, "_applies_disaron_id", False):
        return original

    def _copy(source, exclude_fields=None, update_attrs=None):
        target, child_object_map = original(source, exclude_fields=exclude_fields, update_attrs=update_attrs)
        new_id = getattr(source, "_copy_disaron_id", None)
        if new_id:
            target.disaron_id = new_id
        return target, child_object_map

    _copy._applies_disaron_id = True
    return _copy
