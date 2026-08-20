#!/usr/bin/env bash
# Apply wagtail-transfer 0.11 patches.
# Idempotent: safe to run on every startup. Remove when upgrading to a
# release that includes the upstream fixes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Locate the installed wagtail_transfer package.
# In Docker/Scalingo, packages live in the global env — use python directly.
# Locally, use uv run to activate the venv.
PYTHON="${PYTHON:-$(command -v python3 || command -v python)}"
if $PYTHON -c "import wagtail_transfer" 2>/dev/null; then
    PKG_DIR="$($PYTHON -c "import wagtail_transfer; print(wagtail_transfer.__path__[0])")"
elif command -v uv >/dev/null 2>&1; then
    PKG_DIR="$(uv run --project "$SCRIPT_DIR/.." python -c "import wagtail_transfer; print(wagtail_transfer.__path__[0])")"
else
    echo "Cannot locate wagtail_transfer" >&2
    exit 1
fi
SITE_PACKAGES="$(dirname "$PKG_DIR")"

applied=0
failed=0

for patchfile in "$SCRIPT_DIR"/*.patch; do
    [ -f "$patchfile" ] || continue
    name="$(basename "$patchfile")"
    if patch -p1 --forward --no-backup-if-mismatch --directory="$SITE_PACKAGES" --input="$patchfile" --dry-run >/dev/null 2>&1; then
        patch -p1 --forward --no-backup-if-mismatch --directory="$SITE_PACKAGES" --input="$patchfile"
        # Invalidate all bytecode caches under wagtail_transfer to avoid stale .pyc files
        find "$PKG_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        echo "Applied $name"
        applied=$((applied + 1))
    elif patch -p1 --reverse --directory="$SITE_PACKAGES" --input="$patchfile" --dry-run >/dev/null 2>&1; then
        echo "Already applied: $name"
    else
        echo "FAILED to apply: $name" >&2
        failed=$((failed + 1))
    fi
done

if [ "$failed" -gt 0 ]; then
    exit 1
fi
