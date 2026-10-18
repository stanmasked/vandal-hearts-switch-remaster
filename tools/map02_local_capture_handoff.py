#!/usr/bin/env python3
"""Private, read-only-byte provenance handoff for a local MAP02 capture.

PREPARE before launching a locally owned, instrumented original-PC binary:
bind its file hash, user's owned game-image hash, target DrawOTag frame and
pinned original PC source revision in a private exclusive 0600 plan.

SEAL after a real, previously published and VERIFIED MAP02 source/GTE/OT
+ GPU-window/PutPixel/BlendG1/VRAM witness has been produced. Recompute both
external-file hashes and bind the verified final witness + process session.
VERIFY reruns checks on the same original inputs. Never reads/runs/uploads
the game content except hashing local bytes; output contains aggregates only.

Important limitation: this is a user-supplied file-identity declaration, NOT
hardware attestation, a proof that the binary executed, or retail PS1 parity.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.prepare_map02_pcport import (
    PINNED_UPSTREAM_REF, PINNED_BLOB_SHA1, git_blob_sha1,
)
from tools.instrument_map02_gpu_native_events import PINNED_SOURCE
from tools.publish_map02_blendg1_witness import (
    _private_directory, _prepare_private_file,
)
from tools.publish_map02_window_scoped_witness import (
    MANIFEST as FOUR_STREAM, verify_published_window_scoped_witness,
)
from tools.verify_map02_frame_bundle import fields, number, parse_json
from tools.verify_map02_native_gpu_capture import private_file

PLAN = "gpu-local-capture-plan.json"
HANDOFF = "gpu-local-capture-handoff.json"
PLAN_SCHEMA = "vh.map02.local-capture-plan.v1"
HANDOFF_SCHEMA = "vh.map02.local-capture-handoff.v2"
# The user must have enabled these for the final source-bound observer.
REQUIRED_DIAGNOSTIC_MACROS = (
    "VH_MAP02_GPU_CAPTURE",
    "VH_MAP02_POSIX_CAPTURE_WINDOWS",
    "VH_MAP02_SCOPED_BLEND_PROBE",
    "VH_MAP02_VRAM_EDGE_PROBE",
    "VH_MAP02_POSIX_STAGE",
    "VH_MAP02_CAPTURE_SESSION",
)
SOURCE_BLOBS = {
    **PINNED_BLOB_SHA1,
    "platform/pc/src/libgpu.c": PINNED_SOURCE,
    "platform/pc/src/pc_raster.c": "ba8a05d161ad778c0b75e452ff0a11ed163c65cd",
    "platform/pc/src/libcd.c": "1300664537c49f33bbbace1fe0fb58d2463bd627",
    "platform/pc/src/pc_bootstrap.c": "1020af186761cd323e88d94da21c8755a093cdd9",
    "src/core/cd.c": "30d43504c8becadaca4c475abce9d40b0bc9dc2b",
}
DIGESTS = (
    "pinned_upstream_source_identity_sha256",
    "pc_executable_sha256", "owned_game_image_sha256",
    "plan_sha256", "source_gte_gpu_witness_sha256",
    "capture_session_sha256",
)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_pinned_upstream(checkout):
    """Match actual original native/GTE Git blob bytes to pinned source."""
    checkout = Path(checkout).absolute()
    if checkout.is_symlink() or not checkout.is_dir():
        raise ValueError("pinned original PC-port checkout missing or linked")
    digest = hashlib.sha256()
    for relative, expected in sorted(SOURCE_BLOBS.items()):
        candidate = checkout / relative
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError("original PC-port source missing or linked: " + relative)
        raw = candidate.read_bytes()
        if git_blob_sha1(raw) != expected:
            raise ValueError("original PC-port source differs from pinned: " + relative)
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(raw).digest())
    return digest.hexdigest()


def _sha_file(path, *, private=False):
    path = Path(path).absolute()
    if path.is_symlink() or not path.is_file():
        raise ValueError("local capture input is missing, linked, or nonregular")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
            raise ValueError("capture input is not a nonempty regular file")
        if private and (info.st_mode & 0o077):
            raise ValueError("owned game-image input must be owner-private")
        if info.st_uid != os.geteuid():
            raise ValueError("capture input must be owned by current user")
        hasher = hashlib.sha256()
        with os.fdopen(os.dup(descriptor), "rb", closefd=True) as stream:
            while True:
                chunk = stream.read(1 << 20)
                if not chunk:
                    break
                hasher.update(chunk)
        current = os.fstat(descriptor)
        if (current.st_size != info.st_size or
                current.st_mtime_ns != info.st_mtime_ns or
                current.st_ctime_ns != info.st_ctime_ns):
            raise ValueError("capture input changed during hashing")
        return hasher.hexdigest()
    finally:
        os.close(descriptor)


def _validate_plan(raw):
    plan = parse_json(raw, PLAN)
    fields(plan, (
        "schema", "pinned_original_pc_source_commit",
        "target_gpu_draw_frame", "pinned_upstream_source_identity_sha256",
        "pc_executable_sha256",
        "owned_game_image_sha256", "diagnostic_compile_macros",
        "gameplay_origin_authenticated", "physical_ps1_equivalence_proven",
    ), PLAN)
    if (plan["schema"] != PLAN_SCHEMA or
            plan["pinned_original_pc_source_commit"] != PINNED_UPSTREAM_REF or
            plan["diagnostic_compile_macros"] !=
            list(REQUIRED_DIAGNOSTIC_MACROS) or
            plan["gameplay_origin_authenticated"] is not False or
            plan["physical_ps1_equivalence_proven"] is not False):
        raise ValueError("unsupported/overstated local MAP02 capture plan")
    number(plan["target_gpu_draw_frame"], "target GPU frame", 1, 2**32 - 1)
    for key in ("pinned_upstream_source_identity_sha256",
                "pc_executable_sha256", "owned_game_image_sha256"):
        value = plan[key]
        if (type(value) is not str or len(value) != 64 or
                any(c not in "0123456789abcdef" for c in value)):
            raise ValueError("invalid plan SHA-256: " + key)
    return plan


def _plan_bytes(pc_binary, owned_game, frame, upstream):
    plan = {
        "schema": PLAN_SCHEMA,
        "pinned_original_pc_source_commit": PINNED_UPSTREAM_REF,
        "pinned_upstream_source_identity_sha256": verify_pinned_upstream(upstream),
        "target_gpu_draw_frame": number(frame, "GPU frame", 1, 2**32 - 1),
        "pc_executable_sha256": _sha_file(pc_binary),
        "owned_game_image_sha256": _sha_file(owned_game, private=True),
        "diagnostic_compile_macros": list(REQUIRED_DIAGNOSTIC_MACROS),
        "gameplay_origin_authenticated": False,
        "physical_ps1_equivalence_proven": False,
    }
    return (json.dumps(plan, sort_keys=True, separators=(",", ":"))
            + "\n").encode("utf-8")


def _publish(root, name, raw):
    target = root / name
    if target.exists() or target.is_symlink():
        raise ValueError("MAP02 local capture file already exists; no overwrite")
    temporary = None
    linked = False
    try:
        temporary = _prepare_private_file(target, raw)
        os.link(temporary, target)
        linked = True
        # End the temporary hardlink lifetime before strict readback:
        # the published proof must have exactly one directory entry.
        temporary.unlink()
        if private_file(root, name, max_bytes=4096) != raw:
            raise ValueError("private MAP02 local capture readback changed")
    except BaseException:
        if linked:
            target.unlink(missing_ok=True)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare_local_capture(handoff_dir, pc_binary, owned_game, *, frame, upstream):
    directory = _private_directory(handoff_dir)
    raw = _plan_bytes(pc_binary, owned_game, frame, upstream)
    _validate_plan(raw)
    _publish(directory, PLAN, raw)
    return {"local_plan_sha256": _sha(raw), "capture_executed": False,
            "owned_game_data_emitted": False,
            "original_gameplay_authenticated": False}


def _validated_handoff(raw):
    record = raw if type(raw) is dict else parse_json(raw, HANDOFF)
    fields(record, (
        "schema", "gpu_draw_frame", *DIGESTS,
        "source_gte_gpu_witness_verified",
        "same_process_session_linked",
        "live_kernel_executable_observed",
        "observed_execution_receipt_sha256",
        "owned_game_binary_executed_proven",
        "original_gameplay_authenticated",
        "physical_ps1_equivalence_proven",
    ), HANDOFF)
    if (record["schema"] != HANDOFF_SCHEMA or
            record["source_gte_gpu_witness_verified"] is not True or
            record["same_process_session_linked"] is not True or
            type(record["live_kernel_executable_observed"]) is not bool or
            record["owned_game_binary_executed_proven"] is not False or
            record["original_gameplay_authenticated"] is not False or
            record["physical_ps1_equivalence_proven"] is not False):
        raise ValueError("unsupported or overstated local capture handoff")
    number(record["gpu_draw_frame"], "handoff GPU frame", 1, 2**32 - 1)
    observed_digest = record["observed_execution_receipt_sha256"]
    if record["live_kernel_executable_observed"]:
        if (type(observed_digest) is not str or len(observed_digest) != 64 or
                any(c not in "0123456789abcdef" for c in observed_digest)):
            raise ValueError("invalid live process witness SHA-256")
    elif observed_digest is not None:
        raise ValueError("unobserved local process cannot carry execution receipt")
    for name in DIGESTS:
        value = record[name]
        if (type(value) is not str or len(value) != 64 or
                any(x not in "0123456789abcdef" for x in value)):
            raise ValueError("malformed local capture handoff SHA: " + name)
    return record


def _verified_handoff(handoff_dir, source_dir, native_dir, scoped_dir,
                      pc_binary, owned_game, *, upstream, compiler):
    directory = _private_directory(handoff_dir)
    source, native, scoped = (_private_directory(p)
                              for p in (source_dir, native_dir, scoped_dir))
    if len({p.resolve() for p in (directory, source, native, scoped)}) != 4:
        raise ValueError("local capture folders must be four separate private directories")
    plan_raw = private_file(directory, PLAN, max_bytes=4096)
    plan = _validate_plan(plan_raw)
    if (verify_pinned_upstream(upstream) !=
            plan["pinned_upstream_source_identity_sha256"] or
            _sha_file(pc_binary) != plan["pc_executable_sha256"] or
            _sha_file(owned_game, private=True) != plan["owned_game_image_sha256"]):
        raise ValueError("local PC executable or owned game input differs from pre-run plan")
    frame = plan["target_gpu_draw_frame"]
    final = verify_published_window_scoped_witness(
        source, native, scoped, frame=frame, compiler=compiler)
    raw_final = private_file(source, FOUR_STREAM, max_bytes=4096)
    if _sha(raw_final) != final["private_witness_sha256"]:
        raise ValueError("verified GTE/GPU four-stream witness digest changed")
    final_record = parse_json(raw_final, FOUR_STREAM)
    if (final_record["gpu_frame"] != frame or
            final_record.get("capture_session_linked") is not True):
        raise ValueError("GPU frame or process session not bound in completed witness")
    session = final_record["capture_session_sha256"]
    # Optional opt-in stronger path: the Linux launcher has already
    # observed the live kernel executable and cross-verified native GPU
    # windows/scoped nonce. A missing record remains an explicitly
    # *unobserved*, hash-only legacy/manual handoff.
    from tools.map02_verified_process_launch import (
        RECEIPT as EXECUTION, verify_observed_process,
    )
    execution = directory / EXECUTION
    execution_digest = None
    if execution.is_symlink() or execution.exists():
        process_report = verify_observed_process(
            directory, native, scoped, pc_binary, owned_game, upstream=upstream)
        execution_digest = process_report["private_process_receipt_sha256"]
        receipt = parse_json(private_file(directory, EXECUTION, max_bytes=4096),
                             EXECUTION)
        if receipt["gpu_draw_frame"] != frame or (
                receipt["capture_session_sha256"] != session):
            raise ValueError("live process receipt and GTE-verified GPU session differ")
    record = _validated_handoff({
        "schema": HANDOFF_SCHEMA,
        "gpu_draw_frame": frame,
        "pinned_upstream_source_identity_sha256":
            plan["pinned_upstream_source_identity_sha256"],
        "pc_executable_sha256": plan["pc_executable_sha256"],
        "owned_game_image_sha256": plan["owned_game_image_sha256"],
        "plan_sha256": _sha(plan_raw),
        "source_gte_gpu_witness_sha256": _sha(raw_final),
        "capture_session_sha256": session,
        "source_gte_gpu_witness_verified": True,
        "same_process_session_linked": True,
        "live_kernel_executable_observed": execution_digest is not None,
        "observed_execution_receipt_sha256": execution_digest,
        "owned_game_binary_executed_proven": False,
        "original_gameplay_authenticated": False,
        "physical_ps1_equivalence_proven": False,
    })
    if (execution_digest is not None and
            _sha(private_file(directory, EXECUTION, max_bytes=4096)) !=
            execution_digest):
        raise ValueError("observed process receipt changed during source handoff")
    if (private_file(directory, PLAN, max_bytes=4096) != plan_raw or
            private_file(source, FOUR_STREAM, max_bytes=4096) != raw_final or
            verify_pinned_upstream(upstream) !=
            plan["pinned_upstream_source_identity_sha256"] or
            _sha_file(pc_binary) != plan["pc_executable_sha256"] or
            _sha_file(owned_game, private=True) != plan["owned_game_image_sha256"]):
        raise ValueError("local capture evidence changed during handoff verification")
    return record


def seal_local_capture(handoff_dir, source_dir, native_dir, scoped_dir,
                       pc_binary, owned_game, *, upstream, compiler="gcc"):
    directory = _private_directory(handoff_dir)
    if (directory / HANDOFF).exists() or (directory / HANDOFF).is_symlink():
        raise ValueError("local capture handoff already exists")
    record = _verified_handoff(
        directory, source_dir, native_dir, scoped_dir, pc_binary,
        owned_game, upstream=upstream, compiler=compiler)
    raw = (json.dumps(record, sort_keys=True, separators=(",", ":"))
           + "\n").encode("utf-8")
    if record != _verified_handoff(
            directory, source_dir, native_dir, scoped_dir,
            pc_binary, owned_game, upstream=upstream, compiler=compiler):
        raise ValueError("local capture evidence changed before handoff publication")
    _publish(directory, HANDOFF, raw)
    return {"local_capture_handoff_sha256": _sha(raw),
            "gpu_draw_frame": record["gpu_draw_frame"],
            "source_gte_gpu_witness_verified": True,
            "live_kernel_executable_observed":
                record["live_kernel_executable_observed"],
            "gameplay_origin_authenticated": False,
            "gameplay_bytes_emitted": False}


def verify_local_capture(handoff_dir, source_dir, native_dir, scoped_dir,
                         pc_binary, owned_game, *, upstream, compiler="gcc"):
    directory = _private_directory(handoff_dir)
    raw = private_file(directory, HANDOFF, max_bytes=4096)
    record = _validated_handoff(raw)
    checked = _verified_handoff(
        directory, source_dir, native_dir, scoped_dir,
        pc_binary, owned_game, upstream=upstream, compiler=compiler)
    if record != checked or private_file(directory, HANDOFF, max_bytes=4096) != raw:
        raise ValueError("local MAP02 handoff differs from verified captured evidence")
    return {"local_capture_handoff_sha256": _sha(raw),
            "gpu_draw_frame": record["gpu_draw_frame"],
            "source_gte_gpu_witness_verified": True,
            "live_kernel_executable_observed":
                record["live_kernel_executable_observed"],
            "original_gameplay_authenticated": False,
            "physical_ps1_equivalence_proven": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("operation", choices=("prepare", "seal", "verify"))
    p.add_argument("private_handoff_dir", type=Path)
    p.add_argument("--pc-binary", type=Path, required=True)
    p.add_argument("--owned-game-image", type=Path, required=True)
    p.add_argument("--upstream-checkout", type=Path, required=True)
    p.add_argument("--frame", type=int)
    p.add_argument("--source-bundle", type=Path)
    p.add_argument("--native-windows", type=Path)
    p.add_argument("--scoped-capture", type=Path)
    p.add_argument("--compiler", default="gcc")
    a = p.parse_args()
    try:
        if a.operation == "prepare":
            if a.frame is None:
                raise ValueError("prepare needs explicit --frame")
            result = prepare_local_capture(
                a.private_handoff_dir, a.pc_binary, a.owned_game_image,
                frame=a.frame, upstream=a.upstream_checkout)
        else:
            if not all((a.source_bundle, a.native_windows, a.scoped_capture)):
                raise ValueError("seal/verify require source, windows and scoped directories")
            fn = seal_local_capture if a.operation == "seal" else verify_local_capture
            result = fn(
                a.private_handoff_dir, a.source_bundle,
                a.native_windows, a.scoped_capture,
                a.pc_binary, a.owned_game_image,
                upstream=a.upstream_checkout, compiler=a.compiler)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        p.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
