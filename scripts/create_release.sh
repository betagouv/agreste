#!/usr/bin/env bash
# Bump agreste_version.txt on main-agreste and open a PR into production-agreste.
# Usage: create_release.sh [--repo URL]
# Default repository: https://github.com/betagouv/agreste
# Prefer: just create-release [-- --repo URL]
set -euo pipefail

DEFAULT_REPO_URL="https://github.com/betagouv/agreste"

usage() {
    cat <<EOF
Usage: create_release.sh [--repo URL]

Bump agreste_version.txt on main-agreste and open a pull request into
production-agreste.

  --repo URL   GitHub repository for pull request links and gh commands.
               Default: ${DEFAULT_REPO_URL}
EOF
}

cd "$(git rev-parse --show-toplevel)"

require_clean_worktree() {
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo "ERROR: tracked files have uncommitted changes. Commit or stash them first." >&2
        exit 1
    fi
}

normalize_repo_url() {
    local url path
    url="${1%.git}"
    url="${url%/}"
    case "$url" in
        git@github.com:*)
            path="${url#git@github.com:}"
            ;;
        https://github.com/*)
            path="${url#https://github.com/}"
            ;;
        ssh://git@github.com/*)
            path="${url#ssh://git@github.com/}"
            ;;
        *)
            echo "ERROR: repository must be a GitHub URL (https://github.com/owner/name)." >&2
            exit 1
            ;;
    esac
    printf 'https://github.com/%s' "$path"
}

repo_url="$DEFAULT_REPO_URL"
while [ "$#" -gt 0 ]; do
    case "$1" in
        --repo)
            if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
                echo "ERROR: --repo requires a URL." >&2
                exit 1
            fi
            repo_url="$(normalize_repo_url "$2")"
            shift 2
            ;;
        --repo=*)
            repo_url="$(normalize_repo_url "${1#--repo=}")"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

# Commit on main-agreste that the last production release already contains.
released_main_commit() {
    local release_tip
    release_tip="$(git rev-parse origin/production-agreste)"
    if git rev-parse -q --verify "${release_tip}^2" >/dev/null; then
        git rev-parse "${release_tip}^2"
    else
        git merge-base origin/main-agreste "$release_tip"
    fi
}

show_pull_requests() {
    local since="$1"
    local repo_url="$2"
    local found=0
    local record rest date subject body number title direct_line line

    while IFS= read -r -d $'\x1e' record || [ -n "$record" ]; do
        record="${record#$'\n'}"
        [ -z "$record" ] && continue
        rest="${record#*$'\x1f'}"
        date="${rest%%$'\x1f'*}"
        rest="${rest#*$'\x1f'}"
        subject="${rest%%$'\x1f'*}"
        body="${rest#*$'\x1f'}"
        if [[ ! "$subject" =~ ^Merge\ pull\ request\ \#([0-9]+)[[:space:]] ]]; then
            continue
        fi
        number="${BASH_REMATCH[1]}"
        title="$(printf '%s\n' "$body" | sed -n '/./{p;q;}')"
        if [ -z "$title" ]; then
            title="$subject"
        fi
        printf '  #%s  %s  %s\n' "$number" "${date:0:16}" "$title"
        if [ -n "$repo_url" ]; then
            printf '         %s/pull/%s\n' "$repo_url" "$number"
        fi
        found=1
    done < <(git log --reverse --merges --format='%H%x1f%ci%x1f%s%x1f%b%x1e' "${since}..origin/main-agreste")

    if [ "$found" -eq 0 ]; then
        echo "No pull requests merged into main-agreste since the last release."
    fi

    direct_line=""
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        if [ -n "$direct_line" ]; then
            direct_line="${direct_line}; ${line}"
        else
            direct_line="$line"
        fi
    done < <(git log --reverse --first-parent --no-merges --format='%h %s' "${since}..origin/main-agreste")
    if [ -n "$direct_line" ]; then
        echo "Also committed directly on main-agreste: ${direct_line}"
    fi
}

require_clean_worktree

echo "Fetching origin main-agreste and production-agreste…"
git fetch origin main-agreste production-agreste --tags

release_tip="$(git rev-parse origin/production-agreste)"
if release_label="$(git describe --tags --exact-match "$release_tip" 2>/dev/null)"; then
    :
else
    release_label="$(git rev-parse --short "$release_tip")"
fi
since="$(released_main_commit)"

echo
echo "Repository: ${repo_url}"
echo "Pull requests merged into main-agreste since ${release_label}:"
echo
show_pull_requests "$since" "$repo_url"
echo

current="$(git show origin/main-agreste:agreste_version.txt | tr -d '[:space:]')"
if [[ "$current" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)-([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
    agreste_only="${BASH_REMATCH[1]}.$((10#${BASH_REMATCH[2]} + 1)).0-${BASH_REMATCH[4]}.${BASH_REMATCH[5]}.${BASH_REMATCH[6]}"
    with_sc="${BASH_REMATCH[1]}.$((10#${BASH_REMATCH[2]} + 1)).0-${BASH_REMATCH[4]}.$((10#${BASH_REMATCH[5]} + 1)).0"
else
    agreste_only="2.21.0-4.2.0"
    with_sc="2.21.0-4.3.0"
fi

echo "Current version: ${current}"
echo "Format: <Agreste X.Y.Z>-<Sites Conformes X.Y.Z>"
echo "  ${agreste_only}  bumps only Agreste"
echo "  ${with_sc}  also moves the Sites Conformes version"
echo

while true; do
    read -r -p "New version: " raw
    version="$(printf '%s' "$raw" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//;s/^v//')"
    if [ -z "$version" ]; then
        echo "Cancelled."
        exit 0
    fi
    if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+-[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "Version must look like ${agreste_only} (Agreste X.Y.Z-Sites Conformes X.Y.Z)." >&2
        continue
    fi
    if [ "$version" = "$current" ]; then
        echo "That is already the current version." >&2
        continue
    fi
    break
done

echo
echo "About to commit \"Bump version to ${version}\" on main-agreste, push, and open a PR into production-agreste."
read -r -p "Continue? [y/N] " answer
case "$answer" in
    y|Y|yes|YES) ;;
    *)
        echo "Cancelled."
        exit 0
        ;;
esac

require_clean_worktree

open_prs="$(gh pr list --repo "$repo_url" --base production-agreste --head main-agreste --state open --json number --jq 'length')"
if [ "$open_prs" != "0" ]; then
    echo "ERROR: an open pull request from main-agreste into production-agreste already exists." >&2
    gh pr list --repo "$repo_url" --base production-agreste --head main-agreste --state open
    exit 1
fi

git checkout main-agreste
git pull --ff-only
printf '%s\n' "$version" > agreste_version.txt
git add agreste_version.txt
git commit -m "Bump version to ${version}"
git push origin main-agreste

pr_url="$(gh pr create --repo "$repo_url" --base production-agreste --head main-agreste --title "v${version}" --body "")"
printf '%s\n' "$pr_url"
echo "Merging this pull request into production-agreste creates the GitHub release and tag."
