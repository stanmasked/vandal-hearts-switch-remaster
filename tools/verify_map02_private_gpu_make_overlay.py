#!/usr/bin/env python3
"""Independent read-only replay of the private MAP02 two-word GPU/DDA Make overlay.

Recreate every generated C/Make byte from the pinned public PC source;
compare the private preparation receipt, all on-disk outputs and their
stable file identities. Does not execute Make, the game or user assets.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

from tools import prepare_map02_private_gpu_make_overlay as builder

MAX_MANIFEST_BYTES = 32768
MAX_GENERATED_BYTES = 64 * 1024 * 1024
IDENTITY_FIELDS = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")


def _identity(st):
    return tuple(getattr(st, key) for key in IDENTITY_FIELDS)


def _stable_regular_bytes(path, *, max_bytes, dir_fd=None):
    """Read one immutable regular inode; reject FIFO, symlink and replacement."""
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
    fd = os.open(path, flags, dir_fd=dir_fd)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode)
                or before.st_size < 0 or before.st_size > max_bytes):
            raise ValueError("private Make witness must be a bounded regular file")
        if _identity(os.stat(path, dir_fd=dir_fd, follow_symlinks=False)) != _identity(before):
            raise ValueError("private Make witness changed before reading")
        chunks = []
        remaining = before.st_size
        while remaining:
            part = os.read(fd, min(1024 * 1024, remaining))
            if not part:
                raise ValueError("private Make witness was truncated")
            chunks.append(part)
            remaining -= len(part)
        if (os.read(fd, 1)
                or _identity(os.fstat(fd)) != _identity(before)
                or _identity(os.stat(path, dir_fd=dir_fd, follow_symlinks=False))
                != _identity(before)):
            raise ValueError("private Make witness changed during reading")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _unique_object(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError("private Make receipt contains duplicate JSON keys")
        result[k] = v
    return result


def replay(upstream, output, manifest):
    upstream = Path(upstream).resolve(strict=True)
    output = Path(output).absolute()
    manifest = Path(manifest).absolute()
    if not upstream.is_dir():
        raise ValueError("pinned public PC checkout missing")
    real_output = output.resolve(strict=True)
    if (output != real_output or not real_output.is_dir()
            or upstream == real_output or upstream in real_output.parents):
        raise ValueError("private Make overlay directory invalid or redirected")
    if (output == manifest or manifest.parent == output
            or upstream == manifest or upstream in manifest.parents):
        raise ValueError("private Make receipt must live outside generated checkout")
    builder.make_overlay(output)  # Validate the same restricted Make path.
    builder._require_pinned_clean_checkout(upstream)

    sources = {}
    expected_git = {
        builder.MAKE_REL: builder.PINNED_BLOB_SHA1[builder.MAKE_REL],
        builder.GPU_REL: builder.GPU_BLOB,
        builder.RASTER_REL: builder.RASTER_BLOB,
    }
    for rel, expected in expected_git.items():
        original = upstream / rel
        content = _stable_regular_bytes(original, max_bytes=MAX_GENERATED_BYTES)
        if builder.git_blob_sha1(content) != expected:
            raise ValueError("private Make source is not the pinned Git blob")
        sources[rel] = content
    original_make = sources[builder.MAKE_REL].decode("utf-8")
    graph = (
        "default: $(GAME_O_FILES) $(BACKEND_OBJS)",
        "objs: default $(DATA_OBJS)", "link: $(DATA_OBJS)",
        "$(GAME_O_FILES) $(BACKEND_OBJS) $(DATA_OBJS)",
        "libgpu.c pc_raster.c",
        "$(BUILD_DIR)/libgpu.o: src/libgpu.c",
        "$(BUILD_DIR)/pc_raster.o: src/pc_raster.c",
    )
    if not all(a in original_make for a in
               (*builder.REQUIRED_MAKE_ANCHORS, *graph)):
        raise ValueError("pinned original PC Make graph differs")
    generated = {
        builder.GENERATED_GPU:
            builder.multi_gpu(sources[builder.GPU_REL].decode("utf-8")).encode("utf-8"),
        builder.GENERATED_RASTER:
            builder.instrument_span(builder.instrument_vertical(
                builder.instrument_raster_skips(builder.multi_raster(
                    sources[builder.RASTER_REL].decode("utf-8"))))).encode("utf-8"),
        builder.GENERATED_MAKE: builder.make_overlay(output).encode("utf-8"),
    }
    expected_report = {
        "schema": "vh.map02.private-native-two-word-dda-overlay.v1",
        "pinned_public_pc_commit": builder.PINNED_UPSTREAM_REF,
        "source_pinned": True,
        "full_checkout_head_verified": True,
        "full_tracked_checkout_clean": True,
        "original_checkout_modified": False,
        "native_gpu_two_word_and_dda_in_same_make_objects": True,
        "source_sha256": {p: hashlib.sha256(data).hexdigest()
                          for p, data in sorted(sources.items())},
        "generated_sha256": {p: hashlib.sha256(data).hexdigest()
                             for p, data in sorted(generated.items())},
        "required_compiler_defines": list(builder.FLAGS),
        "required_native_symbols": list(builder.SYMBOLS),
        "output_files": sorted(generated),
        "isolated_build_directory_required": True,
        "game_assets_included": False,
        "retail_map02_gameplay_captured": False,
        "native_process_to_gpu_log_causality_verified": False,
        "hd_replacement_authorized": False,
    }
    # Anchor every generated-file operation to the same opened directory;
    # pathname-only checks can silently follow a swapped overlay directory.
    directory_flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                       | getattr(os, "O_NOFOLLOW", 0)
                       | getattr(os, "O_CLOEXEC", 0))
    directory_fd = os.open(output, directory_flags)
    try:
        directory_before = os.fstat(directory_fd)
        if (not stat.S_ISDIR(directory_before.st_mode)
                or _identity(os.stat(output, follow_symlinks=False))
                != _identity(directory_before)):
            raise ValueError("private Make overlay directory changed before reading")
        if sorted(os.listdir(directory_fd)) != sorted(generated):
            raise ValueError("private Make output files differ from expected inventory")
        for name, wanted in generated.items():
            if _stable_regular_bytes(name, max_bytes=MAX_GENERATED_BYTES,
                                     dir_fd=directory_fd) != wanted:
                raise ValueError("private Make generated file differs from pinned source")
        receipt = json.loads(
            _stable_regular_bytes(manifest, max_bytes=MAX_MANIFEST_BYTES),
            object_pairs_hook=_unique_object,
        )
        if type(receipt) is not dict or receipt != expected_report:
            raise ValueError("private Make preparation receipt differs from regenerated sources")
        if (_identity(os.fstat(directory_fd)) != _identity(directory_before)
                or _identity(os.stat(output, follow_symlinks=False))
                != _identity(directory_before)):
            raise ValueError("private Make overlay directory changed during replay")
    finally:
        os.close(directory_fd)
    return {
        "schema": "vh.map02.private-native-make-overlay-replay.v1",
        "pinned_public_pc_commit": builder.PINNED_UPSTREAM_REF,
        "full_checkout_head_verified": True,
        "full_tracked_checkout_clean": True,
        "generated_files_checked": len(generated),
        "receipt_exactly_replayed": True,
        "generated_sha256": expected_report["generated_sha256"],
        "private_game_assets_read": False,
        "private_game_executable_built": False,
        "retail_map02_gameplay_captured": False,
        "native_process_to_gpu_log_causality_verified": False,
        "hd_replacement_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_public_pc_checkout", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = replay(args.pinned_public_pc_checkout, args.output_dir, args.manifest)
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
