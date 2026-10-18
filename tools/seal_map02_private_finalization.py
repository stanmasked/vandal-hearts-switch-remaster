#!/usr/bin/env python3
"""Seal/read-only-verify final MAP02 evidence strictly within a private folder.

No original disc/ELF or screen pixels enter the receipt; a positive result
still does not authenticate retail MAP02 gameplay or a host window.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.finalize_map02_private_capture import finalize_private_capture
from tools.publish_map02_blendg1_witness import _private_directory
from tools.verify_map02_cycle_cd_gpu_join import _private_evidence_snapshot
from tools.verify_map02_frame_bundle import fields, number, parse_json

NAME = "map02-postcapture-final-seal.jsonl"
SCHEMA = "vh.map02.postcapture-final-seal.v1"
KEYS = (
    "schema", "gpu_draw_frame", "capture_session_sha256",
    "source_cd_gpu_process_witness_sha256", "process_receipt_sha256",
    "native_vram_png_sha256", "private_pc_preoverlay_rgb24_sha256",
    "verified_draw_primitives", "finalizer_report_sha256",
    "independent_postcapture_recheck_completed",
    "original_map02_rendering_proven", "presented_host_window_authenticated",
    "physical_ps1_equivalence_proven", "game_bytes_uploaded",
)


def _report_payload(report):
    """Canonical binding to an independently reverified *read-only* result."""
    if (report["schema"] != "vh.map02.private-postcapture-finalization.v1" or
            report["private_cd_witness_created"] is not False or
            report["private_native_vram_png_created"] is not False or
            report["independently_verified_cd_gpu_process_and_rgb24_png"]
            is not True or
            report["original_map02_rendering_proven"] is not False or
            report["presented_host_window_authenticated"] is not False or
            report["physical_ps1_equivalence_proven"] is not False or
            report["game_bytes_uploaded"] is not False):
        raise ValueError("MAP02 finalization is not read-only and fully verified")
    raw = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema": SCHEMA,
        "gpu_draw_frame": report["gpu_draw_frame"],
        "capture_session_sha256": report["capture_session_sha256"],
        "source_cd_gpu_process_witness_sha256":
            report["source_cd_gpu_process_witness_sha256"],
        "process_receipt_sha256": report["process_receipt_sha256"],
        "native_vram_png_sha256": report["native_vram_png_sha256"],
        "private_pc_preoverlay_rgb24_sha256":
            report["private_pc_preoverlay_rgb24_sha256"],
        "verified_draw_primitives": report["verified_draw_primitives"],
        "finalizer_report_sha256": hashlib.sha256(raw).hexdigest(),
        "independent_postcapture_recheck_completed": True,
        "original_map02_rendering_proven": False,
        "presented_host_window_authenticated": False,
        "physical_ps1_equivalence_proven": False,
        "game_bytes_uploaded": False,
    }


def _roots(roots, seal_dir):
    directory = _private_directory(seal_dir)
    owned = tuple(_private_directory(path) for path in roots)
    resolved = tuple(p.resolve() for p in (*owned, directory))
    if any(a == b or a in b.parents or b in a.parents
           for i, a in enumerate(resolved) for b in resolved[i + 1:]):
        raise ValueError("MAP02 private seal must be separate from every capture folder")
    return directory


def _identity(info):
    # Stable inode identity: size and timestamps legitimately change on write.
    return (info.st_dev, info.st_ino, info.st_uid, info.st_nlink,
            info.st_mode)


def _complete_identity(info):
    # After fsync, compare complete metadata including size and timestamps.
    return _identity(info) + (info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _dir_identity(info):
    # Directory st_size and timestamps change when a new entry is created.
    return _identity(info)


def _canonical(raw):
    if (raw.count(b"\n") != 1 or not raw.endswith(b"\n") or
            b"\r" in raw):
        raise ValueError("MAP02 sealed completion is not canonical JSONL")
    data = parse_json(raw[:-1], NAME)
    fields(data, KEYS, NAME)
    if raw != (json.dumps(data, sort_keys=True, separators=(",", ":")) +
               "\n").encode("utf-8"):
        raise ValueError("MAP02 final seal is not canonical JSONL")
    if (data["schema"] != SCHEMA or
            data["independent_postcapture_recheck_completed"] is not True or
            any(data[k] is not False for k in (
                "original_map02_rendering_proven",
                "presented_host_window_authenticated",
                "physical_ps1_equivalence_proven", "game_bytes_uploaded"))):
        raise ValueError("MAP02 final seal schema or authenticity flags invalid")
    number(data["gpu_draw_frame"], "final seal frame", 1, 2**32 - 1)
    number(data["verified_draw_primitives"], "sealed draw count", 1, 63)
    for key in KEYS:
        if key.endswith("_sha256"):
            digest = data[key]
            if (type(digest) is not str or len(digest) != 64 or
                    any(ch not in "0123456789abcdef" for ch in digest)):
                raise ValueError("invalid MAP02 final seal digest")
    return data


def _publish(directory, raw):
    """Exclusive, 0600, nofollow; clean only the inode we created."""
    dfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY |
                  os.O_CLOEXEC | os.O_NOFOLLOW)
    fd = -1
    created = None
    try:
        original_dir = os.fstat(dfd)
        if (stat.S_IMODE(original_dir.st_mode) != 0o700 or
                original_dir.st_uid != os.geteuid() or
                _dir_identity(os.stat(directory, follow_symlinks=False)) !=
                _dir_identity(original_dir)):
            raise ValueError("MAP02 private seal output directory changed")
        if tuple(directory.iterdir()):
            raise ValueError("private final-seal directory must start empty")
        fd = os.open(NAME, os.O_RDWR | os.O_CREAT | os.O_EXCL |
                     os.O_CLOEXEC | os.O_NOFOLLOW, 0o600, dir_fd=dfd)
        created = _identity(os.fstat(fd))
        os.fchmod(fd, 0o600)
        created = _identity(os.fstat(fd))
        done = 0
        while done < len(raw):
            n = os.write(fd, raw[done:])
            if n <= 0:
                raise ValueError("incomplete private seal write")
            done += n
        os.fsync(fd)
        completed = os.fstat(fd)
        if (not stat.S_ISREG(completed.st_mode) or
                stat.S_IMODE(completed.st_mode) != 0o600 or
                completed.st_uid != os.geteuid() or
                completed.st_nlink != 1 or completed.st_size != len(raw) or
                _identity(completed) != created or
                os.pread(fd, len(raw), 0) != raw or
                _complete_identity(os.fstat(fd)) !=
                _complete_identity(completed) or
                _complete_identity(os.stat(NAME, dir_fd=dfd,
                                           follow_symlinks=False)) !=
                _complete_identity(completed) or
                _dir_identity(os.stat(directory, follow_symlinks=False)) !=
                _dir_identity(original_dir)):
            raise ValueError("MAP02 private final seal readback/identity differs")
        os.fsync(dfd)
        return _complete_identity(completed), _dir_identity(original_dir)
    except BaseException:
        if created is not None:
            try:
                if _identity(os.stat(NAME, dir_fd=dfd,
                                     follow_symlinks=False)) == created:
                    os.unlink(NAME, dir_fd=dfd)
            except OSError:
                pass
        raise
    finally:
        if fd >= 0:
            os.close(fd)
        os.close(dfd)


def _discard_own_published_seal(directory, file_identity, directory_identity):
    """Best-effort rollback; NEVER delete a replaced or modified inode."""
    fd = -1
    try:
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY |
                     os.O_CLOEXEC | os.O_NOFOLLOW)
        if (_dir_identity(os.fstat(fd)) != directory_identity or
                _dir_identity(os.stat(directory, follow_symlinks=False))
                != directory_identity):
            return
        observed = os.stat(NAME, dir_fd=fd, follow_symlinks=False)
        if (not stat.S_ISREG(observed.st_mode) or
                _complete_identity(observed) != file_identity):
            return
        os.unlink(NAME, dir_fd=fd)
        os.fsync(fd)
    except OSError:
        # Preserve uncertain evidence instead of risking deletion of a
        # foreign inode. The caller still reports finalization failure.
        pass
    finally:
        if fd >= 0:
            os.close(fd)


def _require_published_identity(directory, file_identity, directory_identity):
    """Reject replacement of the published receipt, even with identical bytes."""
    dfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY |
                  os.O_CLOEXEC | os.O_NOFOLLOW)
    fd = -1
    try:
        if (_dir_identity(os.fstat(dfd)) != directory_identity or
                _dir_identity(os.stat(directory, follow_symlinks=False))
                != directory_identity):
            raise ValueError("MAP02 final seal directory changed after publication")
        fd = os.open(NAME, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC |
                     os.O_NOFOLLOW, dir_fd=dfd)
        observed = os.fstat(fd)
        if (not stat.S_ISREG(observed.st_mode) or
                _complete_identity(observed) != file_identity or
                _complete_identity(os.stat(NAME, dir_fd=dfd,
                                           follow_symlinks=False))
                != file_identity):
            raise ValueError("MAP02 final seal inode changed after publication")
    finally:
        if fd >= 0:
            os.close(fd)
        os.close(dfd)


def _check(source, native, scoped, handoff, cycle, preview, rgb,
           owned_game, upstream, binary, seal_directory, frame,
           compiler):
    frame = number(frame, "MAP02 seal target frame", 1, 2**32 - 1)
    directory = _roots(
        (source, native, scoped, handoff, cycle, preview, rgb),
        seal_directory)
    report = finalize_private_capture(
        source, native, scoped, handoff, cycle, preview, rgb,
        owned_game, upstream, binary, frame=frame, compiler=compiler,
        complete_missing=False)
    expected = _report_payload(report)
    if expected["gpu_draw_frame"] != frame:
        raise ValueError("MAP02 final seal frame changed")
    return directory, expected


def seal_final_capture(source, native, scoped, handoff, cycle, preview, rgb,
                       owned_game, upstream, binary, seal_directory, *,
                       frame, compiler="gcc"):
    output = _roots((source, native, scoped, handoff, cycle, preview, rgb),
                    seal_directory)
    if tuple(output.iterdir()):
        raise ValueError("private MAP02 seal output already exists")
    directory, first = _check(
        source, native, scoped, handoff, cycle, preview, rgb,
        owned_game, upstream, binary, seal_directory, frame, compiler)
    _, second = _check(
        source, native, scoped, handoff, cycle, preview, rgb,
        owned_game, upstream, binary, seal_directory, frame, compiler)
    if first != second:
        raise ValueError("MAP02 final evidence changed between audits")
    raw = (json.dumps(first, sort_keys=True, separators=(",", ":")) +
           "\n").encode("utf-8")
    _canonical(raw)
    file_identity, directory_identity = _publish(directory, raw)
    try:
        # Close the verification gap between the second pre-write audit
        # and exclusive publication. This reopens the seal by inode and
        # independently revalidates ALL source/CD/GPU/process/RGB/PNG files.
        observed = verify_final_seal(
            source, native, scoped, handoff, cycle, preview, rgb,
            owned_game, upstream, binary, seal_directory,
            frame=frame, compiler=compiler)
        if (observed["private_final_seal_sha256"] !=
                hashlib.sha256(raw).hexdigest() or
                observed["gpu_draw_frame"] != first["gpu_draw_frame"] or
                observed["sealed_evidence_independently_reverified"]
                is not True):
            raise ValueError("published MAP02 seal differs after verification")
        # Matching bytes are insufficient: the path must still refer to
        # the exact receipt inode published by this invocation.
        _require_published_identity(directory, file_identity,
                                    directory_identity)
    except BaseException:
        _discard_own_published_seal(directory, file_identity,
                                    directory_identity)
        raise
    return {
        "schema": SCHEMA,
        "gpu_draw_frame": first["gpu_draw_frame"],
        "private_final_seal_sha256": hashlib.sha256(raw).hexdigest(),
        "two_independent_readonly_final_audits": True,
        "postpublication_independent_verification_completed": True,
        "game_bytes_uploaded": False,
        "original_map02_rendering_proven": False,
    }


def verify_final_seal(source, native, scoped, handoff, cycle, preview, rgb,
                      owned_game, upstream, binary, seal_directory, *,
                      frame, compiler="gcc"):
    directory = _roots(
        (source, native, scoped, handoff, cycle, preview, rgb),
        seal_directory)
    if {p.name for p in directory.iterdir()} != {NAME}:
        raise ValueError("missing or unexpected MAP02 final seal files")
    before = _private_evidence_snapshot(directory, NAME, max_bytes=4096)
    recorded = _canonical(before[0])
    _, independently_verified = _check(
        source, native, scoped, handoff, cycle, preview, rgb,
        owned_game, upstream, binary, directory, frame, compiler)
    if (recorded != independently_verified or
            _private_evidence_snapshot(directory, NAME,
                                       max_bytes=4096) != before):
        raise ValueError("MAP02 final seal differs from independently verified evidence")
    return {
        "schema": SCHEMA,
        "gpu_draw_frame": recorded["gpu_draw_frame"],
        "private_final_seal_sha256": hashlib.sha256(before[0]).hexdigest(),
        "sealed_evidence_independently_reverified": True,
        "game_bytes_uploaded": False,
        "original_map02_rendering_proven": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "verify"))
    p.add_argument("private_source_bundle", type=Path)
    p.add_argument("private_native_gpu", type=Path)
    p.add_argument("private_scoped", type=Path)
    p.add_argument("private_process_handoff", type=Path)
    p.add_argument("private_cycle", type=Path)
    p.add_argument("private_png", type=Path)
    p.add_argument("private_pc_rgb24", type=Path)
    p.add_argument("private_owned_game_image", type=Path)
    p.add_argument("private_seal_directory", type=Path)
    p.add_argument("--upstream-checkout", type=Path, required=True)
    p.add_argument("--pc-binary", type=Path, required=True)
    p.add_argument("--frame", type=int, required=True)
    p.add_argument("--compiler", choices=("gcc", "clang"), default="gcc")
    args = p.parse_args()
    fn = seal_final_capture if args.action == "seal" else verify_final_seal
    try:
        result = fn(
            args.private_source_bundle, args.private_native_gpu,
            args.private_scoped, args.private_process_handoff,
            args.private_cycle, args.private_png, args.private_pc_rgb24,
            args.private_owned_game_image, args.upstream_checkout,
            args.pc_binary, args.private_seal_directory,
            frame=args.frame, compiler=args.compiler)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        p.error("private MAP02 final seal unavailable")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
