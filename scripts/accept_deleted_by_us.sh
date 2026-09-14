#!/usr/bin/env bash
# Resolve "deleted by us" (DU) merge conflicts under a path by keeping the deletion.
# Usage: accept_deleted_by_us.sh <path>
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <path>" >&2
    exit 1
fi

path="${1%/}"
count=0

while IFS= read -r file; do
    [ -z "$file" ] && continue
    git rm -- "$file"
    count=$((count + 1))
done <<EOF
$(git status --short | awk -v p="$path" '
    /^DU / {
        f = $2
        if (f == p || index(f, p "/") == 1) print f
    }')
EOF

if [ "$count" -eq 0 ]; then
    echo "No 'deleted by us' conflicts under ${path}"
    exit 0
fi

echo "Kept deletion for ${count} path(s) under ${path}"
