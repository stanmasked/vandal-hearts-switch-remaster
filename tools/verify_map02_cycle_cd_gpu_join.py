#!/usr/bin/env python3
"""Independently join a real in-process CD->DrawOTag ordering receipt to the
already published MAP02 CD/GPU/GTE/kernel-process SHA witness.

This is a local *verification*, not a publisher and not proof of a rendered
original MAP02 scene. The full original witness is reverified on every run;
no shortcut via matching JSON identifiers is accepted. No original disc,
executable, texture or VRAM bytes are printed, copied or uploaded.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.publish_map02_blendg1_witness import _private_directory
from tools.publish_map02_cd_bound_witness import (
    MANIFEST as CD_GPU_MANIFEST,
    verify_published_original_cd_witness,
)
from tools.verify_map02_frame_bundle import fields, number, parse_json
from tools.verify_map02_native_gpu_capture import private_file
from tools.verify_map02_window_scoped_join import CD_READ

CYCLE_RECEIPT = "map02-single-process-cycle.jsonl"
CYCLE_CLEAN_EXIT = "map02-cycle-clean-exit.jsonl"
CYCLE_SCHEMA = "vh.map02.cycle-order.v2"
SCHEMA = "vh.map02.same-process-cycle-cd-gpu-join.v1"
CD_READ_KEYS = (
    "schema", "capture_session", "source", "cdf", "lba",
    "sectors", "bytes", "raw_user_crc32", "returned_user_crc32",
    "raw_user_sha256", "returned_user_sha256", "loader_completed",
)

CYCLE_KEYS = (
    "schema", "capture_session", "gpu_draw_frame",
    "original_cd_raw_user_crc32",
    "ordered_source_hooks_observed", "cd_payload_verified_by_this_receipt",
    "original_map02_rendering_proven", "physical_ps1_equivalence_proven",
)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _private_evidence_snapshot(root, filename, *, max_bytes):
    """Double-read a single verified private inode; retain its identity.

    Bytes alone cannot detect replacement by a byte-identical foreign inode.
    Keep both the exact bytes and inode/metadata snapshot until completion of
    the expensive independent retail-source and process witness validation.
    """
    path = root / filename
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise ValueError("private MAP02 evidence input unavailable") from None
    try:
        def identity(st):
            return (st.st_dev, st.st_ino, st.st_uid, st.st_mode,
                    st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns)

        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or
                before.st_uid != os.geteuid() or before.st_nlink != 1 or
                stat.S_IMODE(before.st_mode) != 0o600 or
                not 0 < before.st_size <= max_bytes):
            raise ValueError("private MAP02 evidence must be owner-only 0600 regular file")

        def read_pass():
            raw = os.pread(fd, before.st_size, 0)
            if len(raw) != before.st_size:
                raise ValueError("private MAP02 evidence incomplete read")
            return raw

        first = read_pass()
        if identity(os.fstat(fd)) != identity(before):
            raise ValueError("private MAP02 evidence changed during read")
        second = read_pass()
        if first != second:
            raise ValueError("private MAP02 evidence bytes changed between reads")
        if (identity(os.fstat(fd)) != identity(before) or
                identity(os.stat(path, follow_symlinks=False)) != identity(before)):
            raise ValueError("private MAP02 evidence inode changed during read")
        return first, identity(before)
    except OSError:
        raise ValueError("private MAP02 evidence verification unavailable") from None
    finally:
        os.close(fd)


def _cycle_receipt(directory, frame):
    root = _private_directory(directory)
    if {entry.name for entry in root.iterdir()} != {CYCLE_RECEIPT, CYCLE_CLEAN_EXIT}:
        raise ValueError("cycle directory must contain receipt and normal-exit seal")
    raw, inode_identity = _private_evidence_snapshot(
        root, CYCLE_RECEIPT, max_bytes=2048)
    seal, seal_identity = _private_evidence_snapshot(
        root, CYCLE_CLEAN_EXIT, max_bytes=2048)
    if (raw != seal or
            (inode_identity[0], inode_identity[1]) ==
            (seal_identity[0], seal_identity[1])):
        raise ValueError("MAP02 cycle normal-exit seal and receipt differ")
    if raw.count(b"\n") != 1 or not raw.endswith(b"\n") or b"\r" in raw:
        raise ValueError("noncanonical cycle receipt JSONL")
    event = parse_json(raw[:-1], CYCLE_RECEIPT)
    fields(event, CYCLE_KEYS, CYCLE_RECEIPT)
    if (event["schema"] != CYCLE_SCHEMA or
            event["ordered_source_hooks_observed"] is not True or
            event["cd_payload_verified_by_this_receipt"] is not False or
            event["original_map02_rendering_proven"] is not False or
            event["physical_ps1_equivalence_proven"] is not False):
        raise ValueError("unsupported or overstated single-process cycle receipt")
    if number(event["gpu_draw_frame"], "cycle DrawOTag frame",
              1, 2**32-1) != frame:
        raise ValueError("single-process cycle and GPU frame mismatch")
    checksum = event["original_cd_raw_user_crc32"]
    if (type(checksum) is not str or len(checksum) != 8 or
            any(ch not in "0123456789abcdef" for ch in checksum)):
        raise ValueError("invalid same-process original CdRead CRC32")
    token = event["capture_session"]
    if (type(token) is not str or len(token) != 32 or
            any(c not in "0123456789abcdef" for c in token)):
        raise ValueError("invalid single-process cycle nonce")
    # Retain identities of BOTH independent files across the full later
    # CD/GPU/process audit; neither file may be replaced during it.
    return raw, _sha(token.encode("ascii")), (inode_identity, seal_identity)


def _cycle_cd_pair(scoped, cycle, frame, expected_session_sha256):
    """Match private in-process order and original CdRead before process seal.

    Do not conflate an ordered hook event with authenticated disc contents.
    The full source/image/GPU recheck is performed by the final verifier.
    Return the original bytes AND inode metadata for an after-audit recheck.
    """
    cycle_raw, session_digest, cycle_inode = _cycle_receipt(cycle, frame)
    if session_digest != expected_session_sha256:
        raise ValueError("single-process cycle nonce differs from GPU/scoped witness")
    event = parse_json(cycle_raw[:-1], CYCLE_RECEIPT)
    scoped = _private_directory(scoped)
    cd_raw, cd_inode = _private_evidence_snapshot(scoped, CD_READ, max_bytes=2048)
    if cd_raw.count(b"\n") != 1 or not cd_raw.endswith(b"\n") or b"\r" in cd_raw:
        raise ValueError("noncanonical original MAP02 CdRead JSONL")
    cd_event = parse_json(cd_raw[:-1], CD_READ)
    fields(cd_event, CD_READ_KEYS, CD_READ)
    # Only the original pinned MAP02 resource is acceptable. Matching CRC
    # bytes alone does not identify an extent, source hook, or completed load.
    if (cd_event["schema"] != "vh.map02.original-cd-read.v2" or
            cd_event["source"] != "original-CdRead-and-ContinueLoadingCdFile" or
            cd_event["cdf"] != "CDF_M_MAP02_PRS" or
            number(cd_event["lba"], "MAP02 original LBA", 0, 0x1bcc) != 0x1bcc or
            number(cd_event["sectors"], "MAP02 original sector count", 1, 12) != 12 or
            number(cd_event["bytes"], "MAP02 original transfer bytes", 1, 24576) != 24576 or
            cd_event["loader_completed"] is not True):
        raise ValueError("original MAP02 CdRead extent or loader state differs")
    token = cd_event["capture_session"]
    if (type(token) is not str or len(token) != 32 or
            any(ch not in "0123456789abcdef" for ch in token) or
            _sha(token.encode("ascii")) != session_digest or
            cd_event["raw_user_crc32"] != event["original_cd_raw_user_crc32"] or
            cd_event["returned_user_crc32"] != event["original_cd_raw_user_crc32"] or
            cd_event["raw_user_sha256"] != cd_event["returned_user_sha256"] or
            any(type(cd_event[k]) is not str or len(cd_event[k]) != 64 or
                any(ch not in "0123456789abcdef" for ch in cd_event[k])
                for k in ("raw_user_sha256", "returned_user_sha256"))):
        raise ValueError("ordered cycle checksum and original CdRead receipt differ")
    return cycle_raw, cycle_inode, cd_raw, cd_inode


def verify_cycle_cd_gpu_join(source, native, scoped, handoff, cycle, image,
                             upstream, pc_binary, *, frame, compiler="gcc"):
    frame = number(frame, "selected DrawOTag frame", 1, 2**32-1)
    roots = [_private_directory(p) for p in
             (source, native, scoped, handoff, cycle)]
    if len({p.resolve() for p in roots}) != 5:
        raise ValueError("source, GPU, scoped, process and cycle directories must differ")
    source, native, scoped, handoff, cycle = roots
    cycle_raw, cycle_session_sha256, cycle_inode = _cycle_receipt(cycle, frame)
    cycle_event = parse_json(cycle_raw[:-1], CYCLE_RECEIPT)
    before, manifest_inode = _private_evidence_snapshot(
        source, CD_GPU_MANIFEST, max_bytes=4096)
    original = parse_json(before, CD_GPU_MANIFEST)
    if (type(original) is not dict or
            original.get("gpu_draw_frame") != frame or
            original.get("capture_session_sha256") != cycle_session_sha256):
        raise ValueError("original CD/GPU manifest and ordered cycle are not one session")

    # Match both native CdRead and cycle-order evidence before the costly
    # original-disc/GPU/process audit; retain their inode identities too.
    pair = _cycle_cd_pair(scoped, cycle, frame, cycle_session_sha256)
    if pair[:2] != (cycle_raw, cycle_inode):
        raise ValueError("cycle evidence changed during verification")

    # This is intentionally the expensive FULL original source/CD/GPU/process
    # audit, not a mocked assertion or a trust-only schema comparison.
    verified = verify_published_original_cd_witness(
        source, native, scoped, handoff, image, upstream, pc_binary,
        frame=frame, compiler=compiler)
    if verified["private_map02_cd_final_sha256"] != _sha(before):
        raise ValueError("original CD/GPU manifest SHA differs after re-verification")
    if (_private_evidence_snapshot(source, CD_GPU_MANIFEST, max_bytes=4096)
            != (before, manifest_inode) or
            _cycle_cd_pair(scoped, cycle, frame, cycle_session_sha256) != pair):
        raise ValueError("cycle or original CD/GPU evidence changed during verification")

    # Return hashes only; the nonce and all original game material remain private.
    return {
        "schema": SCHEMA,
        "gpu_draw_frame": frame,
        "source_cd_gpu_process_witness_sha256": _sha(before),
        "single_process_cycle_receipt_sha256": _sha(cycle_raw),
        "capture_session_sha256": cycle_session_sha256,
        "same_process_event_order_and_prior_cd_gpu_witness_join_verified": True,
        "full_original_gameplay_authenticated": False,
        "original_map02_rendering_proven": False,
        "physical_ps1_equivalence_proven": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_source_bundle", type=Path)
    parser.add_argument("private_gpu_windows", type=Path)
    parser.add_argument("private_scoped_capture", type=Path)
    parser.add_argument("private_local_handoff", type=Path)
    parser.add_argument("private_cycle_order", type=Path)
    parser.add_argument("private_owned_us_disc", type=Path)
    parser.add_argument("--upstream-checkout", type=Path, required=True)
    parser.add_argument("--pc-binary", type=Path, required=True)
    parser.add_argument("--frame", type=int, required=True)
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    try:
        result = verify_cycle_cd_gpu_join(
            args.private_source_bundle, args.private_gpu_windows,
            args.private_scoped_capture, args.private_local_handoff,
            args.private_cycle_order, args.private_owned_us_disc,
            args.upstream_checkout, args.pc_binary,
            frame=args.frame, compiler=args.compiler)
    except ValueError as exc:
        parser.error(str(exc))
    except (OSError, subprocess.TimeoutExpired):
        # Filesystem errors / timed-out external audits may include absolute
        # private image, source or witness paths and captured process output.
        parser.error("private MAP02 cycle verification unavailable")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
