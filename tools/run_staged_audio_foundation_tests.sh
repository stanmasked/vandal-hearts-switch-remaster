#!/usr/bin/env bash
# Independent host checks for audio files staged beside existing MAP02.
# Intentionally does not touch the main Makefile or alter tactical main.c.
set -euo pipefail

compiler="${1:-gcc}"
case "$compiler" in
  gcc|clang) ;;
  *) echo "Unsupported compiler: $compiler" >&2; exit 2 ;;
esac

export ASAN_OPTIONS="detect_leaks=1:halt_on_error=1"
export UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"
flags=(-std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined
       -fno-sanitize-recover=all -fno-omit-frame-pointer -Isource)
output_dir="$(mktemp -d)"
trap 'rm -rf "$output_dir"' EXIT

check() {
  local test_name="$1"
  shift
  echo "=== $compiler: $test_name ==="
  "$compiler" "${flags[@]}" "tests/$test_name.c" "$@" -lm \
    -o "$output_dir/$test_name"
  "$output_dir/$test_name"
}

seq_spu=(
  source/vh_native_seq.c
  source/vh_native_spu.c
  source/vh_spu_reverb.c
  source/vh_spu_gaussian.c
  source/vh_audio_stream.c
)

check test_vh_audio_stream source/vh_audio_stream.c
check test_vh_audio_resample source/vh_audio_resample.c
check test_vh_native_seq "${seq_spu[@]}"
check test_vh_spu_reverb source/vh_spu_reverb.c source/vh_native_spu.c \
  source/vh_spu_gaussian.c source/vh_audio_stream.c
check test_vh_native_spu source/vh_native_spu.c source/vh_spu_reverb.c \
  source/vh_spu_gaussian.c source/vh_spu_adpcm.c source/vh_audio_stream.c
check test_vh_native_vab source/vh_native_vab.c "${seq_spu[@]}" \
  source/vh_spu_adpcm.c
check test_vh_music_scene source/vh_music_scene.c "${seq_spu[@]}"
check test_vh_music_scene_soak source/vh_music_scene.c "${seq_spu[@]}" \
  source/vh_audio_resample.c

echo "PASS: $compiler audio foundation host regression suite (8 executables)"
