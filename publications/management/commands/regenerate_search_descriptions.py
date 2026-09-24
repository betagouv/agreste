"""
Recompute ``search_description`` from the hero and body of every page.

Run on staging first::

    just regenerate_search_descriptions --dry-run
    just regenerate_search_descriptions

Existing descriptions are overwritten. Live pages without a pending draft are
republished; pages with a pending draft and unpublished pages only get a new
revision, which an editor has to publish. Both lists are recapped at the end of
the run.

See ``publications/migrations/batch_commands/search_description_backfill.py``.
"""

from django.core.management.base import BaseCommand, CommandError

from publications.migrations.batch_commands.search_description_backfill import (
    FAILED,
    pages_to_process,
    regenerate_search_descriptions,
)


class Command(BaseCommand):
    help = "Regenerate the search description of every page from its hero and body."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report changes without writing to the database.",
        )
        parser.add_argument(
            "--page-type",
            action="append",
            dest="page_types",
            metavar="app_label.ModelName",
            help="Limit the run to these page types (repeatable; default: all pages).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Stop after this many pages, for staged runs.",
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Do not prompt for confirmation before running.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        try:
            pages = pages_to_process(options["page_types"])
        except ValueError as exc:
            raise CommandError(str(exc)) from None

        if not dry_run and not options["no_input"]:
            prompt = (
                f"This will overwrite the search description of up to {pages.count()} page(s), "
                "publishing the live ones and saving a draft revision for the others. "
                "Continue? [y/N]: "
            )
            if input(prompt).strip().lower() not in {"y", "yes"}:
                self.stdout.write("Aborted.")
                return

        summary = regenerate_search_descriptions(
            pages,
            dry_run=dry_run,
            limit=options["limit"],
            log=self._log,
        )

        failed = summary.count(FAILED)
        if failed:
            raise CommandError(f"{failed} page(s) failed, see the list above.")

    def _log(self, line: str) -> None:
        self.stdout.write(line)
        self.stdout.flush()
