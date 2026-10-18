#!/usr/bin/env python3
"""Compile two source-pinned MAP02 backend objects from Linux sealed inputs.

The original Makefile, generated Make overlay, both generated C files and
each pinned, source-local Git header are sealed in anonymous Linux memfd
inodes before preprocessing. The two preprocessed C inputs are then sealed
before object compilation. System headers, compiler/toolchain and other
checkout inputs are NOT execution-attested.
"""
import argparse
from contextlib import ExitStack
import ctypes
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


HEADER_LIMIT = 16 * 1024 * 1024


def _tracked_header_blobs(upstream):
    """Read HEAD's tracked header inventory, independent of the mutable index."""
    git = shutil.which("git", path="/usr/bin:/bin")
    if not git:
        raise ValueError("MAP02 pinned header Git inspector unavailable")
    try:
        result = subprocess.run(
            [git, "ls-tree", "-r", "-z", "HEAD", "--",
             "include", "platform/pc/include", "platform/pc/src"],
            cwd=upstream, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
            capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("MAP02 pinned header inventory unavailable") from exc
    if result.returncode or not result.stdout:
        raise ValueError("MAP02 pinned header inventory unavailable")
    headers = {}
    for entry in result.stdout.split(bytes([0])):
        if not entry:
            continue
        try:
            meta, raw_path = entry.split(bytes([9]), 1)
            mode, kind, blob = meta.decode("ascii").split(" ")
            rel = raw_path.decode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise ValueError("MAP02 pinned header inventory malformed") from exc
        if not (rel.startswith(("include/", "platform/pc/include/",
                                "platform/pc/src/"))
                and rel.endswith((".h", ".inc", ".hpp"))):
            continue
        if (kind != "blob" or mode not in ("100644", "100755")
                or rel in headers or not re.fullmatch(r"[A-Za-z0-9_./-]+", rel)
                or any(x in (".", "..") for x in Path(rel).parts)):
            raise ValueError("MAP02 pinned header inventory invalid")
        headers[rel] = blob
    if not headers:
        raise ValueError("MAP02 pinned header inventory empty")
    return headers


def _stage_headers(upstream, stage, files, stack):
    """Expose exact pinned header bytes only through immutable memfd symlinks."""
    digests = {}
    for relative, blob in sorted(_tracked_header_blobs(upstream).items()):
        source = upstream / relative
        for parent in source.parents:
            if parent == upstream:
                break
            if parent.is_symlink():
                raise ValueError("MAP02 pinned header directory redirected")
        content = auditor._stable_regular_bytes(source, max_bytes=HEADER_LIMIT)
        if builder.git_blob_sha1(content) != blob:
            raise ValueError("MAP02 pinned header differs from Git blob")
        key = "header:" + relative
        fd = _sealed_fd(content, "vh-map02-pinned-header")
        stack.callback(os.close, fd)
        files[key] = fd
        dest = stage / relative
        dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        dest.symlink_to("/proc/self/fd/" + str(fd))
        digests[relative] = hashlib.sha256(content).hexdigest()
    return digests


def _recheck_headers(stage, digests, files):
    """Require an exact link inventory backed by the same sealed header FDs."""
    observed = set()
    for current, directories, filenames in os.walk(stage, followlinks=False):
        for directory in directories:
            if (Path(current) / directory).is_symlink():
                raise ValueError("MAP02 staged header inventory changed")
        for filename in filenames:
            file = Path(current) / filename
            relative = file.relative_to(stage).as_posix()
            key = "header:" + relative
            if relative not in digests or key not in files or not file.is_symlink():
                raise ValueError("MAP02 staged header inventory changed")
            fd = files[key]
            if (os.readlink(file) != "/proc/self/fd/" + str(fd)
                    or (os.stat(file).st_dev, os.stat(file).st_ino) !=
                    (os.fstat(fd).st_dev, os.fstat(fd).st_ino)):
                raise ValueError("MAP02 staged header link redirected")
            observed.add(relative)
    if observed != set(digests):
        raise ValueError("MAP02 staged header inventory changed")
    for relative, digest in digests.items():
        fd = files["header:" + relative]
        if fcntl.fcntl(fd, fcntl.F_GET_SEALS) & SEALS != SEALS:
            raise ValueError("MAP02 staged header seal invalid")
        if hashlib.sha256(os.pread(fd, HEADER_LIMIT + 1, 0)).hexdigest() != digest:
            raise ValueError("MAP02 staged header changed during preprocessing")




IN_MUTATION = (0x2 | 0x4 | 0x8 | 0x40 | 0x80 | 0x100 | 0x200 |
               0x400 | 0x800 | 0x2000 | 0x4000 | 0x8000)
IN_ONLYDIR = 0x01000000
IN_DONT_FOLLOW = 0x02000000


def _watch_header_tree(stage):
    """Watch every include directory; refuse races including restored links."""
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        init = libc.inotify_init1
        add = libc.inotify_add_watch
    except AttributeError as exc:
        raise ValueError("MAP02 Linux inotify unavailable") from exc
    init.argtypes, init.restype = [ctypes.c_int], ctypes.c_int
    add.argtypes, add.restype = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32], ctypes.c_int
    fd = init(os.O_NONBLOCK | os.O_CLOEXEC)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "MAP02 inotify initialization failed")
    try:
        count = 0
        for current, directories, names in os.walk(stage, followlinks=False):
            if count >= 512:
                raise ValueError("MAP02 include watch directory limit exceeded")
            if Path(current).is_symlink():
                raise ValueError("MAP02 include directory redirected")
            wd = add(fd, os.fsencode(current), IN_MUTATION | IN_ONLYDIR | IN_DONT_FOLLOW)
            if wd < 0:
                raise OSError(ctypes.get_errno(), "MAP02 include watch installation failed")
            count += 1
        if not count:
            raise ValueError("MAP02 include watch inventory empty")
        return fd, count
    except BaseException:
        os.close(fd)
        raise


