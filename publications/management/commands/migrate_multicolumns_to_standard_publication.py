"""
Migrate matching ``multicolumns`` blocks on ``PublicationPage`` to ``standard_publication``.

Run on staging first::

    python manage.py migrate_multicolumns_to_standard_publication --dry-run
    python manage.py migrate_multicolumns_to_standard_publication
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from publications.migrations.data_migrations.multicolumns_to_standard_publication import (
    migration_log_path,
    run_migration,
)
from publications.models import PublicationPage


class Command(BaseCommand):
    help = "Migrate matching multicolumns blocks on PublicationPage to standard_publication."

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
                "migrate_to_standard_<timestamp>.log)."
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
        pages = PublicationPage.objects.live().specific()

        if not dry_run and not options["no_input"]:
            page_count = pages.count()
            prompt = (
                f"This will migrate matching multicolumns blocks on {page_count} live PublicationPage(s). "
                "Continue? [y/N]: "
            )
            if input(prompt).strip().lower() not in {"y", "yes"}:
                self.stdout.write("Aborted.")
                return

        log_file = None
        if not options["no_log_file"]:
            path = migration_log_path(
                override=options["log_file"],
                started_at=timezone.now(),
            )
            log_file = path.open("w", encoding="utf-8")
            self.stdout.write(f"Logging to {path}")

        try:
            summary = run_migration(
                pages,
                dry_run=dry_run,
                log_file=log_file,
            )
        finally:
            if log_file is not None:
                log_file.close()

        for page_result in summary.page_results:
            for block_result in page_result.block_results:
                if block_result.action == "migrated":
                    prefix = "[dry-run] " if dry_run else ""
                    self.stdout.write(
                        f"{prefix}MIGRATED: id={page_result.page_id} {page_result.page_url} "
                        f"({page_result.migrated_count} block(s))",
                    )
                elif block_result.action == "skipped":
                    self.stdout.write(
                        f"SKIPPED: id={page_result.page_id} {page_result.page_url} reason: {block_result.reason}",
                    )

        self.stdout.write(
            f"pages_scanned={summary.pages_scanned} "
            f"pages_changed={summary.pages_changed} "
            f"blocks_migrated={summary.blocks_migrated} "
            f"blocks_skipped={summary.blocks_skipped}",
        )
