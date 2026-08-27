#!/usr/bin/env bash
# Merge Sites Conformes tag v<version> into a fresh branch from main-agreste.
# Resolves known Agreste paths (deleted demo/tarteaucitron, ours package.json, uv.lock).
# Usage: merge_sc_tag.sh <version>   e.g. merge_sc_tag.sh 4.2.0-rc1
# Prefer: just merge-sc-tag <version>
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <version>" >&2
    echo "Example: $0 4.2.0-rc1" >&2
    exit 1
fi

SC_VERSION="$1"
BRANCH="merge-sites-conformes-${SC_VERSION}-test" # todo

run_uv() {
    if [ "${USE_DOCKER:-0}" = "1" ]; then
        docker compose exec -ti web uv "$@"
    else
        uv "$@"
    fi
}

current_branch="$(git branch --show-current)"
if [ "${current_branch}" = "${BRANCH}" ] && git rev-parse -q --verify MERGE_HEAD >/dev/null; then
    echo "==> Already on ${BRANCH} with a merge in progress; resuming resolutions…"
else
    git fetch upstream --tags
    if ! git rev-parse -q --verify "refs/tags/v${SC_VERSION}" >/dev/null; then
        echo "ERROR: tag v${SC_VERSION} not found on upstream (after fetch --tags)" >&2
        exit 1
    fi

    #git checkout main-agreste # todo
    #git pull # todo
    git checkout -B "${BRANCH}"
    echo "==> Publishing empty branch on origin (pre-merge)"
    git push -u origin "HEAD:${BRANCH}"

    echo "==> Merging Sites Conformes v${SC_VERSION} into ${BRANCH}"
    set +e
    git merge "v${SC_VERSION}"
    merge_status=$?
    set -e
    if [ "$merge_status" -ne 0 ]; then
        if ! git rev-parse -q --verify MERGE_HEAD >/dev/null; then
            echo "ERROR: merge failed (not a conflict state)" >&2
            exit "$merge_status"
        fi
        echo "==> Merge stopped with conflicts; applying known resolutions…"
    fi
fi

blocked=()
for required in justfile pyproject.toml config/settings.py; do
    if git ls-files -u -- "$required" | grep -q .; then
        blocked+=("$required")
    fi
done
if [ "${#blocked[@]}" -gt 0 ]; then
    echo ""
    echo "================================================================"
    echo "  Manual conflict resolution required before continuing"
    echo "================================================================"
    echo ""
    echo "  The following file(s) still have merge conflicts:"
    echo ""
    for f in "${blocked[@]}"; do
        echo "    - ${f}"
    done
    echo ""
    echo "  Resolve them, then re-run:"
    echo ""
    echo "    just merge-sc-tag ${SC_VERSION}"
    echo ""
    echo "================================================================"
    echo ""
    exit 1
fi

just accept-deleted-by-us demo
just accept-deleted-by-us sites_conformes/static/lib/tarteaucitronjs

# Always keep Agreste's package.json; never take upstream changes.
echo "==> package.json: forcing ours (main-agreste)"
git checkout main-agreste -- package.json
git add -- package.json

if git ls-files -u -- uv.lock | grep -q .; then
    echo "==> uv.lock: taking theirs, then regenerating"
    git checkout --theirs -- uv.lock
    git add -- uv.lock
else
    echo "==> uv.lock: no conflict; regenerating from pyproject.toml"
fi
run_uv lock
run_uv sync
git add -- uv.lock

echo "==> Running makemigrations"
just makemigrations
migrations_changed="$(git status --porcelain -- '**/migrations/*.py' || true)"
if [ -n "${migrations_changed}" ]; then
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "!!  WARNING: makemigrations created or modified migrations  !!"
    echo "!!  This is not necessarily an error — review carefully.    !!"
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "${migrations_changed}"
    echo ""
else
    echo "==> No new migrations"
fi

remaining="$(git diff --name-only --diff-filter=U || true)"
if [ -n "${remaining}" ]; then
    echo ""
    echo "==> Remaining unresolved conflicts (resolve manually, then commit the merge and push):"
    echo "${remaining}"
    if [ -n "${migrations_changed}" ]; then
        echo ""
        echo "==> Reminder: review the migrations created or modified above."
    fi
    exit 0
fi

if git rev-parse -q --verify MERGE_HEAD >/dev/null; then
    # Merge had conflicts; they are resolved but still uncommitted.
    echo "==> Conflicts resolved. Review the tree, then finish with:"
    echo "    git add -A && git commit  # conclude the merge"
    echo "    git push                # branch already tracks origin"
else
    # Merge had no conflicts, so the merge commit is already done.
    echo "==> Done. Review the merge, then: git push"
fi
if [ -n "${migrations_changed}" ]; then
    echo ""
    echo "==> Reminder: review the migrations created or modified by makemigrations."
fi
