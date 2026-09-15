#!/usr/bin/env python3
"""Pack medias/documents into <=99MB upload-batches/ folders for manual upload.

Excludes GraFra* filenames and extensions the target site rejects.
Uses hardlinks so originals are untouched and disk use stays low.
Writes SUMMARY.md with markdown checkboxes for tracking uploads.

Progress of uploads : https://github.com/betagouv/agreste/issues/89

Usage:
  python scripts/piag/prepare_upload_batches.py
  python scripts/piag/prepare_upload_batches.py --source medias/documents --output upload-batches
  python scripts/piag/prepare_upload_batches.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

ALLOWED_EXTENSIONS = frozenset(
    {
        ".docx",
        ".pptx",
        ".pdf",
        ".pptm",
        ".md",
        ".html",
        ".htm",
        ".xhtml",
        ".adoc",
        ".asciidoc",
        ".asc",
        ".csv",
        ".xlsx",
        ".xlsm",
        ".odt",
        ".dotm",
        ".txt",
        ".eml",
    }
)

DEFAULT_LIMIT_MB = 99.0
REPO_ROOT = Path(__file__).resolve().parents[2]


def classify(path: Path) -> str | None:
    """Return skip reason, or None if the file should be uploaded."""
    if path.name.lower().startswith("grafra"):
        return "grafra"
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        return "unsupported_ext"
    return None


def pack_first_fit(files: list[tuple[Path, int]], limit: int) -> list[list[tuple[Path, int]]]:
    """Greedy first-fit: largest files first, fill existing batches when possible."""
    ordered = sorted(files, key=lambda item: item[1], reverse=True)
    batches: list[list[tuple[Path, int]]] = []
    batch_sizes: list[int] = []
    for path, size in ordered:
        if size > limit:
            raise SystemExit(f"File exceeds batch limit ({size} > {limit} bytes): {path}")
        placed = False
        for i, current in enumerate(batch_sizes):
            if current + size <= limit:
                batches[i].append((path, size))
                batch_sizes[i] = current + size
                placed = True
                break
        if not placed:
            batches.append([(path, size)])
            batch_sizes.append(size)
    return batches


def clear_output(output: Path) -> None:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)


def hardlink_or_copy(src: Path, dest: Path) -> None:
    try:
        dest.hardlink_to(src)
    except OSError:
        shutil.copy2(src, dest)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=REPO_ROOT / "medias" / "documents",
        help="Directory of source documents (default: medias/documents)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "upload-batches",
        help="Output directory (default: upload-batches/)",
    )
    parser.add_argument(
        "--limit-mb",
        type=float,
        default=DEFAULT_LIMIT_MB,
        help=f"Max batch size in MiB (default: {DEFAULT_LIMIT_MB:g})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify and pack, but do not write hardlinks or clear output",
    )
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    limit = int(args.limit_mb * 1024 * 1024)

    if not source.is_dir():
        raise SystemExit(f"Source directory not found: {source}")

    uploadable: list[tuple[Path, int]] = []
    skipped_rows: list[dict[str, object]] = []

    for path in sorted(source.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file():
            continue
        reason = classify(path)
        size = path.stat().st_size
        if reason:
            skipped_rows.append(
                {
                    "filename": path.name,
                    "size_bytes": size,
                    "reason": reason,
                    "extension": path.suffix.lower() or "(none)",
                }
            )
            continue
        uploadable.append((path, size))

    batches = pack_first_fit(uploadable, limit)

    if not args.dry_run:
        clear_output(output)

    manifest_rows: list[dict[str, object]] = []
    summary_lines = [
        "# Upload batches",
        "",
        "Prepared for manual multi-file upload (log in yourself; no credentials in this repo).",
        "",
        f"- **Source:** `{source}`",
        f"- **Output:** `{output}`",
        f"- **Batch limit:** {args.limit_mb:g} MiB",
        f"- **Uploadable files:** {len(uploadable)}",
        f"- **Skipped files:** {len(skipped_rows)}",
        f"- **Batches:** {len(batches)}",
        "",
        "## Workflow",
        "",
        "1. Log into the site in your browser.",
        "2. For each `batch-NNN` folder below, select all files and upload.",
        "3. Tick the checkbox when a batch is done.",
        "",
        "## Batches",
        "",
    ]

    for index, batch in enumerate(batches, start=1):
        batch_id = f"batch-{index:03d}"
        batch_dir = output / batch_id
        total = sum(size for _, size in batch)
        if not args.dry_run:
            batch_dir.mkdir(parents=True, exist_ok=True)
        for path, size in sorted(batch, key=lambda item: item[0].name.lower()):
            if not args.dry_run:
                hardlink_or_copy(path, batch_dir / path.name)
            manifest_rows.append(
                {
                    "batch": batch_id,
                    "filename": path.name,
                    "size_bytes": size,
                }
            )
        summary_lines.append(f"- [ ] `{batch_id}`: {len(batch)} files, {total / (1024 * 1024):.1f} MiB")

    summary_lines.extend(
        [
            "",
            "## Skipped (counts)",
            "",
        ]
    )
    reason_counts: dict[str, int] = {}
    for row in skipped_rows:
        reason = str(row["reason"])
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    for reason, count in sorted(reason_counts.items()):
        summary_lines.append(f"- `{reason}`: {count}")

    if args.dry_run:
        print("\n".join(summary_lines))
        print("\nDry run: no files written.")
        return 0

    write_csv(
        output / "manifest.csv",
        ["batch", "filename", "size_bytes"],
        manifest_rows,
    )
    write_csv(
        output / "skipped.csv",
        ["filename", "size_bytes", "reason", "extension"],
        skipped_rows,
    )
    (output / "SUMMARY.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print("\n".join(summary_lines))
    print(f"\nWrote {output}/manifest.csv, skipped.csv, SUMMARY.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
