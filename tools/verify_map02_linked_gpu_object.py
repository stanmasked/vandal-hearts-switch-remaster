#!/usr/bin/env python3
"""Recheck published MAP02 linked ELF and consume only its sealed snapshot.

Hash verification alone does not prevent a pathname swap after the check.
This tool seals the verified linked bytes in memfd before invoking binutils.
The published disk pathname itself remains mutable for any future consumer.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from tools import build_map02_private_gpu_make_overlay as builder
from tools import consume_map02_sealed_gpu_objects as linker
from tools import verify_map02_private_gpu_make_overlay as auditor


def verify_and_inspect(pc_dir, build_dir, primary, linked):
    if sys.platform != "linux" or not hasattr(os, "memfd_create"):
        raise ValueError("MAP02 linked ELF inspection requires Linux memfd")
    if not re.fullmatch(r"build-map02-[A-Za-z0-9_-]+", build_dir):
        raise ValueError("MAP02 linked object build directory invalid")
    pc = Path(pc_dir).resolve(strict=True)
    directory = pc / build_dir
    if directory.is_symlink() or not directory.is_dir() or directory.resolve() != directory:
        raise ValueError("MAP02 linked object directory is not ordinary")
    if (not isinstance(primary, dict) or
            primary.get("schema") != "vh.map02.sealed-gpu-make-objects.v1"):
        raise ValueError("MAP02 primary object receipt invalid")
    if (not isinstance(linked, dict) or
            linked.get("schema") != "vh.map02.sealed-linked-gpu-object.v1"):
        raise ValueError("MAP02 linked object receipt schema invalid")
    for key in ("actual_make_children_kernel_attested",
                "kernel_make_primary_executables_match_sha256",
                "compiled_from_sealed_preprocessor_output"):
        if primary.get(key) is not True:
            raise ValueError("MAP02 primary object provenance not confirmed")
    for key in ("source_objects_match_primary_receipt",
                "binutils_consumed_sealed_objects",
                "linked_output_path_stays_mutable"):
        if linked.get(key) is not True:
            raise ValueError("MAP02 linked object provenance not confirmed")
    if (primary.get("hd_replacement_authorized") is not False or
            linked.get("hd_replacement_authorized") is not False):
        raise ValueError("MAP02 HD gate must remain disabled")
    originals = primary.get("objects_sha256")
    if (not isinstance(originals, dict) or
            set(originals) != set(linker.OBJECT_NAMES) or
            any(not isinstance(value, str) or
                re.fullmatch(r"[0-9a-f]{64}", value) is None
                for value in originals.values()) or
            linked.get("source_objects_sha256") != originals or
            type(linked.get("sealed_object_inputs")) is not int or
            linked["sealed_object_inputs"] != 2):
        raise ValueError("MAP02 linked object source hash binding invalid")
    sha = linked.get("linked_object_sha256")
    if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{64}", sha) is None:
        raise ValueError("MAP02 linked object receipt hash invalid")
    content = auditor._stable_regular_bytes(
        directory / linker.LINKED_NAME, max_bytes=builder.MAX_OBJECT_BYTES)
    if not content or hashlib.sha256(content).hexdigest() != sha:
        raise ValueError("MAP02 published linked object SHA-256 differs from receipt")
    linker._elf_profile(content)
    with ExitStack() as stack:
        fd = builder._sealed_fd(content, "vh-map02-linked-consumer")
        stack.callback(os.close, fd)
        fd_path = "/proc/self/fd/" + str(fd)
        output = linker._run_binary("nm", ["--defined-only", "-P", fd_path],
                                    pass_fds=(fd,))
        defined = {line.split()[0] for line in output.splitlines() if line.split()}
        missing = set(name.encode("ascii") for name in linker.SYMBOLS) - defined
        if missing:
            raise ValueError("MAP02 linked ELF required GPU symbols absent")
        strings = linker._run_binary("strings", [fd_path], pass_fds=(fd,))
        for marker in linker.RASTER_MARKERS:
            if marker.encode("ascii") not in strings:
                raise ValueError("MAP02 linked ELF DDA marker absent")
    return {
        "schema": "vh.map02.sealed-linked-gpu-consumption.v1",
        "source_objects_sha256": originals,
        "linked_object_sha256": sha,
        "linked_hash_verified_against_receipt": True,
        "linked_bytes_sealed_before_binutils": True,
        "linked_symbols_and_dda_markers_checked": True,
        "linked_output_path_stays_mutable": True,
        "hd_replacement_authorized": False,
    }


def _read_receipt(path):
    file = Path(path)
    if file.is_symlink() or not file.is_file() or file.stat().st_size > 1024 * 1024:
        raise ValueError("MAP02 object receipt file path invalid")
    return json.loads(file.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pc-dir", required=True)
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--primary-receipt", required=True)
    parser.add_argument("--linked-receipt", required=True)
    args = parser.parse_args()
    print(json.dumps(verify_and_inspect(
        args.pc_dir, args.build_dir,
        _read_receipt(args.primary_receipt),
        _read_receipt(args.linked_receipt)), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
