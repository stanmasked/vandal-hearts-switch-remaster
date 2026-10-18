#!/usr/bin/env python3
"""Consume final MAP02 objects through immutable, hash-checked Linux memfds.

The primary Make receipt binds output bytes; after verifying it, binutils
see only sealed snapshots. The final linked pathname remains mutable and
must be hash-checked by any later consumer.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from tools import build_map02_private_gpu_make_overlay as builder
from tools import verify_map02_private_gpu_make_overlay as auditor

OBJECT_NAMES = ("libgpu.o", "pc_raster.o")
SYMBOLS = ("VH_CaptureEvent", "VH_Map02PixelScopeSet",
           "VH_Map02PixelScopeClear", "VH_PixelSampleRecord",
           "VH_Map02SkipAt", "VH_Map02SpanObserve")
RASTER_MARKERS = ("VH_MAP02_PUTPIXEL_X2", "VH_MAP02_PUTPIXEL_Y2")
LINKED_NAME = "gpu-two-word-dda.o"


def _elf_profile(content):
    if (len(content) < 20 or content[:4] != b"\x7fELF" or
            content[4] not in (1, 2) or content[5] != 1 or
            content[16:18] != b"\x01\x00"):
        raise ValueError("MAP02 object is not a little-endian relocatable ELF")
    return content[4], content[18:20]


def _run_binary(tool, args, *, pass_fds=(), cwd=None):
    executable = shutil.which(tool, path="/usr/bin:/bin")
    if not executable:
        raise ValueError("MAP02 object analysis tool unavailable")
    try:
        result = subprocess.run(
            [executable, *args], cwd=cwd,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
            pass_fds=pass_fds, capture_output=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("MAP02 sealed object consumer execution failed") from exc
    if result.returncode or len(result.stdout) > 4 * 1024 * 1024:
        raise ValueError("MAP02 sealed object consumer rejected tool execution")
    return result.stdout


def verify_and_link(pc_dir, build_dir, report, *, linked_name=LINKED_NAME):
    """Feed SHA-pinned immutable .o images to nm/strings/ld and publish once."""
    if sys.platform != "linux" or not hasattr(os, "memfd_create"):
        raise ValueError("MAP02 immutable object consumption requires Linux memfd")
    if not re.fullmatch(r"build-map02-[A-Za-z0-9_-]+", build_dir):
        raise ValueError("MAP02 object build directory name invalid")
    if linked_name != LINKED_NAME:
        raise ValueError("MAP02 linked object output name invalid")
    pc = Path(pc_dir).resolve(strict=True)
    directory = pc / build_dir
    if directory.is_symlink() or not directory.is_dir() or directory.resolve() != directory:
        raise ValueError("MAP02 object build directory is not ordinary")
    if not isinstance(report, dict) or report.get("schema") != "vh.map02.sealed-gpu-make-objects.v1":
        raise ValueError("MAP02 primary build receipt schema invalid")
    for field in ("actual_make_children_kernel_attested",
                  "kernel_make_primary_executables_match_sha256",
                  "compiled_from_sealed_preprocessor_output"):
        if report.get(field) is not True:
            raise ValueError("MAP02 primary object provenance not confirmed")
    if report.get("hd_replacement_authorized") is not False:
        raise ValueError("MAP02 HD gate must remain disabled")
    expected = report.get("objects_sha256")
    if not isinstance(expected, dict) or set(expected) != set(OBJECT_NAMES):
        raise ValueError("MAP02 object receipt inventory invalid")
    for name in OBJECT_NAMES:
        if not isinstance(expected[name], str) or not re.fullmatch(r"[0-9a-f]{64}", expected[name]):
            raise ValueError("MAP02 object receipt hash invalid")
    output = directory / linked_name
    if output.exists() or output.is_symlink():
        raise ValueError("MAP02 linked output already exists")
    with ExitStack() as stack:
        descriptors, profiles = [], []
        for name in OBJECT_NAMES:
            content = auditor._stable_regular_bytes(
                directory / name, max_bytes=builder.MAX_OBJECT_BYTES)
            if not content or hashlib.sha256(content).hexdigest() != expected[name]:
                raise ValueError("MAP02 compiled object SHA-256 differs from primary receipt")
            profiles.append(_elf_profile(content))
            fd = builder._sealed_fd(content, "vh-map02-verified-" + name)
            stack.callback(os.close, fd)
            descriptors.append(fd)
        if profiles[0] != profiles[1]:
            raise ValueError("MAP02 compiled objects have inconsistent ELF ABI")
        inputs = ["/proc/self/fd/" + str(fd) for fd in descriptors]
        symbols = _run_binary("nm", ["-a", *inputs], pass_fds=tuple(descriptors))
        for symbol in SYMBOLS:
            if symbol.encode("ascii") not in symbols:
                raise ValueError("MAP02 required GPU symbol absent from sealed objects")
        strings = _run_binary("strings", [inputs[1]], pass_fds=tuple(descriptors))
        for marker in RASTER_MARKERS:
            if marker.encode("ascii") not in strings:
                raise ValueError("MAP02 DDA marker absent from sealed raster object")
        with tempfile.TemporaryDirectory(prefix=".vh-map02-link-", dir=directory) as tmp:
            stage = Path(tmp) / linked_name
            _run_binary("ld", ["-r", "-o", str(stage), *inputs],
                        pass_fds=tuple(descriptors), cwd=directory)
            linked = auditor._stable_regular_bytes(stage, max_bytes=builder.MAX_OBJECT_BYTES)
            if not linked or _elf_profile(linked) != profiles[0]:
                raise ValueError("MAP02 sealed linked object ELF profile invalid")
            linked_sha = hashlib.sha256(linked).hexdigest()
            try:
                os.link(stage, output, follow_symlinks=False)
            except FileExistsError as exc:
                raise ValueError("MAP02 linked output claimed before publication") from exc
            if hashlib.sha256(auditor._stable_regular_bytes(
                    output, max_bytes=builder.MAX_OBJECT_BYTES)).hexdigest() != linked_sha:
                raise ValueError("MAP02 linked output changed during publication")
    return {
        "schema": "vh.map02.sealed-linked-gpu-object.v1",
        "source_objects_sha256": expected,
        "sealed_object_inputs": 2,
        "source_objects_match_primary_receipt": True,
        "binutils_consumed_sealed_objects": True,
        "linked_object_sha256": linked_sha,
        "linked_output_path_stays_mutable": True,
        "hd_replacement_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pc-dir", required=True)
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--primary-receipt", required=True)
    args = parser.parse_args()
    path = Path(args.primary_receipt)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("MAP02 primary receipt path invalid")
    report = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps(verify_and_link(args.pc_dir, args.build_dir, report),
                     sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
