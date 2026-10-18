#!/usr/bin/env python3
"""Exclusively seal a REAL observed original MAP02 CdRead into GPU/GTE evidence.

The existing GPU-only witness retains its original meaning and schema. This
extra *stronger* final witness requires ALL independent checks at publication
and reopening: pinned GTE/FT4 source -> original GPU windows/PutPixel/
BlendG1/VRAM -> original CdRead + loader-complete -> privately owned raw US
disc bytes -> OS-observed child ELF / opened disc fd, with ONE session nonce.

It is still only a software provenance/integrity chain, NOT proof of original
retail gameplay, full MAP02 map rendering, or hardware PlayStation accuracy.
No original game bytes or full VRAM are emitted.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from tools.publish_map02_blendg1_witness import (
    _private_directory, _prepare_private_file,
)
from tools.publish_map02_window_scoped_witness import (
    MANIFEST as GPU_GTE_MANIFEST,
    verify_published_window_scoped_witness,
)
from tools.map02_verified_process_launch import (
    RECEIPT as PROCESS_MANIFEST, verify_observed_process,
)
from tools.verify_map02_original_cd_read import verify_map02_original_cd_read
from tools.verify_map02_frame_bundle import fields, number, parse_json
from tools.verify_map02_native_gpu_capture import private_file

SCHEMA = "vh.map02.native-gte-gpu-cd-process-witness.v1"
MANIFEST = "gpu-native-map02-cd-process-source-witness.json"
DIGESTS = (
    "verified_gpu_gte_witness_sha256",
    "observed_process_receipt_sha256",
    "original_cd_read_receipt_sha256",
    "owned_disc_image_sha256",
    "original_map02_user_data_sha256",
    "capture_session_sha256",
)
REQUIRED = (
    "schema", "gpu_draw_frame", "original_map02_lba",
    "original_map02_sectors", *DIGESTS,
    "source_gte_gpu_verified", "kernel_pc_executable_observed",
    "original_cd_loader_completion_observed",
    "original_cd_payload_matches_owned_image",
    "same_process_all_streams",
    "full_original_gameplay_authenticated",
    "original_map02_rendering_proven",
    "physical_ps1_equivalence_proven",
)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _validate(payload):
    if type(payload) is not dict:
        raise ValueError("MAP02 CD/GPU final witness must be a JSON object")
    fields(payload, REQUIRED, MANIFEST)
    if (payload["schema"] != SCHEMA or
            any(payload[key] is not True for key in (
                "source_gte_gpu_verified",
                "kernel_pc_executable_observed",
                "original_cd_loader_completion_observed",
                "original_cd_payload_matches_owned_image",
                "same_process_all_streams",
            )) or any(payload[key] is not False for key in (
                "full_original_gameplay_authenticated",
                "original_map02_rendering_proven",
                "physical_ps1_equivalence_proven",
            ))):
        raise ValueError("unverified or overstated MAP02 CD/GPU final witness")
    number(payload["gpu_draw_frame"], "CD/GPU frame", 1, 2**32-1)
    if (number(payload["original_map02_lba"], "MAP02 resource LBA",
               0, 0x1bcc) != 0x1bcc or
            number(payload["original_map02_sectors"], "MAP02 sector count",
                   1, 12) != 12):
        raise ValueError("MAP02 original CD resource boundaries changed")
    for key in DIGESTS:
        word = payload[key]
        if (type(word) is not str or len(word) != 64 or
                any(c not in "0123456789abcdef" for c in word)):
            raise ValueError("malformed final MAP02 CD/GPU SHA-256: " + key)
    return payload


def _verified(source, native, scoped, handoff, image, upstream, pc_binary, *,
              frame, compiler):
    folders = [(_private_directory(p)) for p in (
        source, native, scoped, handoff)]
    if len({p.resolve() for p in folders}) != len(folders):
        raise ValueError("CD source, GPU, scoped and process witness directories must differ")
    source, native, scoped, handoff = folders
    frame = number(frame, "target GPU frame", 1, 2**32-1)

    # Capture BOTH identities before expensive independent re-verification.
    # A byte-identical same-UID replacement inode must not be accepted as
    # unchanged merely because the final SHA-256 still matches.
    # Lazy import avoids the cycle join -> final witness import at module load.
    from tools.verify_map02_cycle_cd_gpu_join import _private_evidence_snapshot
    source_raw, source_identity = _private_evidence_snapshot(
        source, GPU_GTE_MANIFEST, max_bytes=4096)
    process_raw, process_identity = _private_evidence_snapshot(
        handoff, PROCESS_MANIFEST, max_bytes=4096)
    gpu = verify_published_window_scoped_witness(
        source, native, scoped, frame=frame, compiler=compiler)
    cd = verify_map02_original_cd_read(
        scoped, native, image, upstream, frame=frame)
    process = verify_observed_process(
        handoff, native, scoped, pc_binary, image, upstream=upstream)
    process_info = parse_json(process_raw, PROCESS_MANIFEST)

    if (_sha(source_raw) != gpu["private_witness_sha256"] or
            _sha(process_raw) != process["private_process_receipt_sha256"] or
            process_info.get("gpu_draw_frame") != frame or
            process_info.get("game_image_fd_observed") is not True or
            process_info.get("capture_session_sha256") !=
            cd["native_gpu_process_session_sha256"] or
            process_info.get("native_window_all_files_sha256") is None):
        raise ValueError("observed CD/GPU source and process receipts are not same-run")

    record = _validate({
        "schema": SCHEMA,
        "gpu_draw_frame": frame,
        "original_map02_lba": cd["original_map02_resource_lba"],
        "original_map02_sectors": cd["original_map02_resource_sector_count"],
        "verified_gpu_gte_witness_sha256": _sha(source_raw),
        "observed_process_receipt_sha256": _sha(process_raw),
        "original_cd_read_receipt_sha256": cd["original_cd_receipt_sha256"],
        "owned_disc_image_sha256": cd["owned_disc_image_sha256"],
        "original_map02_user_data_sha256":
            cd["original_map02_user_data_sha256"],
        "capture_session_sha256": cd["native_gpu_process_session_sha256"],
        "source_gte_gpu_verified": True,
        "kernel_pc_executable_observed": True,
        "original_cd_loader_completion_observed": True,
        "original_cd_payload_matches_owned_image": True,
        "same_process_all_streams": True,
        "full_original_gameplay_authenticated": False,
        "original_map02_rendering_proven": False,
        "physical_ps1_equivalence_proven": False,
    })
    if (_private_evidence_snapshot(source, GPU_GTE_MANIFEST, max_bytes=4096)
            != (source_raw, source_identity) or
            _private_evidence_snapshot(handoff, PROCESS_MANIFEST, max_bytes=4096)
            != (process_raw, process_identity)):
        raise ValueError("GTE/GPU or observed-process evidence identity changed during final CD audit")
    return record


def publish_original_cd_witness(source, native, scoped, handoff, image,
                                upstream, pc_binary, *, frame, compiler="gcc"):
    source = _private_directory(source)
    target = source / MANIFEST
    if target.exists() or target.is_symlink():
        raise ValueError("final source/GPU/CD process MAP02 witness already exists")
    record = _verified(source, native, scoped, handoff, image, upstream,
                       pc_binary, frame=frame, compiler=compiler)
    raw = (json.dumps(record, sort_keys=True, separators=(",", ":"))
           + "\n").encode("utf-8")
    temporary = None
    linked = False
    try:
        temporary = _prepare_private_file(target, raw)
        if _verified(source, native, scoped, handoff, image, upstream,
                     pc_binary, frame=frame, compiler=compiler) != record:
            raise ValueError("source/GPU/CD process evidence changed before publication")
        os.link(temporary, target)
        linked = True
        # Strict source-bound file readback rejects temporary hardlinks.
        temporary.unlink()
        if private_file(source, MANIFEST, max_bytes=4096) != raw:
            raise ValueError("published MAP02 CD/GPU final witness readback differs")
    except BaseException:
        if linked:
            target.unlink(missing_ok=True)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"private_map02_cd_final_sha256": _sha(raw),
            "same_process_original_cd_and_gpu_source_bound": True,
            "original_map02_rendering_proven": False,
            "physical_ps1_equivalence_proven": False}


def verify_published_original_cd_witness(
        source, native, scoped, handoff, image, upstream, pc_binary, *,
        frame, compiler="gcc"):
    source = _private_directory(source)
    from tools.verify_map02_cycle_cd_gpu_join import _private_evidence_snapshot
    raw, manifest_identity = _private_evidence_snapshot(
        source, MANIFEST, max_bytes=4096)
    recorded = _validate(parse_json(raw, MANIFEST))
    if recorded["gpu_draw_frame"] != number(
            frame, "selected GPU frame", 1, 2**32-1):
        raise ValueError("selected frame differs from original MAP02 CD/GPU witness")
    verified = _verified(source, native, scoped, handoff, image, upstream,
                         pc_binary, frame=frame, compiler=compiler)
    if (verified != recorded or
            _private_evidence_snapshot(source, MANIFEST, max_bytes=4096)
            != (raw, manifest_identity)):
        raise ValueError("final original MAP02 CD/GPU process witness identity changed")
    return {"private_map02_cd_final_sha256": _sha(raw),
            "same_process_original_cd_and_gpu_source_bound": True,
            "original_map02_rendering_proven": False,
            "physical_ps1_equivalence_proven": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_source_bundle", type=Path)
    p.add_argument("private_gpu_windows", type=Path)
    p.add_argument("private_scoped_capture", type=Path)
    p.add_argument("private_local_handoff", type=Path)
    p.add_argument("private_owned_us_disc", type=Path)
    p.add_argument("--upstream-checkout", type=Path, required=True)
    p.add_argument("--pc-binary", type=Path, required=True)
    p.add_argument("--frame", type=int, required=True)
    p.add_argument("--compiler", default="gcc")
    p.add_argument("--publish", action="store_true")
    args = p.parse_args()
    fn = (publish_original_cd_witness if args.publish else
          verify_published_original_cd_witness)
    try:
        print(json.dumps(fn(
            args.private_source_bundle, args.private_gpu_windows,
            args.private_scoped_capture, args.private_local_handoff,
            args.private_owned_us_disc, args.upstream_checkout,
            args.pc_binary, frame=args.frame, compiler=args.compiler),
            sort_keys=True, indent=2))
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
