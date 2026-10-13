#!/usr/bin/env bash
set -euo pipefail

# Fetch the audited upstream source into a local cache for inspection.
# This script does not build or execute upstream code and does not fetch game discs/assets.
readonly UPSTREAM_URL="https://github.com/HalmyLyseas/VandalHearts-PcPort.git"
readonly UPSTREAM_COMMIT="14552fffa0e0b47e02b57592e274fc6e7a649923"
destination="${1:-.cache/upstream-pc-port}"

if [[ -e "$destination" ]]; then
    if [[ ! -d "$destination/.git" ]]; then
        echo "Error: destination exists but is not a Git repository: $destination" >&2
        exit 2
    fi
    git -C "$destination" fetch --depth=1 "$UPSTREAM_URL" "$UPSTREAM_COMMIT"
    git -C "$destination" checkout --detach FETCH_HEAD
else
    mkdir -p "$(dirname "$destination")"
    git init "$destination" >/dev/null
    git -C "$destination" fetch --depth=1 "$UPSTREAM_URL" "$UPSTREAM_COMMIT"
    git -C "$destination" checkout --detach FETCH_HEAD
fi

actual="$(git -C "$destination" rev-parse HEAD)"
if [[ "$actual" != "$UPSTREAM_COMMIT" ]]; then
    echo "Error: expected upstream commit $UPSTREAM_COMMIT, got $actual" >&2
    exit 3
fi

printf 'Fetched audited upstream revision %s into %s\n' "$actual" "$destination"
printf 'Source is for inspection only; this does not imply Switch compatibility.\n'
