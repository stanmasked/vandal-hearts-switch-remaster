#!/usr/bin/env bash
# Opt-in local build of the pinned upstream PC port.
# Game executable and font/BIOS input stay outside version control.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
upstream_dir="${VH_UPSTREAM_DIR:-$repo_root/upstream}"
build_dir="${VH_UPSTREAM_BUILD_DIR:-$repo_root/build-upstream-local}"

: "${VH_PSX_EXE:?Set VH_PSX_EXE to your own matching regional PS-X executable}"
: "${VH_KROM_SOURCE:?Set VH_KROM_SOURCE to your own KROMDAT.BIN or compatible BIOS font source}"

for input in "$VH_PSX_EXE" "$VH_KROM_SOURCE"; do
  if [[ ! -f "$input" || ! -r "$input" ]]; then
    printf 'Required input is not a readable file: %s\n' "$input" >&2
    exit 2
  fi
done
if [[ ! -f "$upstream_dir/platform/pc/CMakeLists.txt" ]]; then
  printf 'Pinned upstream source not found at %s\n' "$upstream_dir" >&2
  printf 'Check out HalmyLyseas/VandalHearts-PcPort at audited revision 14552fffa0e0b47e02b57592e274fc6e7a649923.\n' >&2
  exit 2
fi

cmake -S "$upstream_dir/platform/pc" -B "$build_dir" -G Ninja \
  -DVH_PSX_EXE="$VH_PSX_EXE" \
  -DVH_KROM_SOURCE="$VH_KROM_SOURCE" \
  -DVH_WEBP=OFF -DVH_HDVIDEO=OFF
cmake --build "$build_dir" --target vandalhearts_pc --parallel "${VH_BUILD_JOBS:-2}"
printf '\nBuild completed. Output: %s/vandalhearts_pc\n' "$build_dir"
printf 'This is a host PC build, not a Switch-targeted build or runtime validation.\n'
