"""
Copy ``disaron_id`` out of the top-level ``<div id="disaron-nom">`` HTML block.

Run on staging first::

    python manage.py migrate_disaron_ids --dry-run
    python manage.py migrate_disaron_ids

The log lists every publication with its pk, disaron_id, then title. Pages with
no id, and pages whose HTML block is not exactly that div, are left unchanged.
Other pages are still written. See
``publications/migrations/data_migrations/migrate_disaron_ids.py``.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from publications.migrations.data_migrations.migrate_disaron_ids import (
    migration_log_path,
    run_migration,
)
from publications.models import PublicationPage


class Command(BaseCommand):
    help = "Copy disaron_id out of the top-level disaron-nom HTML block on publication pages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report changes without writing to the database.",
        )
        parser.add_argument(
            "--log-file",
            default=None,
            help=(
                "Log file path (default: publications/migrations/data_migrations/output/"
                "migrate_disaron_ids_<timestamp>.log)."
            ),
        )
        parser.add_argument(
            "--no-log-file",
            action="store_true",
            help="Do not write migration output to a log file (stdout only).",
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
                f"This will set disaron_id and remove the disaron HTML block on up to {pages.count()} "
                "PublicationPage(s). Pages with no id are left unchanged. Continue? [y/N]: "
            )
            if input(prompt).strip().lower() not in {"y", "yes"}:
                self.stdout.write("Aborted.")
                return

        log_file = None
        if not options["no_log_file"]:
            path = migration_log_path(override=options["log_file"], started_at=timezone.now())
            log_file = path.open("w", encoding="utf-8")
            self.stdout.write(f"Logging to {path}")

        try:
            summary = run_migration(pages, dry_run=dry_run, log_file=self._tee(log_file))
        finally:
            if log_file is not None:
                log_file.close()

        if summary.failed:
            raise CommandError(f"{summary.failed} page(s) failed, see the log above.")

    def _tee(self, log_file):
        command = self

        class _Tee:
            def write(self, text):
                command.stdout.write(text)
                if log_file is not None:
                    log_file.write(text)

            def flush(self):
                command.stdout.flush()
                if log_file is not None:
                    log_file.flush()

        return _Tee()
