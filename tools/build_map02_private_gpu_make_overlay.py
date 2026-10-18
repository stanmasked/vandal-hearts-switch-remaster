#!/usr/bin/env python3
"""Compile two source-pinned MAP02 backend objects from Linux sealed inputs.

The original Makefile, generated Make overlay and both generated C files
are sealed in anonymous memfd inodes before GNU Make starts. This narrows
the audit-to-compiler pathname race for these four inputs only; headers,
compiler/toolchain and the wider checkout are NOT execution-attested.
"""
import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from tools import prepare_map02_private_gpu_make_overlay as builder
from tools import verify_map02_private_gpu_make_overlay as auditor

MAX_OBJECT_BYTES = 64 * 1024 * 1024
SEALS = (fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW |
         fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)


def _sealed_fd(content, label):
    """Return an anonymous, immutable file; never fall back to a path."""
    fd = os.memfd_create(label, flags=os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        pos = 0
        while pos < len(content):
            n = os.write(fd, content[pos:])
            if n <= 0:
                raise OSError("unable to write sealed MAP02 source")
            pos += n
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, SEALS)
        if fcntl.fcntl(fd, fcntl.F_GET_SEALS) & SEALS != SEALS:
            raise ValueError("MAP02 source sealing was incomplete")
        os.lseek(fd, 0, os.SEEK_SET)
        return fd
    except BaseException:
        os.close(fd)
        raise


def compile_overlay(upstream, output, manifest, *, build_dir):
    """Fail closed if the replayed payload differs from the sealed Make input."""
    if sys.platform != "linux" or not hasattr(os, "memfd_create"):
        raise ValueError("Linux sealed memfd support is required")
    if not re.fullmatch(r"build-map02-[A-Za-z0-9_-]+", build_dir):
        raise ValueError("isolated MAP02 build directory name invalid")
    upstream = Path(upstream).resolve(strict=True)
    output = Path(output).absolute()
    manifest = Path(manifest).absolute()
    pc = upstream / "platform" / "pc"
    if not pc.is_dir() or (pc / build_dir).exists() or (pc / build_dir).is_symlink():
        raise ValueError("MAP02 isolated build directory missing parent or already exists")
    make = shutil.which("make", path="/usr/bin:/bin")
    if not make:
        raise ValueError("GNU Make unavailable")
    before = auditor.replay(upstream, output, manifest)
    payloads = {}
    for name in (builder.GENERATED_MAKE, builder.GENERATED_GPU,
                 builder.GENERATED_RASTER):
        payload = auditor._stable_regular_bytes(
            output / name, max_bytes=auditor.MAX_GENERATED_BYTES)
        if hashlib.sha256(payload).hexdigest() != before["generated_sha256"][name]:
            raise ValueError("MAP02 generated source changed before sealing")
        payloads[name] = payload
    original_make = auditor._stable_regular_bytes(
        upstream / builder.MAKE_REL, max_bytes=auditor.MAX_GENERATED_BYTES)
    if builder.git_blob_sha1(original_make) != builder.PINNED_BLOB_SHA1[builder.MAKE_REL]:
        raise ValueError("MAP02 pinned Makefile changed before sealing")
    # Reconfirm the original paths before spawning Make, but compile only
    # from our sealed byte snapshots after this point.
    if auditor.replay(upstream, output, manifest) != before:
        raise ValueError("MAP02 independent replay changed before compilation")
    with ExitStack() as stack:
        files = {}
        for name, payload in (
            ("original-make", original_make),
            (builder.GENERATED_MAKE, payloads[builder.GENERATED_MAKE]),
            (builder.GENERATED_GPU, payloads[builder.GENERATED_GPU]),
            (builder.GENERATED_RASTER, payloads[builder.GENERATED_RASTER]),
        ):
            fd = _sealed_fd(payload, "vh-map02-" + name)
            stack.callback(os.close, fd)
            files[name] = fd
        def fd_path(name):
            return "/proc/self/fd/" + str(files[name])

        base = [
            make, "--no-print-directory",
            "-f", fd_path("original-make"),
            "-f", fd_path(builder.GENERATED_MAKE),
            "REGION=us", "BUILD_DIR=" + build_dir,
        ]
        clean_env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}

        def run_make(args):
            try:
                result = subprocess.run(
                    args, cwd=pc, env=clean_env,
                    pass_fds=tuple(files.values()), capture_output=True,
                    timeout=180, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ValueError("MAP02 sealed Make execution failed") from exc
            if result.returncode:
                raise ValueError("MAP02 sealed Make compilation failed")

        # Header expansion is a separate, audited boundary. Unlike the C
        # compiler, the preprocessor must still read headers from the
        # checkout; its complete output is sealed before object compilation.
        with tempfile.TemporaryDirectory(prefix="vh-map02-preprocessed-") as temp:
            run_make(base + [
                "VH_MAP02_PRIVATE_GPU_C=" + fd_path(builder.GENERATED_GPU),
                "VH_MAP02_PRIVATE_RASTER_C=" + fd_path(builder.GENERATED_RASTER),
                "VH_MAP02_PRIVATE_PREPROCESS_DIR=" + temp,
                "map02-private-gpu-preprocess",
            ])
            preprocessed = {}
            for unit in ("libgpu", "pc_raster"):
                source = auditor._stable_regular_bytes(
                    Path(temp) / (unit + ".i"),
                    max_bytes=MAX_OBJECT_BYTES)
                if not source:
                    raise ValueError("MAP02 preprocessor emitted an empty source")
                preprocessed[unit] = hashlib.sha256(source).hexdigest()
                files[unit + "-preprocessed"] = _sealed_fd(
                    source, "vh-map02-preprocessed-" + unit)
                stack.callback(os.close, files[unit + "-preprocessed"])

        run_make(base + [
            "VH_MAP02_PRIVATE_INPUT_LANG=cpp-output",
            "VH_MAP02_PRIVATE_GPU_C=" + fd_path("libgpu-preprocessed"),
            "VH_MAP02_PRIVATE_RASTER_C=" + fd_path("pc_raster-preprocessed"),
            "map02-private-gpu-objects",
        ])
    after = auditor.replay(upstream, output, manifest)
    if after != before:
        raise ValueError("MAP02 private overlay changed during sealed Make build")
    hashes = {}
    for filename in ("libgpu.o", "pc_raster.o"):
        payload = auditor._stable_regular_bytes(
            pc / build_dir / filename, max_bytes=MAX_OBJECT_BYTES)
        if not payload:
            raise ValueError("MAP02 sealed Make produced an empty object")
        hashes[filename] = hashlib.sha256(payload).hexdigest()
    return {
        "schema": "vh.map02.sealed-gpu-make-objects.v1",
        "pinned_public_pc_commit": builder.PINNED_UPSTREAM_REF,
        "generated_sha256": before["generated_sha256"],
        "makefile_sha256": hashlib.sha256(original_make).hexdigest(),
        "objects_sha256": hashes,
        "sealed_inputs": 6,
        "preprocessed_sha256": preprocessed,
        "compiled_from_sealed_preprocessor_output": True,
        "verified_source_bytes_used_for_compilation": True,
        "private_game_assets_read": False,
        "retail_map02_gameplay_captured": False,
        "native_process_to_gpu_log_causality_verified": False,
        "all_headers_sealed": False,
        "compiler_execution_attested": False,
        "hd_replacement_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_public_pc_checkout", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--build-dir", required=True)
    args = parser.parse_args()
    try:
        result = compile_overlay(
            args.pinned_public_pc_checkout, args.output_dir,
            args.manifest, build_dir=args.build_dir)
    except (OSError, ValueError, UnicodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
