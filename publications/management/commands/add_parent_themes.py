"""
Tag every publication page with the ancestors of its themes.

Run on staging first::

    just add_parent_themes --dry-run
    just add_parent_themes

Live pages without a pending draft are republished. Pages with a pending draft
and unpublished pages only get a new revision, which an editor has to publish.
Those pages are recapped at the end of the run.

See ``publications/migrations/batch_commands/batch_add_parent_themes.py``.
"""

from django.core.management.base import BaseCommand, CommandError

from publications.migrations.batch_commands.batch_add_parent_themes import FAILED, add_parent_themes
from publications.models import PublicationPage


class Command(BaseCommand):
    help = "Add each theme's ancestors to every publication page."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report changes without writing to the database.",
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
        pages = PublicationPage.objects.order_by("pk")

        if not dry_run and not options["no_input"]:
            prompt = (
                f"This will add missing ancestor themes to up to {pages.count()} publication page(s), "
                "publishing the live ones and saving a draft revision for the others. "
                "Continue? [y/N]: "
            )
            if input(prompt).strip().lower() not in {"y", "yes"}:
                self.stdout.write("Aborted.")
                return

        summary = add_parent_themes(
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
