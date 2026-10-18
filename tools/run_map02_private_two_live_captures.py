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
import subprocess

from tools.capture_map02_live_frame_pipe import capture
from tools.audit_map02_private_frame_repeatability import audit
from tools.prepare_map02_private_frame_pair import _directory, _check_directory, WIDTH, HEIGHT
from tools.run_map02_private_joint_capture_audit import _session_inode_witness

SCHEMA = "vh.map02.private-two-live-elf-gpu-runs.v1"
CAPTURE_SCHEMA = "vh.map02.live-child-pipe-bgr555-gpu.v1"
AUDIT_SCHEMA = "vh.map02.private-two-elf-gpu-frame-repeatability.v1"


def _require_bit_exact_gpu_timeline(report):
    """Accept only bit-exact *independent* journals and every GPU snapshot.

    Terminal pixel equality alone is insufficient: earlier native VRAM
    snapshots may diverge and reconverge. Identical JSONL event records
    alone are likewise insufficient: native VRAM bytes can differ.
    """
    if (type(report) is not dict
            or report.get("repeated_full_gpu_vram_snapshot_sequence_identical") is not True
            or report.get("repeated_native_frame_pixels_identical") is not True
            or report.get("repeated_gpu_final_vram_identical") is not True
            or report.get("repeated_gpu_event_journal_identical") is not True
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


def run(executable, first_frame, first_journal, second_frame, second_journal,
        *, frame, executable_sha256, args=(), timeout=10,
        require_identical_gpu_timeline=False):
    """Launch the same SHA-pinned ELF twice and audit independent GPU captures.

    Requires four pre-existing, distinct, empty owner-private directories.
    Failed captures leave already-created private evidence available for
    local diagnosis, but NEVER issue a successful summary.
    """
    if (type(frame) is not int or not 1 <= frame <= 0xffffffff
            or type(executable_sha256) is not str
            or len(executable_sha256) != 64
            or any(c not in "0123456789abcdef" for c in executable_sha256)
            or type(timeout) not in (int, float) or not 0 < timeout <= 60
            or type(require_identical_gpu_timeline) is not bool
            or not isinstance(args, (tuple, list))
            or any(type(arg) is not str or "\x00" in arg for arg in args)):
        raise ValueError("MAP02 two-run launch arguments invalid")

    executable = Path(executable).absolute()
    folders = tuple(Path(p).absolute() for p in (
        first_frame, first_journal, second_frame, second_journal))
    opened, identities = [], []
    try:
        # Check ALL destinations before executing either child. Aliasing a
        # second journal to the first frame path must not publish anything.
        for path in folders:
            fd, identity = _directory(path, empty=True)
            opened.append(fd)
            identities.append(identity)
        if len({identity[:2] for identity in identities}) != 4:
            raise ValueError("MAP02 two-run private directory roles overlap")

        witnesses = []
        for offset in (0, 2):
            frame_dir, journal_dir = folders[offset:offset + 2]
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
            witness = _session_inode_witness(frame_dir, journal_dir)
            if witness != published[0]:
                raise ValueError("MAP02 two-run published frame/GPU files changed")
            witnesses.append(witness)

        def verify_all_published():
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
        verify_all_published()
        for fd, path, identity in zip(opened, folders, identities):
            _check_directory(fd, path, identity)
        # In normal mode a different but independently replay-verified
        # native GPU sequence is a *diagnostic*, not a capture failure.
        # The opt-in gate requires every intermediate VRAM snapshot, the
        # terminal frame AND the separate native GPU event JSONL to match.
        if require_identical_gpu_timeline:
            _require_bit_exact_gpu_timeline(report)
        return {
            **report,
            "schema": SCHEMA,
            "same_elf_arguments_used_for_both_launches": True,
            "two_native_elf_captures_and_complete_replays_verified": True,
            "strict_gpu_timeline_match_required": require_identical_gpu_timeline,
            "strict_gpu_timeline_match_verified": require_identical_gpu_timeline,
            "original_ps1_reference_authenticated": False,
            "retail_gameplay_authenticated": False,
            "hd_replacement_authorized": False,
        }
    finally:
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
    ns = p.parse_args()
    try:
        report = run(
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
