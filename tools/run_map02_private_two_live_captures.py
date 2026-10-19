#!/usr/bin/env python3
"""Run two private Linux ELF/GPU captures and compare their full VRAM timelines.

This is a local, synthetic-testable repeatability tool. A pinned ELF
is launched twice with the SAME frame and argv. Independent BGR555
frame and GPU event/snapshot evidence is replayed; it never certifies
original retail gameplay, a PlayStation disc or authentic PS1 pixels.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.capture_map02_live_frame_pipe import capture, _fingerprint_fd
from tools.map02_linux_elf_process_image import require_elf_image
from tools.audit_map02_private_frame_repeatability import (
    audit, _require_gpu_snapshot_aggregate_consistency,
    _require_terminal_gpu_frame_consistency,
    _joint_gpu_vram_first_divergence,
)
from tools.prepare_map02_private_frame_pair import _directory, _check_directory, WIDTH, HEIGHT
from tools.run_map02_private_joint_capture_audit import _session_inode_witness
from tools.replay_map02_live_frame_receipt import (
    _read_private_file, RECEIPT_NAME, MAX_RECEIPT,
)

SCHEMA = "vh.map02.private-two-live-elf-gpu-runs.v1"
CAPTURE_SCHEMA = "vh.map02.live-child-pipe-bgr555-gpu.v1"
AUDIT_SCHEMA = "vh.map02.private-two-elf-gpu-frame-repeatability.v1"


def _elf_file_identity(info):
    return tuple(getattr(info, field) for field in (
        "st_dev", "st_ino", "st_size", "st_mode", "st_uid", "st_gid",
        "st_nlink", "st_mtime_ns", "st_ctime_ns"))


def _require_held_elf_image(fd, path, expected_sha256, original_identity=None):
    """Read and pin one ELF inode, not only its re-creatable SHA-256 bytes.

    The same descriptor remains open during both real child launches and
    the full native GPU/VRAM audit. A same-byte path swap between launches
    is rejected before the second run can be issued.
    """
    held = os.fstat(fd)
    observed = os.stat(path, follow_symlinks=False)
    identity = _elf_file_identity(held)
    if (not stat.S_ISREG(held.st_mode) or not held.st_mode & 0o111
            or not 0 < held.st_size <= 1024 * 1024 * 1024
            or identity != _elf_file_identity(observed)
            or (original_identity is not None and identity != original_identity)):
        raise ValueError("MAP02 pinned two-run ELF identity changed or invalid")
    require_elf_image(fd)
    size, sha = _fingerprint_fd(fd)
    if sha != expected_sha256 or size != held.st_size:
        raise ValueError("MAP02 pinned two-run ELF SHA-256 mismatch")
    if (_elf_file_identity(os.fstat(fd)) != identity
            or _elf_file_identity(os.stat(path, follow_symlinks=False))
            != identity):
        raise ValueError("MAP02 pinned two-run ELF changed during verification")
    return identity


def _require_bit_exact_gpu_timeline(report):
    """Accept only bit-exact *independent* journals and every GPU snapshot.

    Terminal pixel equality alone is insufficient: earlier native VRAM
    snapshots may diverge and reconverge. Identical JSONL event records
    alone are likewise insufficient: native VRAM bytes can differ.
    """
    # A successful strict claim also requires coherent aligned event/VRAM
    # counts and a *present* all-null joint divergence witness. Otherwise
    # a stale/mutated report could assert exactness while contradicting its
    # own new first-divergence evidence.
    joint_keys = (
        "first_joint_gpu_divergence_index",
        "first_joint_gpu_divergence_pair_index",
        "first_joint_gpu_divergence_phase",
        "first_joint_gpu_divergence_kind",
    )
    if (type(report) is not dict
            or any(key not in report or report[key] is not None
                   for key in joint_keys)
            or any(type(report.get(key)) is not int for key in (
                "first_gpu_event_count", "second_gpu_event_count",
                "first_gpu_vram_snapshot_count",
                "second_gpu_vram_snapshot_count"))
            or report["first_gpu_event_count"] != report["second_gpu_event_count"]
            or report["first_gpu_event_count"] != report.get("gpu_event_records_compared")
            or report["first_gpu_vram_snapshot_count"]
               != report["second_gpu_vram_snapshot_count"]
            or report["first_gpu_vram_snapshot_count"]
               != report.get("gpu_vram_snapshots_compared")
            or report["first_gpu_event_count"]
               != report["first_gpu_vram_snapshot_count"]
            or report.get("repeated_full_gpu_vram_snapshot_sequence_identical") is not True
            or report.get("gpu_vram_timeline_commitments_identical") is not True
            or type(report.get("first_gpu_vram_timeline_sha256")) is not str
            or type(report.get("second_gpu_vram_timeline_sha256")) is not str
            or len(report["first_gpu_vram_timeline_sha256"]) != 64
            or len(report["second_gpu_vram_timeline_sha256"]) != 64
            or any(c not in "0123456789abcdef"
                   for c in report["first_gpu_vram_timeline_sha256"])
            or any(c not in "0123456789abcdef"
                   for c in report["second_gpu_vram_timeline_sha256"])
            or report["first_gpu_vram_timeline_sha256"]
               != report["second_gpu_vram_timeline_sha256"]
            or report.get("repeated_native_frame_pixels_identical") is not True
            or report.get("repeated_gpu_final_vram_identical") is not True
            or report.get("repeated_gpu_event_journal_identical") is not True
            or report.get("repeated_gpu_event_records_identical") is not True
            or type(report.get("different_gpu_event_records_in_common_prefix")) is not int
            or report["different_gpu_event_records_in_common_prefix"] != 0
            or type(report.get("unmatched_gpu_event_records")) is not int
            or report["unmatched_gpu_event_records"] != 0
            or type(report.get("gpu_event_records_compared")) is not int
            or report["gpu_event_records_compared"] < 2
            or type(report.get("gpu_vram_snapshots_compared")) is not int
            or report["gpu_vram_snapshots_compared"] < 2
            or type(report.get("unmatched_gpu_vram_snapshots")) is not int
            or report["unmatched_gpu_vram_snapshots"] != 0
            or type(report.get("different_gpu_vram_snapshots_in_common_prefix")) is not int
            or report["different_gpu_vram_snapshots_in_common_prefix"] != 0
            or type(report.get("different_bgr555_pixels")) is not int
            or report["different_bgr555_pixels"] != 0
            or type(report.get("gpu_vram_equal_different_state_transitions")) is not int
            or report["gpu_vram_equal_different_state_transitions"] != 0):
        raise ValueError("MAP02 independent native GPU timelines are not bit-exact")
    # The main audit checks these on its own path; repeat the independent
    # calculations at the final strict acceptance boundary as well. A
    # post-audit mutation of one secondary phase/history/digest field must
    # never become a successful bit-exact receipt by preserving only the
    # legacy all-true booleans and zero mismatch counters.
    try:
        # The source-labelled GPU journal digests and replay-verified
        # DrawOTag pair counts are also part of a strict equality claim.
        # Recheck them here, since a mutated post-audit report could keep
        # the "identical" booleans while changing the source commitments.
        first_digest = report.get("first_gpu_journal_sha256")
        second_digest = report.get("second_gpu_journal_sha256")
        if (any(type(digest) is not str or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)
                for digest in (first_digest, second_digest))
                or first_digest != second_digest
                or any(type(report.get(key)) is not int for key in (
                    "first_gpu_pairs_verified", "second_gpu_pairs_verified"))
                or report["first_gpu_pairs_verified"] * 2 !=
                   report["first_gpu_event_count"]
                or report["second_gpu_pairs_verified"] * 2 !=
                   report["second_gpu_event_count"]):
            raise ValueError("GPU journal commitment/pair mismatch")
        _require_gpu_snapshot_aggregate_consistency(report)
        _require_terminal_gpu_frame_consistency(
            report,
            different=report["different_bgr555_pixels"],
            changed_scanlines=report["changed_scanlines"],
            stp_bit_differences=report["stp_bit_differences"],
            first_image_sha256=report["first_image_sha256"],
            second_image_sha256=report["second_image_sha256"],
        )
        witnessed = _joint_gpu_vram_first_divergence(report, report)
        if any(witnessed[key] is not None for key in joint_keys):
            raise ValueError("unexpected GPU divergence")
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(
            "MAP02 independent native GPU timelines are not bit-exact"
        ) from exc


def _validated_launch_args(frame, executable_sha256, args, timeout,
                           require_identical_gpu_timeline):
    """Share the exact argument restrictions between preview and live launch."""
    if (type(frame) is not int or not 1 <= frame <= 0xffffffff
            or type(executable_sha256) is not str
            or len(executable_sha256) != 64
            or any(c not in "0123456789abcdef" for c in executable_sha256)
            or type(timeout) not in (int, float) or not 0 < timeout <= 60
            or type(require_identical_gpu_timeline) is not bool
            or not isinstance(args, (tuple, list))
            or any(type(arg) is not str or "\x00" in arg for arg in args)):
        raise ValueError("MAP02 two-run launch arguments invalid")
    # Freeze caller-owned mutable argv for the entire operation.
    return tuple(args)


def _require_private_capture_destination(path, fd):
    """Refuse a Git worktree or a non-writable private capture directory.

    Owner-only permissions are not sufficient: an operator might otherwise
    write original GPU/VRAM bytes under a public repository by accident.
    Check both the literal path and its real target, including linked
    worktrees whose .git entry is a FILE rather than a directory.
    This is a local preventative check, not a sandbox or publication proof.
    """
    if stat.S_IMODE(os.fstat(fd).st_mode) & 0o700 != 0o700:
        raise ValueError("MAP02 capture directory requires private 0700 permissions")
    for root in (Path(path).absolute(), Path(path).resolve(strict=True)):
        for parent in (root, *root.parents):
            if parent.name == ".git":
                raise ValueError("MAP02 private capture directory is in a Git worktree")
            try:
                os.lstat(parent / ".git")
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise ValueError(
                    "MAP02 private capture Git boundary cannot be verified"
                ) from exc
            else:
                raise ValueError(
                    "MAP02 private capture directory is in a Git worktree")


def preflight(executable, first_frame, first_journal, second_frame,
              second_journal, *, frame, executable_sha256, args=(),
              timeout=10, require_identical_gpu_timeline=False):
    """Read-only private launch readiness check; never execute an ELF.

    All four output directories must ALREADY exist, be owner-private,
    distinct, and empty. This does not create any file/receipt/snapshot.
    A subsequent real launch MUST repeat its own checks since preflight
    cannot pin its descriptors across separate CLI invocations.
    """
    _validated_launch_args(frame, executable_sha256, args, timeout,
                           require_identical_gpu_timeline)
    executable = Path(executable).absolute()
    folders = tuple(Path(p).absolute() for p in (
        first_frame, first_journal, second_frame, second_journal))
    opened, identities = [], []
    exe_fd = None
    try:
        for path in folders:
            fd, identity = _directory(path, empty=True)
            opened.append(fd)
            _require_private_capture_destination(path, fd)
            identities.append(identity)
        if len({identity[:2] for identity in identities}) != 4:
            raise ValueError("MAP02 two-run private directory roles overlap")
        exe_fd = os.open(executable, os.O_RDONLY | os.O_NOFOLLOW |
                         os.O_CLOEXEC | os.O_NONBLOCK)
        _require_held_elf_image(exe_fd, executable, executable_sha256)
        for fd, path, identity in zip(opened, folders, identities):
            _check_directory(fd, path, identity)
            _require_private_capture_destination(path, fd)
            if os.listdir(fd):
                raise ValueError("MAP02 two-run private directory not empty")
        _require_held_elf_image(exe_fd, executable, executable_sha256)
        return {
            "schema": "vh.map02.private-two-live-elf-preflight.v1",
            "frame": frame,
            "width": WIDTH,
            "height": HEIGHT,
            "executable_sha256": executable_sha256,
            "four_owner_private_empty_directory_roles_verified": True,
            "same_executable_inode_and_sha_checked_at_preflight": True,
            "same_elf_arguments_validated": True,
            "strict_gpu_timeline_match_requested": require_identical_gpu_timeline,
            "native_elf_launched": False,
            "two_native_elf_captures_and_complete_replays_verified": False,
            "strict_gpu_timeline_match_verified": False,
            "actual_gameplay_rendering_authenticated": False,
            "ps1_hardware_pixel_equivalence_verified": False,
            "hd_replacement_authorized": False,
            "private_pixel_bytes_or_paths_emitted": False,
        }
    finally:
        if exe_fd is not None:
            os.close(exe_fd)
        for fd in reversed(opened):
            os.close(fd)


# Explicit egress contract for the digest-only independent repeatability
# report. A future audit refactor must consciously extend this allowlist;
# never forward novel paths, raw VRAM, logs, or arbitrary nested values to
# public CI/CLI JSON just because the top-level witness claims safety.
_AUDIT_SAFE_BOOLEAN_FIELDS = frozenset((
        "actual_gameplay_rendering_authenticated",
        "four_private_file_inventories_stable_through_replays",
        "gpu_journal_writer_kernel_authenticated",
        "gpu_vram_divergence_reappeared_after_reconvergence",
        "gpu_vram_reconverged_at_common_prefix_end",
        "gpu_vram_timeline_commitments_identical",
        "hd_replacement_authorized",
        "private_pixel_bytes_or_paths_emitted",
        "ps1_hardware_pixel_equivalence_verified",
        "repeated_full_gpu_vram_snapshot_sequence_identical",
        "repeated_gpu_event_journal_identical",
        "repeated_gpu_event_records_identical",
        "repeated_gpu_final_vram_identical",
        "repeated_native_frame_pixels_identical",
        "two_full_replays_per_capture_verified",
))
_AUDIT_SAFE_DIGEST_FIELDS = frozenset((
        "executable_sha256",
        "first_gpu_journal_sha256",
        "second_gpu_journal_sha256",
        "first_gpu_vram_timeline_sha256",
        "second_gpu_vram_timeline_sha256",
        "first_image_sha256",
        "second_image_sha256",
))
_AUDIT_SAFE_OPTIONAL_INDEX_FIELDS = frozenset((
        "first_different_gpu_draw_pair_index",
        "first_different_gpu_event_pair_index",
        "first_different_gpu_event_record_index",
        "first_different_gpu_snapshot_changed_pixels",
        "first_different_gpu_snapshot_changed_scanlines",
        "first_different_gpu_snapshot_stp_bit_differences",
        "first_different_gpu_vram_snapshot_index",
        "first_joint_gpu_divergence_index",
        "first_joint_gpu_divergence_pair_index",
        "first_reconverged_gpu_vram_snapshot_index",
        "last_different_gpu_vram_snapshot_index",
))
_AUDIT_SAFE_NONNEGATIVE_FIELDS = frozenset((
        "first_gpu_event_count",
        "second_gpu_event_count",
        "gpu_event_records_compared",
        "different_gpu_event_records_in_common_prefix",
        "unmatched_gpu_event_records",
        "first_gpu_vram_snapshot_count",
        "second_gpu_vram_snapshot_count",
        "gpu_vram_snapshots_compared",
        "different_gpu_vram_snapshots_in_common_prefix",
        "different_gpu_before_vram_snapshots",
        "different_gpu_after_vram_snapshots",
        "unmatched_gpu_vram_snapshots",
        "gpu_vram_equal_different_state_transitions",
        "frame",
        "width",
        "height",
        "first_gpu_pairs_verified",
        "second_gpu_pairs_verified",
        "different_bgr555_pixels",
        "changed_scanlines",
        "stp_bit_differences",
))
_AUDIT_SAFE_ENUMS = {
    "first_different_gpu_event_phase": (None, "before", "after"),
    "first_different_gpu_snapshot_phase": (None, "before", "after"),
    "first_joint_gpu_divergence_phase": (None, "before", "after"),
    "first_joint_gpu_divergence_kind": (
        None, "event-only", "vram-only", "event-and-vram", "unmatched-tail"),
}
_AUDIT_SAFE_KEYS = (
    _AUDIT_SAFE_BOOLEAN_FIELDS | _AUDIT_SAFE_DIGEST_FIELDS |
    _AUDIT_SAFE_OPTIONAL_INDEX_FIELDS | _AUDIT_SAFE_NONNEGATIVE_FIELDS |
    frozenset(_AUDIT_SAFE_ENUMS) | {"schema"}
)


def _require_safe_public_audit_summary(report):
    """Refuse unsafe/extra fields before any audit summary can be emitted."""
    if (type(report) is not dict
            or report.keys() != _AUDIT_SAFE_KEYS
            or report.get("schema") != AUDIT_SCHEMA
            or report.get("private_pixel_bytes_or_paths_emitted") is not False):
        raise ValueError("MAP02 public audit summary fields unsafe")
    if any(type(report[key]) is not bool
           for key in _AUDIT_SAFE_BOOLEAN_FIELDS):
        raise ValueError("MAP02 public audit summary fields unsafe")
    if any(type(report[key]) is not str or len(report[key]) != 64
           or any(c not in "0123456789abcdef" for c in report[key])
           for key in _AUDIT_SAFE_DIGEST_FIELDS):
        raise ValueError("MAP02 public audit summary fields unsafe")
    if any(value is not None and
           (type(value) is not int or value < 0)
           for value in (report[key] for key in _AUDIT_SAFE_OPTIONAL_INDEX_FIELDS)):
        raise ValueError("MAP02 public audit summary fields unsafe")
    if any(type(report[key]) is not int or report[key] < 0
           for key in _AUDIT_SAFE_NONNEGATIVE_FIELDS):
        raise ValueError("MAP02 public audit summary fields unsafe")
    if any(report[key] not in allowed or
           (report[key] is not None and type(report[key]) is not str)
           for key, allowed in _AUDIT_SAFE_ENUMS.items()):
        raise ValueError("MAP02 public audit summary fields unsafe")
    if (report["width"], report["height"]) != (WIDTH, HEIGHT):
        raise ValueError("MAP02 public audit summary fields unsafe")


def run(executable, first_frame, first_journal, second_frame, second_journal,
        *, frame, executable_sha256, args=(), timeout=10,
        require_identical_gpu_timeline=False):
    """Launch the same SHA-pinned ELF twice and audit independent GPU captures.

    Requires four pre-existing, distinct, empty owner-private directories.
    Failed captures leave already-created private evidence available for
    local diagnosis, but NEVER issue a successful summary.
    """
    # Preserve the SAME immutable argv for both child processes even if
    # the caller mutates its original list after the first launch.
    args = _validated_launch_args(
        frame, executable_sha256, args, timeout,
        require_identical_gpu_timeline)

    executable = Path(executable).absolute()
    folders = tuple(Path(p).absolute() for p in (
        first_frame, first_journal, second_frame, second_journal))
    opened, identities = [], []
    exe_fd = None
    try:
        # Check ALL destinations before executing either child. Aliasing a
        # second journal to the first frame path must not publish anything.
        for path in folders:
            fd, identity = _directory(path, empty=True)
            opened.append(fd)
            _require_private_capture_destination(path, fd)
            identities.append(identity)
        if len({identity[:2] for identity in identities}) != 4:
            raise ValueError("MAP02 two-run private directory roles overlap")

        # Pin exactly one actual executable inode BEFORE the first launch,
        # and keep its FD for the entire two-run audit.
        exe_fd = os.open(executable, os.O_RDONLY | os.O_NOFOLLOW |
                         os.O_CLOEXEC | os.O_NONBLOCK)
        elf_identity = _require_held_elf_image(
            exe_fd, executable, executable_sha256)

        witnesses = []
        # Freeze the two actual native CAPTURE receipt claims as immutable
        # scalar values before any independent replay starts. This gives a
        # second source of evidence when a post-replay report is mutated.
        launch_claims = []
        for offset in (0, 2):
            _require_held_elf_image(exe_fd, executable, executable_sha256,
                                    original_identity=elf_identity)
            frame_dir, journal_dir = folders[offset:offset + 2]
            for role_fd, role_path in zip(opened[offset:offset + 2],
                                          folders[offset:offset + 2]):
                _require_private_capture_destination(role_path, role_fd)
            published = []
            def pin(held_output_fd, held_journal_fd):
                if held_journal_fd is None:
                    raise ValueError("MAP02 two-run capture lacks held GPU journal descriptor")
                published.append(_session_inode_witness(
                    frame_dir, journal_dir, held_output_fd=held_output_fd,
                    held_journal_fd=held_journal_fd))

            receipt = capture(
                executable, frame_dir, frame=frame, width=WIDTH,
                height=HEIGHT, executable_sha256=executable_sha256,
                timeout=timeout, args=args, gpu_journal_dir=journal_dir,
                post_publish_witness=pin)
            if (type(receipt) is not dict or
                    receipt.get("schema") != CAPTURE_SCHEMA or
                    receipt.get("frame") != frame or
                    (receipt.get("width"), receipt.get("height")) != (WIDTH, HEIGHT)
                    or receipt.get("image_sha256") !=
                    receipt.get("terminal_gpu_after_vram_sha256")
                    or receipt.get("executable_sha256") != executable_sha256
                    or receipt.get("child_writable_gpu_journal_fd_observed") is not True
                    or receipt.get("gpu_journal_writer_kernel_authenticated") is not False
                    or receipt.get("hd_replacement_authorized") is not False
                    or len(published) != 1):
                raise ValueError("MAP02 two-run native capture receipt incomplete")
            # Bind the in-memory result returned by the capture launcher to
            # the precise canonical receipt actually saved in the pinned
            # output directory. Flags not duplicated in the final audit
            # must not be silently mutable after native publication.
            saved_receipt, _ = _read_private_file(
                opened[offset], RECEIPT_NAME, max_bytes=MAX_RECEIPT)
            expected_receipt = (
                json.dumps(receipt, sort_keys=True) + "\n"
            ).encode("utf-8")
            if saved_receipt != expected_receipt:
                raise ValueError(
                    "MAP02 native capture return differs from published receipt")
            witness = _session_inode_witness(frame_dir, journal_dir)
            if witness != published[0]:
                raise ValueError("MAP02 two-run published frame/GPU files changed")
            witnesses.append(witness)
            launch_claims.append((
                receipt.get("image_sha256"),
                receipt.get("gpu_journal_sha256"),
                receipt.get("gpu_journal_pairs_verified"),
            ))
            _require_held_elf_image(exe_fd, executable, executable_sha256,
                                    original_identity=elf_identity)

        def verify_all_published():
            # A Git checkout can be initialized around the private output
            # paths AFTER one or both ELF children have already run. Recheck
            # every destination before/after independent replay, not merely
            # before the first/second capture.
            for role_fd, role_path in zip(opened, folders):
                _require_private_capture_destination(role_path, role_fd)
            for offset, witness in zip((0, 2), witnesses):
                if _session_inode_witness(*folders[offset:offset + 2]) != witness:
                    raise ValueError("MAP02 two-run published files changed during replay")

        verify_all_published()
        report = audit(*folders, executable)
        if (type(report) is not dict or report.get("schema") != AUDIT_SCHEMA
                or report.get("frame") != frame
                or report.get("executable_sha256") != executable_sha256
                or report.get("two_full_replays_per_capture_verified") is not True
                or report.get("four_private_file_inventories_stable_through_replays")
                   is not True
                or report.get("actual_gameplay_rendering_authenticated") is not False
                or report.get("ps1_hardware_pixel_equivalence_verified") is not False
                or report.get("gpu_journal_writer_kernel_authenticated") is not False
                or report.get("hd_replacement_authorized") is not False):
            raise ValueError("MAP02 two-run native repeatability witness invalid")
        _require_safe_public_audit_summary(report)
        # Compare source-labelled replay results to the immutable claims
        # captured at publication, not just to one another. Two FORGED
        # source digests could agree and fool a boolean-only strict gate.
        replay_claims = (
            (report.get("first_image_sha256"),
             report.get("first_gpu_journal_sha256"),
             report.get("first_gpu_pairs_verified")),
            (report.get("second_image_sha256"),
             report.get("second_gpu_journal_sha256"),
             report.get("second_gpu_pairs_verified")),
        )
        if tuple(launch_claims) != replay_claims:
            raise ValueError(
                "MAP02 independent replay disagrees with pinned capture receipts")
        verify_all_published()
        _require_held_elf_image(exe_fd, executable, executable_sha256,
                                original_identity=elf_identity)
        for fd, path, identity in zip(opened, folders, identities):
            _check_directory(fd, path, identity)
        # In normal mode a different but independently replay-verified
        # native GPU sequence is a *diagnostic*, not a capture failure.
        # The opt-in gate requires every intermediate VRAM snapshot, the
        # terminal frame AND the separate native GPU event JSONL to match.
        if require_identical_gpu_timeline:
            _require_bit_exact_gpu_timeline(report)
        # The strict predicate (or another late acceptance callback) runs
        # AFTER the last independent replay and can consume time. Recheck
        # publication provenance and exact pinned file identities once
        # more at the final point where a successful receipt is issued.
        verify_all_published()
        _require_held_elf_image(exe_fd, executable, executable_sha256,
                                original_identity=elf_identity)
        for fd, path, identity in zip(opened, folders, identities):
            _check_directory(fd, path, identity)
        return {
            **report,
            "schema": SCHEMA,
            "same_elf_arguments_used_for_both_launches": True,
            "two_native_elf_captures_and_complete_replays_verified": True,
            "same_executable_inode_and_sha_pinned_through_both_launches": True,
            "strict_gpu_timeline_match_required": require_identical_gpu_timeline,
            "strict_gpu_timeline_match_verified": require_identical_gpu_timeline,
            "original_ps1_reference_authenticated": False,
            "retail_gameplay_authenticated": False,
            "hd_replacement_authorized": False,
        }
    finally:
        if exe_fd is not None:
            os.close(exe_fd)
        for fd in reversed(opened):
            os.close(fd)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--executable", type=Path, required=True)
    p.add_argument("--executable-sha256", required=True)
    p.add_argument("--first-frame", type=Path, required=True)
    p.add_argument("--first-journal", type=Path, required=True)
    p.add_argument("--second-frame", type=Path, required=True)
    p.add_argument("--second-journal", type=Path, required=True)
    p.add_argument("--frame", type=int, required=True)
    p.add_argument("--timeout", type=int, default=10)
    p.add_argument("--elf-arg", action="append", default=[])
    p.add_argument("--require-identical-gpu-timeline", action="store_true",
                   help="reject independently valid but different GPU event/"
                        "VRAM snapshot/terminal frame sequences")
    p.add_argument("--dry-run", action="store_true",
                   help="check the four private directories and ELF SHA-256 "
                        "without launching, writing files or claiming a capture")
    ns = p.parse_args()
    try:
        operation = preflight if ns.dry_run else run
        report = operation(
            ns.executable, ns.first_frame, ns.first_journal,
            ns.second_frame, ns.second_journal,
            frame=ns.frame, executable_sha256=ns.executable_sha256,
            args=tuple(ns.elf_arg), timeout=ns.timeout,
            require_identical_gpu_timeline=ns.require_identical_gpu_timeline)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        p.error("MAP02 two independent private ELF captures failed verification")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
