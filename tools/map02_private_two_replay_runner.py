#!/usr/bin/env python3
"""Run two sequential owner-LOCAL BizHawk capture attempts and audit them.

No original disc, BIOS, BK2, screenshots, private paths or hashes may be sent
to public CI. A successful run proves only the local file/log chain; neither
actual independent cold boots nor MAP02 identity is authenticated here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from tools.map02_private_bk2_capture_plan import plan_lines, write_private_plan
from tools.map02_private_bizhawk_poweron_launch import (
    SCRIPT, DEFAULT_EMULATOR_TIMEOUT_SECONDS,
    MIN_EMULATOR_TIMEOUT_SECONDS, MAX_EMULATOR_TIMEOUT_SECONDS,
)
from tools.map02_private_disc_movie_preflight import (
    _assert_stable, _identity, _open_stable, _parse_cue, _read_at,
    _resolve_private_file, EXPECTED_BIN_BYTES, MAP02_BYTES, MAP02_LBA,
    MAX_CUE_BYTES, PVD_LBA, SECTOR_BYTES, USER_DATA_BYTES,
    inspect_pair, read_private_full_bin_sha256, _full_image_sha256, _read_cue,
)
from tools.map02_private_psx_firmware_probe import compare_firmware
from tools.map02_private_two_capture_audit import _private_root, audit_pair
from tools.verify_map02_private_neutral_capture_chain import verify


SCHEMA = "vh.map02.private-two-sequential-replays.v1"
PLAN_NAME = "vh-map02-review-plan.txt"
RUN_NAMES = ("vh-map02-cold-01", "vh-map02-cold-02")
MAX_PRIVATE_MOVIE_BYTES = 8 * 1024 * 1024
MOVIE_DIGEST_BLOCK_BYTES = 1024 * 1024
# Only these source sectors are pinned automatically. A full-BIN private
# SHA-256 reference is needed to check every sector of the original disc.
MAP02_SECTOR_COUNT = (MAP02_BYTES + USER_DATA_BYTES - 1) // USER_DATA_BYTES


def _disc_source_snapshot(cue_file: Path) -> tuple:
    """Pin private CUE bytes, file identity and audited raw BIN sectors.

    Deliberately does NOT claim whole-BIN content equality. No paths, source
    bytes or digests are printed, serialized, or uploaded.
    """
    cue = _resolve_private_file(cue_file)
    fd, before = _open_stable(cue)
    try:
        if not 0 < before.st_size <= MAX_CUE_BYTES:
            raise ValueError("private CUE outside bounded size")
        source = _read_at(fd, 0, before.st_size)
        if len(source) != before.st_size:
            raise ValueError("private CUE changed during read")
        bin_name = _parse_cue(source.decode("ascii"))
        _assert_stable(fd, cue, before)
        cue_receipt = (str(cue), _identity(before),
                       hashlib.sha256(source).digest())
    finally:
        os.close(fd)
    bin_path = _resolve_private_file(cue.parent / bin_name)
    fd, before = _open_stable(bin_path)
    try:
        if before.st_size != EXPECTED_BIN_BYTES:
            raise ValueError("private BIN size no longer matches audited profile")
        sampled = hashlib.sha256()
        for lba in (PVD_LBA, *range(MAP02_LBA, MAP02_LBA + MAP02_SECTOR_COUNT)):
            raw = _read_at(fd, lba * SECTOR_BYTES, SECTOR_BYTES)
            if len(raw) != SECTOR_BYTES:
                raise ValueError("private BIN sampled sector could not be read")
            sampled.update(raw)
        _assert_stable(fd, bin_path, before)
        bin_receipt = (str(bin_path), _identity(before), sampled.digest())
    finally:
        os.close(fd)
    return cue_receipt, bin_receipt


def _require_disc_unchanged(cue_file: Path, original_snapshot: tuple) -> None:
    if _disc_source_snapshot(cue_file) != original_snapshot:
        raise ValueError("owner-private disc source changed between capture attempts")


def _require_digest_reference_unchanged(
        reference_file: Path | None, initial_digest: str | None) -> None:
    """Recheck the owner-only digest file at every source checkpoint.

    The child launcher reads this reference independently. A changed value
    must never let consecutive runs silently verify different BIN images.
    No digest, file path or contents appear in public-safe output.
    """
    if reference_file is None:
        return
    if read_private_full_bin_sha256(reference_file) != initial_digest:
        raise ValueError(
            "owner-private full-BIN digest reference changed between capture attempts"
        )


def _require_full_bin_unchanged(
        cue_file: Path, expected_digest: str | None) -> None:
    """Re-hash ALL BIN bytes at a post-EmuHawk checkpoint, if requested.

    The prior sector snapshot cannot detect content changes elsewhere on
    the image. The separate owner-local reference is pinned by the caller.
    This checks on-disk bytes, NOT the actual media mounted by EmuHawk.
    Do not print the source path, the digest, or any original game bytes.
    """
    if expected_digest is None:
        return
    cue = _resolve_private_file(cue_file)
    bin_path = _resolve_private_file(cue.parent / _parse_cue(_read_cue(cue)))
    fd, before = _open_stable(bin_path)
    try:
        if before.st_size != EXPECTED_BIN_BYTES:
            raise ValueError("private complete BIN size changed")
        actual = _full_image_sha256(fd, before.st_size)
        _assert_stable(fd, bin_path, before)
    finally:
        os.close(fd)
    if actual != expected_digest:
        raise ValueError("private full BIN content changed after emulator process")


def _private_movie_identity(path: Path) -> bytes:
    """Fingerprint one bounded owner-local BK2; never print the digest.

    Both the open file descriptor and the pathname are checked before and
    after the read. The return value only exists in the local process.
    """
    source = Path(path)
    fd, before = _open_stable(source)
    try:
        if not 0 < before.st_size <= MAX_PRIVATE_MOVIE_BYTES:
            raise ValueError("owner-private BK2 identity outside bounded size")
        result = hashlib.sha256()
        remaining = before.st_size
        while remaining:
            block = os.read(fd, min(MOVIE_DIGEST_BLOCK_BYTES, remaining))
            if not block:
                raise ValueError("owner-private BK2 changed during read")
            result.update(block)
            remaining -= len(block)
        _assert_stable(fd, source, before)
        return result.digest()
    finally:
        os.close(fd)


def _require_movie_unchanged(path: Path, original_digest: bytes) -> None:
    if _private_movie_identity(path) != original_digest:
        raise ValueError("owner-private BK2 changed between capture attempts")


def _require_firmware_candidate_matches(
        movie: Path, private_bios_candidate: Path | None) -> None:
    """Compare private candidate to a unique recorded PSX firmware hash.

    Does not authenticate what EmuHawk mounted. Re-run at checkpoints to
    detect changed candidate bytes during either of two local launches.
    """
    if private_bios_candidate is None:
        return
    receipt = compare_firmware(movie, private_bios_candidate)
    if not receipt["candidate_bios_sha1_matches_movie_psx_firmware_metadata"]:
        raise ValueError("private PSX firmware metadata absent, ambiguous or candidate mismatch")


def _no_existing_outputs(workspace: Path) -> None:
    for name in (PLAN_NAME, *RUN_NAMES):
        candidate = workspace / name
        if candidate.exists() or candidate.is_symlink():
            raise ValueError("private capture output already exists: never overwrite")


def _capture_dir(path: Path) -> None:
    # Do not rely on umask: apply owner-only permissions to newly-created
    # directories before an emulator can produce screenshots or logs.
    path.mkdir(mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)
        info = path.stat()
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError("private capture output directory must be owner-only")


def capture_twice(private_emuhawk: Path, private_disc: Path, private_bk2: Path,
                  private_workspace: Path, *,
                  expected_digest_file: Path | None = None,
                  private_psx_bios_candidate: Path | None = None,
                  max_windows: int = 4,
                  emulator_timeout_seconds: int | None = None,
                  start: bool = False) -> dict:
    """Require explicit opt-in; run separate fresh emulator subprocesses.

    Output remains local. The capture chain and PNG files are independently
    checked after each process, and the second process is not attempted when
    the first is incomplete. The final auditor compares decoded image samples
    where it can, and never asserts original MAP02 authenticity.
    """
    workspace = _private_root(private_workspace)
    _no_existing_outputs(workspace)
    if type(max_windows) is not int or not 1 <= max_windows <= 10:
        raise ValueError("private capture window count must be 1..10")
    if type(start) is not bool:
        raise ValueError("private execution opt-in must be boolean")
    if emulator_timeout_seconds is not None and (
            type(emulator_timeout_seconds) is not int or
            not MIN_EMULATOR_TIMEOUT_SECONDS <= emulator_timeout_seconds
            <= MAX_EMULATOR_TIMEOUT_SECONDS):
        raise ValueError("emulator timeout seconds must be within 300..86400")
    emulator = Path(private_emuhawk)
    if (not emulator.is_absolute() or not emulator.is_file()
            or not SCRIPT.is_absolute() or not SCRIPT.is_file()):
        raise ValueError("absolute EmuHawk executable and capture Lua are required")

    # Pin the BK2 bytes before any preflight, capture plan, emulator
    # process or independent audit. Merely re-parsing a changed archive later
    # would not prove that both sessions used the same exact input movie.
    movie_identity = _private_movie_identity(private_bk2)
    disc_identity = _disc_source_snapshot(private_disc)
    # Dry-run must genuinely inspect the source movie/disc rather than
    # reporting a misleading success based on just an empty workspace.
    # No output file or emulator process is created without --launch-two.
    digest = (read_private_full_bin_sha256(expected_digest_file)
              if expected_digest_file is not None else None)
    profile = inspect_pair(
        private_disc, private_bk2,
        verify_full_bin_sha256=digest is not None,
        expected_bin_sha256=digest,
    )
    if not profile["media_preflight_ready_for_owner_replay"]:
        raise ValueError("owner-private original media preflight failed")
    _require_movie_unchanged(private_bk2, movie_identity)
    _require_disc_unchanged(private_disc, disc_identity)
    _require_digest_reference_unchanged(expected_digest_file, digest)
    _require_firmware_candidate_matches(private_bk2, private_psx_bios_candidate)
    if not start:
        candidate = plan_lines(private_bk2, limit=max_windows)
        if len(candidate) < 6 or (len(candidate) - 3) % 3:
            raise ValueError("private BK2 candidate capture plan is malformed")
        _require_movie_unchanged(private_bk2, movie_identity)
        _require_disc_unchanged(private_disc, disc_identity)
        _require_digest_reference_unchanged(expected_digest_file, digest)
        return {
            "schema": SCHEMA,
            "explicit_launch_requested": False,
            "media_preflight_passed": True,
            "owner_bk2_stable_during_preflight": True,
            "disc_source_stable_during_preflight": True,
            "private_capture_plan_rows_checked": len(candidate) - 3,
            "full_bin_sha256_checked": digest is not None,
            "full_bin_reference_stable_during_preflight": digest is not None,
            "candidate_bios_matches_bk2_psx_firmware_metadata":
                private_psx_bios_candidate is not None,
            "actual_emuhawk_loaded_bios_authenticated": False,
            "emulator_timeout_seconds": (
                emulator_timeout_seconds
                if emulator_timeout_seconds is not None
                else DEFAULT_EMULATOR_TIMEOUT_SECONDS
            ),
            "emulator_processes_started": 0,
            "capture_attempts_audited": 0,
            "owner_private_assets_uploaded": False,
            "original_map02_scene_authenticated": False,
        }

    plan = workspace / PLAN_NAME
    count = write_private_plan(
        private_bk2, plan, limit=max_windows,
    )
    if count < 3 or count % 3:
        raise ValueError("private capture plan contains invalid number of frames")
    _require_movie_unchanged(private_bk2, movie_identity)
    _require_disc_unchanged(private_disc, disc_identity)
    _require_digest_reference_unchanged(expected_digest_file, digest)

    for name in RUN_NAMES:
        _require_movie_unchanged(private_bk2, movie_identity)
        _require_disc_unchanged(private_disc, disc_identity)
        _require_digest_reference_unchanged(expected_digest_file, digest)
        _require_firmware_candidate_matches(private_bk2, private_psx_bios_candidate)
        output = workspace / name
        _capture_dir(output)
        argv = [
            sys.executable, "-m", "tools.map02_private_bizhawk_poweron_launch",
            str(private_emuhawk), str(private_disc), str(private_bk2),
            str(plan), str(output),
        ]
        if expected_digest_file is not None:
            argv += ["--private-full-bin-sha256-file", str(expected_digest_file)]
        if emulator_timeout_seconds is not None:
            argv += ["--emulator-timeout-seconds", str(emulator_timeout_seconds)]
        argv.append("--launch")
        # The child wrapper redirects EmuHawk stdout/stderr (which contain
        # absolute private paths) into files in the private capture folder.
        # Suppress even the wrapper status on this outer public-safe terminal.
        process = subprocess.run(
            argv, check=False, shell=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        _require_movie_unchanged(private_bk2, movie_identity)
        _require_disc_unchanged(private_disc, disc_identity)
        _require_digest_reference_unchanged(expected_digest_file, digest)
        # First hash verification occurs inside the child launcher before
        # EmuHawk. Re-check all bytes AFTER EmuHawk returns, so mutation
        # outside the small PVD/MAP02 sector sample cannot survive.
        _require_full_bin_unchanged(private_disc, digest)
        _require_digest_reference_unchanged(expected_digest_file, digest)
        _require_firmware_candidate_matches(private_bk2, private_psx_bios_candidate)
        if process.returncode != 0:
            raise ValueError("one private emulator capture process failed")
        # Reject an emulator that returned zero without the exact expected
        # Lua markers and structurally intact PNGs before starting the next.
        verify(private_bk2, plan, output / "vh_private_capture.log", output)
        _require_movie_unchanged(private_bk2, movie_identity)
        _require_disc_unchanged(private_disc, disc_identity)
        _require_digest_reference_unchanged(expected_digest_file, digest)

    paired = audit_pair(
        private_bk2, plan, workspace / RUN_NAMES[0], workspace / RUN_NAMES[1],
    )
    _require_movie_unchanged(private_bk2, movie_identity)
    _require_disc_unchanged(private_disc, disc_identity)
    _require_digest_reference_unchanged(expected_digest_file, digest)
    # Third parent-side full read: the final PNG/pair audit may take time.
    _require_full_bin_unchanged(private_disc, digest)
    _require_digest_reference_unchanged(expected_digest_file, digest)
    _require_firmware_candidate_matches(private_bk2, private_psx_bios_candidate)
    return {
        "schema": SCHEMA,
        "explicit_launch_requested": True,
        "emulator_processes_started": 2,
        "capture_attempts_audited": 2,
        "same_reported_bizhawk_runtime_profile":
            paired["same_reported_bizhawk_runtime_profile"],
        "same_reported_psx_lag_timeline":
            paired["same_reported_psx_lag_timeline"],
        "same_reported_psx_core_fallback_configuration":
            paired["same_reported_psx_core_fallback_configuration"],
        "both_runs_reported_psx_core_fallback_disabled":
            paired["both_runs_reported_psx_core_fallback_disabled"],
        "same_bk2_bytes_across_capture_attempts": True,
        "same_cue_and_sampled_bin_sectors_across_attempts": True,
        "full_disc_content_equality_authenticated": False,
        "full_bin_reference_stable_across_attempts": digest is not None,
        "full_bin_postprocess_checks_performed": 2 if digest is not None else 0,
        "full_bin_final_postaudit_check_performed": digest is not None,
        "on_disk_full_bin_matched_private_reference_at_checkpoints":
            digest is not None,
        "emulator_mounted_disc_identity_authenticated": False,
        "candidate_bios_matched_bk2_metadata_at_checkpoints":
            private_psx_bios_candidate is not None,
        "actual_emuhawk_loaded_bios_authenticated": False,
        "emulator_timeout_seconds": (
            emulator_timeout_seconds
            if emulator_timeout_seconds is not None
            else DEFAULT_EMULATOR_TIMEOUT_SECONDS
        ),
        "screenshot_pairs_checked": paired["screenshot_pairs_checked"],
        "matching_pixel_pairs": paired["decoded_pixel_equal_pairs"],
        "different_pixel_pairs": paired["decoded_pixel_different_pairs"],
        "unsupported_pixel_pairs": paired["decoded_pixel_unsupported_pairs"],
        "all_supported_png_pixel_content_equal":
            paired["all_supported_png_pixel_content_equal"],
        "owner_private_assets_uploaded": False,
        "independent_cold_boots_authenticated": False,
        "original_map02_scene_authenticated": False,
        "rendered_pixel_parity_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("absolute_emuhawk_executable", type=Path)
    parser.add_argument("owner_private_ps1_cue", type=Path)
    parser.add_argument("owner_private_bk2", type=Path)
    parser.add_argument("owner_existing_empty_private_workspace", type=Path)
    parser.add_argument("--private-full-bin-sha256-file", type=Path)
    parser.add_argument("--private-psx-bios-candidate", type=Path)
    parser.add_argument("--max-windows", type=int, default=4)
    parser.add_argument(
        "--emulator-timeout-seconds", type=int,
        help="Optional EmuHawk watchdog, between 300 and 86400 seconds",
    )
    parser.add_argument("--launch-two", action="store_true",
                        help="Actually run TWO sequential local EmuHawk processes")
    args = parser.parse_args()
    try:
        report = capture_twice(
            args.absolute_emuhawk_executable,
            args.owner_private_ps1_cue, args.owner_private_bk2,
            args.owner_existing_empty_private_workspace,
            expected_digest_file=args.private_full_bin_sha256_file,
            private_psx_bios_candidate=args.private_psx_bios_candidate,
            max_windows=args.max_windows,
            emulator_timeout_seconds=args.emulator_timeout_seconds,
            start=args.launch_two,
        )
    except (OSError, ValueError, TypeError, RuntimeError, KeyError):
        parser.error("private two-replay execution or capture audit failed")
    print(json.dumps(report, sort_keys=True, indent=2))
    if not args.launch_two:
        return 0
    return 0 if report["all_supported_png_pixel_content_equal"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