def _check_header_watch(fd):
    """A single mutation or an inotify overflow invalidates the build."""
    try:
        events = os.read(fd, 65536)
    except BlockingIOError:
        return
    if events:
        raise ValueError("MAP02 pinned header include paths changed during preprocessing")


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

        # Preprocess against a private byte-verified snapshot of pinned Git
        # headers, never the mutable upstream include/src header directories.
        with (tempfile.TemporaryDirectory(prefix="vh-map02-pinned-headers-") as headers,
              tempfile.TemporaryDirectory(prefix="vh-map02-preprocessed-") as temp):
            snapshot = Path(headers)
            staged_headers = _stage_headers(upstream, snapshot, files, stack)
            _recheck_headers(snapshot, staged_headers, files)
            watch_fd, watched_dirs = _watch_header_tree(snapshot)
            stack.callback(os.close, watch_fd)
            _check_header_watch(watch_fd)
            include_flags = ("-I" + str(snapshot / "platform/pc/include") +
                             " -I" + str(snapshot / "platform/pc/src") +
                             " -I" + str(snapshot / "include"))
            run_make(base + [
                "VH_MAP02_PRIVATE_GPU_C=" + fd_path(builder.GENERATED_GPU),
                "VH_MAP02_PRIVATE_RASTER_C=" + fd_path(builder.GENERATED_RASTER),
                "VH_MAP02_PRIVATE_INCLUDE_FLAGS=" + include_flags,
                "VH_MAP02_PRIVATE_PREPROCESS_DIR=" + temp,
                "map02-private-gpu-preprocess",
            ])
            _check_header_watch(watch_fd)
            _recheck_headers(snapshot, staged_headers, files)
            _check_header_watch(watch_fd)
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
        "sealed_inputs": 6 + len(staged_headers),
        "preprocessed_sha256": preprocessed,
        "pinned_headers_checked": len(staged_headers),
        "pinned_headers_sealed": len(staged_headers),
        "header_include_directory_watches": watched_dirs,
        "header_path_mutations_rejected": True,
        "staged_header_hashes_verified": True,
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
