#!/usr/bin/env bash
# Private, one-command, read-only RU MAP02 source check for macOS.
set -euo pipefail
umask 077

if (( $# < 1 || $# > 2 )); then
  echo 'Usage: bash tools/run_local_map02_ru_owned_disc.sh "/path/Nintendo Switch Remakes — Originals" [private-v10.1-receipt.json]' >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
originals_root="$1"
image="$originals_root/Vandal Hearts/Vandal_Hearts_(RU)_v1.6.bin"
receipt="${2:-$HOME/Documents/NintendoSwitchRemakesAudit/map02_ru_source_reconciliation.json}"
output_dir="$HOME/Documents/NintendoSwitchRemakesAudit/private-map02"
output="$output_dir/map02_ru_owned_disc_verified.json"

if [[ ! -f "$image" || -L "$image" ]]; then
  echo 'BLOCKED: the pinned RU v1.6 BIN must exist as a regular, non-symlinked file.' >&2
  exit 1
fi
if [[ ! -f "$receipt" || -L "$receipt" ]]; then
  echo 'BLOCKED: the local v10.1 reconciliation report is missing or a symlink.' >&2
  exit 1
fi
if [[ -e "$output" || -L "$output" ]]; then
  echo "BLOCKED: report already exists; will not overwrite: $output" >&2
  exit 1
fi
mkdir -p -m 700 "$output_dir"
if [[ -L "$output_dir" ]]; then
  echo 'BLOCKED: private report directory must not be a symlink.' >&2
  exit 1
fi

tmp="$(mktemp "$output_dir/.map02_ru_owned_disc.XXXXXXXX")"
trap 'rm -f "$tmp"' EXIT
PYTHONPATH="$repo_root${PYTHONPATH:+:$PYTHONPATH}" python3 -m tools.verify_map02_ru_owned_disc \
  --disc-image "$image" --receipt "$receipt" > "$tmp"
# POSIX hard-link creation fails rather than replacing a concurrent output.
if ! ln "$tmp" "$output"; then
  echo 'BLOCKED: could not publish report without overwrite.' >&2
  exit 1
fi
printf 'PASS: private metadata-only report: %s\n' "$output"
