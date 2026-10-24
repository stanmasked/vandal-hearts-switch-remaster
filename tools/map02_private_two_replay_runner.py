#!/usr/bin/env python3
"""Run two sequential owner-LOCAL BizHawk capture attempts and audit them.

No original disc, BIOS, BK2, screenshots, private paths or hashes may be sent
to public CI. A successful run proves only the local file/log chain; neither
actual independent cold boots nor MAP02 identity is authenticated here.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Callable

from tools.map02_private_bk2_capture_plan import plan_lines, write_private_plan
from tools.map02_private_bizhawk_poweron_launch import (
    SCRIPT, DEFAULT_EMULATOR_TIMEOUT_SECONDS,
    MIN_EMULATOR_TIMEOUT_SECONDS, MAX_EMULATOR_TIMEOUT_SECONDS,
    AUTO_WITNESS_NAME, require_matching_core_plugin,
    require_runtime_module_pins, require_linux_owner_runtime_pin,
)
from tools.map02_private_disc_movie_preflight import (
    _assert_stable, _identity, _open_stable, _parse_cue, _read_at,
    _resolve_private_file, EXPECTED_BIN_BYTES, MAP02_BYTES, MAP02_LBA,
    MAX_CUE_BYTES, PVD_LBA, SECTOR_BYTES, USER_DATA_BYTES,
    inspect_pair, read_private_full_bin_sha256, _full_image_sha256, _read_cue,
)
from tools.map02_private_psx_firmware_probe import compare_firmware
from tools.map02_private_process_witness_binding import (
    bind_owner_private_replays, NAME as PROCESS_RECEIPT_NAME,
)
from tools.map02_windows_private_output_acl import require_windows_private_output
from tools.map02_private_witness_plugin_digest import require_pinned_core_witness_dll
from tools.map02_private_two_capture_audit import _private_root, audit_pair
from tools.verify_map02_private_neutral_capture_chain import verify
from tools.map02_linux_octoshock.owner_persistent_host import (
    MINIMUM_CAPTURE_BYTES, capture_guard_directories,
    verify_and_snapshot_persistent_host, require_unchanged_persistent_host,
)


SCHEMA = "vh.map02.private-two-sequential-replays.v2"
PLAN_NAME = "vh-map02-review-plan.txt"
RUN_NAMES = ("vh-map02-cold-01", "vh-map02-cold-02")
CAPTURE_LOCK_NAME = ".vh-map02-capture.lock"
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


@contextmanager
def _exclusive_capture_lock(workspace: Path):
    """Serialize real capture coordinators sharing one owner-private workspace.

    A stale lock is intentionally not auto-cleared after a crash: inspect it
    manually rather than risk overlapping two cold-boot capture sessions.
    This is a cooperative concurrency guard, not a lock against a hostile
    process running as the same user.
    """
    lock_path = workspace / CAPTURE_LOCK_NAME
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(lock_path, flags, 0o600)
    except FileExistsError:
        raise ValueError(
            "private capture workspace is already locked; inspect stale lock manually"
        ) from None
    except OSError:
        raise ValueError("private capture lock could not be created safely") from None

    lock_identity = None

    def check_lock() -> None:
        if lock_identity is None:
            raise ValueError("private capture lock identity was not established")
        try:
            opened = os.fstat(fd)
            current = lock_path.lstat()
        except OSError:
            raise ValueError("private capture lock disappeared during execution") from None
        if (not stat.S_ISREG(opened.st_mode)
                or not stat.S_ISREG(current.st_mode)
                or opened.st_nlink != 1 or current.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != lock_identity
                or (current.st_dev, current.st_ino) != lock_identity):
            raise ValueError("private capture lock changed; refusing to continue")
        if os.name != "nt" and (
                opened.st_uid != os.geteuid()
                or current.st_uid != os.geteuid()
                or stat.S_IMODE(opened.st_mode) != 0o600
                or stat.S_IMODE(current.st_mode) != 0o600):
            raise ValueError("private capture lock permissions changed")

    try:
        opened = os.fstat(fd)
        lock_identity = (opened.st_dev, opened.st_ino)
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        check_lock()
        payload = ("VH_MAP02_CAPTURE_LOCK_V1 pid=%d\\n" % os.getpid()).encode("ascii")
        if os.write(fd, payload) != len(payload):
            raise OSError("short private capture lock write")
        os.fsync(fd)
        check_lock()
        yield check_lock
    finally:
        try:
            if lock_identity is not None:
                check_lock()
                lock_path.unlink()
        finally:
            os.close(fd)


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
    require_windows_private_output(path)


def _capture_twice_impl(private_emuhawk: Path, private_disc: Path, private_bk2: Path,
                        private_workspace: Path, *,
                        expected_digest_file: Path | None = None,
                        private_psx_bios_candidate: Path | None = None,
                        record_windows_process_identity: bool = False,
                        auto_core_witness_plugin: Path | None = None,
                        core_witness_sha256: str | None = None,
                        max_windows: int = 4,
                        emulator_timeout_seconds: int | None = None,
                        run_count: int = 2,
                        start: bool = False,
                        mono_executable: Path | None = None,
                        trusted_runtime_manifest_pin_file: Path | None = None,
                        _capture_lock_guard: Callable[[], None] | None = None) -> dict:
    """Require explicit opt-in; run separate fresh emulator subprocesses.

    Output remains local. The capture chain and PNG files are independently
    checked after each process, and the second process is not attempted when
    the first is incomplete. The final auditor compares decoded image samples
    where it can, and never asserts original MAP02 authenticity.
    """
    workspace = _private_root(private_workspace)
    def recheck_capture_lock() -> None:
        if _capture_lock_guard is not None:
            _capture_lock_guard()
    recheck_capture_lock()
    _no_existing_outputs(workspace)
    recheck_capture_lock()
    if type(max_windows) is not int or not 1 <= max_windows <= 10:
        raise ValueError("private capture window count must be 1..10")
    if type(run_count) is not int or run_count not in (1, 2):
        raise ValueError("owner capture run count must be exactly one or two")
    if type(start) is not bool:
        raise ValueError("private execution opt-in must be boolean")
    if type(record_windows_process_identity) is not bool:
        raise ValueError("process binding request must be boolean")
    if auto_core_witness_plugin is not None and not record_windows_process_identity:
        raise ValueError("owner private automatic core witness requires process identity recording")
    if core_witness_sha256 is not None and auto_core_witness_plugin is None:
        raise ValueError("private plugin hash requires the automatic core witness DLL")
    linux_runtime = sys.platform.startswith("linux") and mono_executable is not None
    if mono_executable is not None:
        mono = Path(mono_executable)
        if not sys.platform.startswith("linux") or not mono.is_absolute():
            raise ValueError("Linux Mono executable requires an absolute path")
        mono = mono.resolve(strict=True)
        if not mono.is_file() or mono.is_symlink() or not os.access(mono, os.X_OK):
            raise ValueError("resolved Linux Mono executable must be a regular executable file")
    if auto_core_witness_plugin is not None and start and os.name != "nt" and not linux_runtime:
        raise ValueError("owner automatic core witness requires Windows or Linux with explicit Mono")
    if record_windows_process_identity and start and os.name != "nt" and not linux_runtime:
        raise ValueError("private process identity requires Windows or Linux with explicit Mono")
    if emulator_timeout_seconds is not None and (
            type(emulator_timeout_seconds) is not int or
            not MIN_EMULATOR_TIMEOUT_SECONDS <= emulator_timeout_seconds
            <= MAX_EMULATOR_TIMEOUT_SECONDS):
        raise ValueError("emulator timeout seconds must be within 300..86400")
    emulator = Path(private_emuhawk)
    if (not emulator.is_absolute() or not emulator.is_file()
            or not SCRIPT.is_absolute() or not SCRIPT.is_file()):
        raise ValueError("absolute EmuHawk executable and capture Lua are required")
    if auto_core_witness_plugin is not None:
        require_matching_core_plugin(emulator, auto_core_witness_plugin)
    if core_witness_sha256 is not None:
        require_pinned_core_witness_dll(auto_core_witness_plugin, core_witness_sha256)
        # Fail before creating a plan or launching EmuHawk unless the same
        # independently trusted build supplies both runtime module pins.
        require_runtime_module_pins(required=auto_core_witness_plugin is not None)

    # Fail before reading the owner's disc or movie.
    require_linux_owner_runtime_pin(
        private_emuhawk, mono_executable, trusted_runtime_manifest_pin_file
    )
    recheck_capture_lock()
    host_guarded_paths = None
    host_identity = None
    if linux_runtime and start:
        # A real Linux capture must run on persistent owner-only local storage,
        # never GitHub CI, tmpfs/overlay, a cloud mount, or the repository.
        host_guarded_paths = capture_guard_directories(
            Path(private_emuhawk).parent, workspace, private_disc, private_bk2,
            trusted_runtime_manifest_pin_file,
            private_full_bin_sha256_file=expected_digest_file,
            private_psx_bios_candidate=private_psx_bios_candidate,
            auto_core_witness_plugin=auto_core_witness_plugin,
        )
        host_identity = verify_and_snapshot_persistent_host(
            host_guarded_paths, minimum_free_bytes=MINIMUM_CAPTURE_BYTES,
        )

    def recheck_capture_host() -> None:
        if host_guarded_paths is not None:
            require_unchanged_persistent_host(
                host_guarded_paths, host_identity,
                minimum_free_bytes=MINIMUM_CAPTURE_BYTES,
            )

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
    recheck_capture_host()
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
            "runtime_witness_reports_loaded_psx_u_bios_matches_bk2_header": False,
            "actual_emuhawk_loaded_bios_authenticated": False,
            "emulator_timeout_seconds": (
                emulator_timeout_seconds
                if emulator_timeout_seconds is not None
                else DEFAULT_EMULATOR_TIMEOUT_SECONDS
            ),
            "emulator_processes_started": 0,
            "planned_emulator_processes": run_count,
            "private_windows_process_start_receipts_requested": False,
            "process_to_manual_core_witness_bound": False,
            "automatic_core_witness_requested": auto_core_witness_plugin is not None,
            "installed_core_witness_sha256_pinned": core_witness_sha256 is not None,
            "automatic_core_witness_process_bound": False,
            "capture_attempts_audited": 0,
            "owner_private_assets_uploaded": False,
            "original_map02_scene_authenticated": False,
        }

    recheck_capture_lock()
    plan = workspace / PLAN_NAME
    count = write_private_plan(
        private_bk2, plan, limit=max_windows,
    )
    recheck_capture_lock()
    if count < 3 or count % 3:
        raise ValueError("private capture plan contains invalid number of frames")
    _require_movie_unchanged(private_bk2, movie_identity)
    _require_disc_unchanged(private_disc, disc_identity)
    _require_digest_reference_unchanged(expected_digest_file, digest)

    for name in RUN_NAMES[:run_count]:
        recheck_capture_lock()
        recheck_capture_host()
        require_linux_owner_runtime_pin(
            private_emuhawk, mono_executable, trusted_runtime_manifest_pin_file
        )
        if core_witness_sha256 is not None:
            require_pinned_core_witness_dll(auto_core_witness_plugin, core_witness_sha256)
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
        if record_windows_process_identity:
            argv.append("--record-process-identity")
        if auto_core_witness_plugin is not None:
            argv += ["--auto-core-witness-plugin", str(auto_core_witness_plugin)]
        if core_witness_sha256 is not None:
            argv += ["--private-core-witness-sha256", core_witness_sha256]
        if mono_executable is not None:
            argv += ["--mono-executable", str(Path(mono_executable).resolve(strict=True))]
            argv += ["--trusted-runtime-manifest-pin-file",
                     str(trusted_runtime_manifest_pin_file)]
        argv.append("--launch")
        # The child wrapper redirects EmuHawk stdout/stderr (which contain
        # absolute private paths) into files in the private capture folder.
        # Suppress even the wrapper status on this outer public-safe terminal.
        process = subprocess.run(
            argv, check=False, shell=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        recheck_capture_lock()
        recheck_capture_host()
        if core_witness_sha256 is not None:
            require_pinned_core_witness_dll(auto_core_witness_plugin, core_witness_sha256)
        require_linux_owner_runtime_pin(
            private_emuhawk, mono_executable, trusted_runtime_manifest_pin_file
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
        recheck_capture_lock()
        chain = verify(private_bk2, plan, output / "vh_private_capture.log", output)
        recheck_capture_lock()
        if auto_core_witness_plugin is not None:
            if chain.get("owner_log_reports_auto_core_witness_before_first_png") is not True:
                raise ValueError("private auto core witness did not precede first PNG")
            # Fail before creating a second emulator if this capture is not
            # independently tied to its OWN launched process.
            from tools.map02_private_process_witness_binding import (
                read_started_process,
            )
            from tools.map02_private_core_witness_audit import read_witness_record
            started = read_started_process(output / PROCESS_RECEIPT_NAME)
            observed = read_witness_record(output / AUTO_WITNESS_NAME)
            if started != observed[:2]:
                raise ValueError("owner automatic core witness differs from captured process")
            if observed[6] is not True:
                raise ValueError("owner automatic core witness does not confirm PSX/U firmware match")
            if observed[7] is not True:
                raise ValueError(
                    "owner automatic core witness does not confirm mounted-disc state and source CUE basename")
            if (core_witness_sha256 is not None
                    and observed[3] != core_witness_sha256.lower()):
                raise ValueError(
                    "runtime witness tool hash differs from pinned DLL digest")
            from tools.verify_map02_private_neutral_capture_chain import parse_plan
            _, planned_rows = parse_plan(plan)
            if not planned_rows or observed[2] > planned_rows[0][2] + 1:
                raise ValueError("owner auto core witness frame after first screenshot")
        _require_movie_unchanged(private_bk2, movie_identity)
        _require_disc_unchanged(private_disc, disc_identity)
        _require_digest_reference_unchanged(expected_digest_file, digest)
        if core_witness_sha256 is not None:
            require_pinned_core_witness_dll(auto_core_witness_plugin, core_witness_sha256)
        recheck_capture_host()

    if run_count == 1:
        recheck_capture_lock()
        require_linux_owner_runtime_pin(
            private_emuhawk, mono_executable, trusted_runtime_manifest_pin_file
        )
        # This is owner-private first-run evidence only, never evidence of
        # a second emulator process, repeatability, or scene identity.
        _require_full_bin_unchanged(private_disc, digest)
        _require_digest_reference_unchanged(expected_digest_file, digest)
        _require_firmware_candidate_matches(private_bk2, private_psx_bios_candidate)
        recheck_capture_host()
        return {
            "schema": SCHEMA,
            "explicit_launch_requested": True,
            "planned_emulator_processes": 1,
            "emulator_processes_started": 1,
            "capture_attempts_audited": 1,
            "first_private_capture_log_and_png_chain_passed": True,
            "first_private_capture_screenshot_count": chain["screenshot_count"],
            "automatic_core_witness_requested": auto_core_witness_plugin is not None,
            "installed_core_witness_sha256_pinned": core_witness_sha256 is not None,
            "runtime_tool_file_hash_self_reported": auto_core_witness_plugin is not None,
            "runtime_tool_file_hash_reported_by_witness_matches_pin":
                auto_core_witness_plugin is not None and core_witness_sha256 is not None,
            "first_auto_core_witness_bound_to_launched_process":
                auto_core_witness_plugin is not None,
            "first_runtime_witness_reports_loaded_psx_u_bios_matches_bk2_header":
                auto_core_witness_plugin is not None and observed[6] is True,
            "first_runtime_witness_reports_single_mounted_disc_tray_closed_source_cue_name_match":
                auto_core_witness_plugin is not None and observed[7] is True,
            "first_auto_core_frame_not_later_than_first_png":
                auto_core_witness_plugin is not None,
            "same_bk2_bytes_across_capture_attempts": False,
            "same_cue_and_sampled_bin_sectors_across_attempts": False,
            "full_bin_reference_stable_during_capture": digest is not None,
            "full_bin_postprocess_checks_performed": 2 if digest is not None else 0,
            "on_disk_full_bin_matched_private_reference_at_checkpoints":
                digest is not None,
            "actual_emuhawk_loaded_bios_authenticated": False,
            "emulator_mounted_disc_identity_authenticated": False,
            "original_bk2_controller_delivery_authenticated": False,
            "independent_cold_boots_authenticated": False,
            "two_run_pixel_repeatability_authenticated": False,
            "original_map02_scene_authenticated": False,
            "owner_private_assets_uploaded": False,
        }

    recheck_capture_lock()
    recheck_capture_host()
    paired = audit_pair(
        private_bk2, plan, workspace / RUN_NAMES[0], workspace / RUN_NAMES[1],
    )
    recheck_capture_lock()
    recheck_capture_host()
    _require_movie_unchanged(private_bk2, movie_identity)
    _require_disc_unchanged(private_disc, disc_identity)
    _require_digest_reference_unchanged(expected_digest_file, digest)
    if auto_core_witness_plugin is not None:
        bound = bind_owner_private_replays(
            workspace / RUN_NAMES[0] / PROCESS_RECEIPT_NAME,
            workspace / RUN_NAMES[0] / AUTO_WITNESS_NAME,
            workspace / RUN_NAMES[1] / PROCESS_RECEIPT_NAME,
            workspace / RUN_NAMES[1] / AUTO_WITNESS_NAME,
        )
        if bound.get("runtime_core_witnesses_bound_to_launched_process_identity") is not True:
            raise ValueError("automatic core witness binding rejected")
        if bound.get("both_witnesses_report_psx_u_firmware_matches_bk2_header") is not True:
            raise ValueError("paired automatic witnesses do not confirm PSX/U firmware match")
        if bound.get(
                "both_witnesses_report_single_mounted_disc_tray_closed_source_cue_name_match") is not True:
            raise ValueError("paired automatic witnesses do not confirm mounted-disc state/source CUE basename")
    # Third parent-side full read: the final PNG/pair audit may take time.
    require_linux_owner_runtime_pin(
        private_emuhawk, mono_executable, trusted_runtime_manifest_pin_file
    )
    if core_witness_sha256 is not None:
        require_pinned_core_witness_dll(auto_core_witness_plugin, core_witness_sha256)
    _require_full_bin_unchanged(private_disc, digest)
    _require_digest_reference_unchanged(expected_digest_file, digest)
    _require_firmware_candidate_matches(private_bk2, private_psx_bios_candidate)
    return {
        "schema": SCHEMA,
        "explicit_launch_requested": True,
        "emulator_processes_started": 2,
        "planned_emulator_processes": 2,
        "private_windows_process_start_receipts_requested":
            record_windows_process_identity,
        "process_to_manual_core_witness_bound": False,
        "automatic_core_witness_requested": auto_core_witness_plugin is not None,
        "installed_core_witness_sha256_pinned": core_witness_sha256 is not None,
        "runtime_tool_file_hash_self_reported": auto_core_witness_plugin is not None,
        "runtime_tool_file_hash_reported_by_witness_matches_pin":
            auto_core_witness_plugin is not None and core_witness_sha256 is not None,
        "automatic_core_witness_process_bound": auto_core_witness_plugin is not None,
        "both_runtime_witnesses_report_loaded_psx_u_bios_matches_bk2_header":
            auto_core_witness_plugin is not None
            and bound.get("both_witnesses_report_psx_u_firmware_matches_bk2_header") is True,
        "both_runtime_witnesses_report_single_mounted_disc_tray_closed_source_cue_name_match":
            auto_core_witness_plugin is not None
            and bound.get("both_witnesses_report_single_mounted_disc_tray_closed_source_cue_name_match") is True,
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


def capture_twice(private_emuhawk: Path, private_disc: Path, private_bk2: Path,
                  private_workspace: Path, *,
                  expected_digest_file: Path | None = None,
                  private_psx_bios_candidate: Path | None = None,
                  record_windows_process_identity: bool = False,
                  auto_core_witness_plugin: Path | None = None,
                  core_witness_sha256: str | None = None,
                  max_windows: int = 4,
                  emulator_timeout_seconds: int | None = None,
                  run_count: int = 2,
                  start: bool = False,
                  mono_executable: Path | None = None,
                  trusted_runtime_manifest_pin_file: Path | None = None) -> dict:
    """Run a capture with a workspace-exclusive lock when execution is requested."""
    arguments = dict(
        expected_digest_file=expected_digest_file,
        private_psx_bios_candidate=private_psx_bios_candidate,
        record_windows_process_identity=record_windows_process_identity,
        auto_core_witness_plugin=auto_core_witness_plugin,
        core_witness_sha256=core_witness_sha256,
        max_windows=max_windows,
        emulator_timeout_seconds=emulator_timeout_seconds,
        run_count=run_count,
        start=start,
        mono_executable=mono_executable,
        trusted_runtime_manifest_pin_file=trusted_runtime_manifest_pin_file,
    )
    if not start:
        return _capture_twice_impl(
            private_emuhawk, private_disc, private_bk2, private_workspace,
            **arguments,
        )
    workspace = _private_root(private_workspace)
    with _exclusive_capture_lock(workspace) as check_lock:
        check_lock()
        return _capture_twice_impl(
            private_emuhawk, private_disc, private_bk2, private_workspace,
            _capture_lock_guard=check_lock, **arguments,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("absolute_emuhawk_executable", type=Path)
    parser.add_argument("owner_private_ps1_cue", type=Path)
    parser.add_argument("owner_private_bk2", type=Path)
    parser.add_argument("owner_existing_empty_private_workspace", type=Path)
    parser.add_argument("--private-full-bin-sha256-file", type=Path)
    parser.add_argument("--private-psx-bios-candidate", type=Path)
    parser.add_argument("--auto-core-witness-plugin", type=Path,
                        help="Owner opt-in: matching EmuHawk ExternalTools DLL auto-saves private PSX-only core evidence")
    parser.add_argument("--private-core-witness-sha256", type=str,
                        help="Owner opt-in: independently pinned SHA256 for the installed experimental DLL")
    parser.add_argument(
        "--record-process-identity", "--record-windows-process-identity",
        dest="record_windows_process_identity", action="store_true",
        help="Opt-in owner-private Windows/Linux process-start receipts for comparison to core witness files",
    )
    parser.add_argument("--mono-executable", type=Path,
                        help="Linux only: absolute Mono executable for the official EmuHawk.exe")
    parser.add_argument("--trusted-runtime-manifest-pin-file", type=Path,
                        help="Required with Linux Mono: external owner-private runtime SHA-256")
    parser.add_argument("--max-windows", type=int, default=4)
    parser.add_argument(
        "--emulator-timeout-seconds", type=int,
        help="Optional EmuHawk watchdog, between 300 and 86400 seconds",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--launch-one", action="store_true",
                       help="Run and audit only ONE local EmuHawk; no replay comparison")
    modes.add_argument("--launch-two", action="store_true",
                       help="Actually run TWO sequential local EmuHawk processes")
    args = parser.parse_args()
    try:
        report = capture_twice(
            args.absolute_emuhawk_executable,
            args.owner_private_ps1_cue, args.owner_private_bk2,
            args.owner_existing_empty_private_workspace,
            expected_digest_file=args.private_full_bin_sha256_file,
            private_psx_bios_candidate=args.private_psx_bios_candidate,
            record_windows_process_identity=args.record_windows_process_identity,
            auto_core_witness_plugin=args.auto_core_witness_plugin,
            core_witness_sha256=args.private_core_witness_sha256,
            max_windows=args.max_windows,
            emulator_timeout_seconds=args.emulator_timeout_seconds,
            run_count=1 if args.launch_one else 2,
            start=args.launch_one or args.launch_two,
            mono_executable=args.mono_executable,
            trusted_runtime_manifest_pin_file=args.trusted_runtime_manifest_pin_file,
        )
    except (OSError, ValueError, TypeError, RuntimeError, KeyError):
        parser.error("private two-replay execution or capture audit failed")
    print(json.dumps(report, sort_keys=True, indent=2))
    if not args.launch_two:
        return 0
    return 0 if report["all_supported_png_pixel_content_equal"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
