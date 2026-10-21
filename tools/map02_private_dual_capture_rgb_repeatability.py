#!/usr/bin/env python3
"""Owner-local TWO-BUNDLE PNG-pixel repeatability audit for MAP02 review.

Validates each supplied source-BK2/plan/Lua-log/PNG chain before comparisons.
Two matching directories are NOT proof of two actual emulator executions.
Never send private screenshots, input frame numbers or output JSON to CI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

from tools.verify_map02_private_neutral_capture_chain import (
    parse_plan, verify as verify_chain,
)
from tools.verify_map02_private_visual_candidates import read_png_private
from tools.map02_private_png_visual_diff import (
    compare_private_rgb8, decode_private_rgb8,
)
from tools.map02_private_visual_diff_triage import save_private_report

SCHEMA = "vh.map02.private-dual-bundle-rgb-repeatability.v1"
MAX_FRAMES = 30
MAX_EVIDENCE_FILE_BYTES = 128 * 1024 * 1024
ROLES = ("before", "middle", "after")


def _hash_source_file(digest, label: str, path: Path) -> None:
    """Add one bounded, race-checked source file to a local aggregate digest."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("capture evidence file must not be a symlink")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_size < 0
                or before.st_size > MAX_EVIDENCE_FILE_BYTES):
            raise ValueError("capture evidence file is not regular or exceeds bounds")
        encoded_label = label.encode("ascii")
        digest.update(len(encoded_label).to_bytes(4, "big"))
        digest.update(encoded_label)
        digest.update(before.st_size.to_bytes(8, "big"))
        count = 0
        with os.fdopen(os.dup(fd), "rb") as source:
            while True:
                block = source.read(1024 * 1024)
                if not block:
                    break
                count += len(block)
                digest.update(block)
        after = os.fstat(fd)
        if (count != before.st_size
                or (before.st_dev, before.st_ino, before.st_size,
                    before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_dev, after.st_ino, after.st_size,
                    after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError("capture evidence changed while being hashed")
    finally:
        os.close(fd)


def _preflight_source_path(path: Path, *, directory: bool) -> None:
    """Reject missing, nonregular or Git-contained owner files before hashing."""
    source = Path(path)
    if source.is_symlink():
        raise ValueError("private capture evidence path must not be a symlink")
    if directory:
        if not source.is_dir():
            raise ValueError("private capture evidence root must be a directory")
    elif not source.is_file():
        raise ValueError("private capture evidence source must be a regular file")
    real = source.resolve(strict=True)
    info = real.stat()
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("private capture evidence root must be a directory")
    elif not stat.S_ISREG(info.st_mode):
        raise ValueError("private capture evidence source must be regular")
    for parent in (real, *real.parents):
        marker = parent / ".git"
        if marker.exists() or marker.is_symlink():
            raise ValueError("owner-private capture evidence must stay outside Git")


def capture_evidence_digest(
    private_bk2: Path, private_plan: Path,
    log_one: Path, root_one: Path, log_two: Path, root_two: Path,
    planned: list[tuple[int, str, int, str]],
) -> str:
    """Return one opaque digest of the exact inputs, logs and planned PNG bytes."""
    digest = hashlib.sha256()
    digest.update(b"vh.map02.private-capture-evidence.v1\\0")
    for label, path in (
        ("source-bk2", private_bk2),
        ("canonical-plan", private_plan),
        ("run1-log", log_one),
        ("run2-log", log_two),
    ):
        _hash_source_file(digest, label, Path(path))
    for group, role, frame, _held in planned:
        filename = "vh_review_w%02d_%s_counter_%07d.png" % (
            group, role, frame + 1)
        for run_label, root in (("run1", root_one), ("run2", root_two)):
            label = "%s:%d:%s:%d" % (run_label, group, role, frame)
            _hash_source_file(digest, label, Path(root) / filename)
    return digest.hexdigest()


def _separate_real_files(first: Path, second: Path) -> None:
    """Refuse same path, symlink path or same inode, but not claim independence."""
    a, b = Path(first), Path(second)
    if a.is_symlink() or b.is_symlink():
        raise ValueError("supplied capture path must not be symlink")
    if not a.exists() or not b.exists():
        raise ValueError("capture path unavailable")
    if a.resolve() == b.resolve() or os.path.samefile(a, b):
        raise ValueError("two capture bundles must not share the same local object")


def verify(private_bk2: Path, private_plan: Path,
           log_one: Path, root_one: Path,
           log_two: Path, root_two: Path,
           *, minimum: int = 180, maximum: int = 1800,
           after: int = 1663, before: int = 933949,
           pixel_threshold: int = 0) -> dict:
    """Compare *provided* per-input screenshots for image reproducibility."""
    if type(pixel_threshold) is not int or not 0 <= pixel_threshold <= 254:
        raise ValueError("pixel threshold must be an integer 0..254")
    _separate_real_files(log_one, log_two)
    _separate_real_files(root_one, root_two)
    for source_path in (private_bk2, private_plan, log_one, log_two):
        _preflight_source_path(source_path, directory=False)
    for root_path in (root_one, root_two):
        _preflight_source_path(root_path, directory=True)
    plan_snapshot, planned = parse_plan(private_plan)
    evidence_before = capture_evidence_digest(
        private_bk2, private_plan, log_one, root_one, log_two, root_two, planned,
    )
    if parse_plan(private_plan)[0] != plan_snapshot:
        raise ValueError("private capture plan changed before audit")

    # Critical: both bundles are independently checked against the same
    # original BK2 frame plan, without trusting their own marker lines.
    proof_one = verify_chain(
        private_bk2, private_plan, log_one, root_one,
        minimum=minimum, maximum=maximum, after=after, before=before)
    proof_two = verify_chain(
        private_bk2, private_plan, log_two, root_two,
        minimum=minimum, maximum=maximum, after=after, before=before)
    if (proof_one["screenshot_count"] != proof_two["screenshot_count"]
            or not 3 <= proof_one["screenshot_count"] <= MAX_FRAMES):
        raise ValueError("source capture bundle counts disagree")

    if len(planned) != proof_one["screenshot_count"]:
        raise ValueError("private capture plan length disagrees with audit")
    inodes = set()
    compared = []
    rgb_matches = 0
    png_matches = 0
    differing = 0
    for group, role, frame, _ in planned:
        filename = "vh_review_w%02d_%s_counter_%07d.png" % (
            group, role, frame + 1)
        pair = []
        for root in (Path(root_one), Path(root_two)):
            # Avoid accidentally using hardlinks across the two purported
            # runs or cross-linking different frame names in distinct roots.
            file_path = root / filename
            fstat = os.stat(file_path, follow_symlinks=False)
            if not stat.S_ISREG(fstat.st_mode):
                raise ValueError("image path is not a regular screenshot file")
            identity = (fstat.st_dev, fstat.st_ino)
            if identity in inodes:
                raise ValueError("screenshot inode reused across capture bundles")
            inodes.add(identity)
            pair.append(read_png_private(root, filename))

        first, second = pair
        bytes_identical = first == second
        png_matches += int(bytes_identical)
        rgb_first = decode_private_rgb8(first)
        rgb_second = decode_private_rgb8(second)
        difference = compare_private_rgb8(
            rgb_first, rgb_second, threshold=pixel_threshold)
        rgb_identical = rgb_first == rgb_second
        rgb_matches += int(rgb_identical)
        differing += int(not rgb_identical)
        compared.append({
            "review_group": group,
            "frame_role": role,
            "same_decoded_rgb_pixels": rgb_identical,
            "same_png_file_bytes": bytes_identical,
            "cross_bundle": difference,
        })

    if parse_plan(private_plan)[0] != plan_snapshot:
        raise ValueError("private capture plan changed during audit")
    evidence_after = capture_evidence_digest(
        private_bk2, private_plan, log_one, root_one, log_two, root_two, planned,
    )
    if evidence_after != evidence_before:
        raise ValueError("private capture evidence changed during audit")

    # Rank mismatches first. Order of captured positions remains recoverable
    # from the group and role; no sensitive private frame indices are emitted.
    roles = {name: idx for idx, name in enumerate(ROLES)}
    compared.sort(key=lambda item: (
        -item["cross_bundle"]["fraction_pixels_above_threshold"],
        -item["cross_bundle"]["mean_absolute_rgb_channel_delta"],
        item["review_group"], roles[item["frame_role"]],
    ))
    return {
        "schema": SCHEMA,
        "source_capture_evidence_sha256": evidence_after,
        "supplied_capture_bundle_count": 2,
        "compared_screenshot_positions": len(compared),
        "exact_decoded_rgb_matches": rgb_matches,
        "identical_png_file_bytes": png_matches,
        "decoded_rgb_discrepancy_positions": differing,
        "pixel_change_threshold": pixel_threshold,
        "both_source_bk2_capture_chains_passed_integrity_audit": True,
        "no_local_capture_inode_reused": True,
        "all_decoded_rgb_images_repeated_exactly": differing == 0,
        "matches_and_differences_by_review_position": compared,
        "two_actual_octoshock_runs_authenticated": False,
        "independent_replay_executions_authenticated": False,
        "correct_input_to_display_offset_verified": False,
        "scene_transition_verified": False,
        "map02_start_frame_identified": False,
        "source_native_gpu_vram_verified": False,
        "private_png_or_bk2_uploaded": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("owner_private_bk2", type=Path)
    p.add_argument("owner_private_plan", type=Path)
    p.add_argument("run_one_private_log", type=Path)
    p.add_argument("run_one_png_directory", type=Path)
    p.add_argument("run_two_private_log", type=Path)
    p.add_argument("run_two_png_directory", type=Path)
    p.add_argument("--private-report-output", required=True, type=Path)
    p.add_argument("--pixel-change-threshold", default=0, type=int)
    p.add_argument("--min-neutral-frames", default=180, type=int)
    p.add_argument("--max-neutral-frames", default=1800, type=int)
    p.add_argument("--after-input-frame", default=1663, type=int)
    p.add_argument("--before-input-frame", default=933949, type=int)
    args = p.parse_args()
    try:
        output = verify(
            args.owner_private_bk2, args.owner_private_plan,
            args.run_one_private_log, args.run_one_png_directory,
            args.run_two_private_log, args.run_two_png_directory,
            minimum=args.min_neutral_frames,
            maximum=args.max_neutral_frames,
            after=args.after_input_frame, before=args.before_input_frame,
            pixel_threshold=args.pixel_change_threshold,
        )
        save_private_report(output, args.private_report_output)
    except (OSError, ValueError, TypeError, UnicodeError, RuntimeError):
        p.error("private dual-capture RGB-repeatability audit unavailable")
    print(
        "VH_MAP02_DUAL_RGB_AUDIT_COMPLETE supplied_bundles=2 "
        "compared=%d decoded_rgb_identical=%d disagreements=%d "
        "real_emulation_authenticated=0 map02_identified=0"
        % (output["compared_screenshot_positions"],
           output["exact_decoded_rgb_matches"],
           output["decoded_rgb_discrepancy_positions"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
