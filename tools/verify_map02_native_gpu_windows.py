#!/usr/bin/env python3
"""Verify bounded two-window native GPU capture from ONE original-PC run.

Each 64-event window is separately native-VRAM checked. The global
sequence is reconstructed only from explicit window order, and every
adjacent operation's 1-MiB VRAM endpoint must equal the next beginning.
This verifies a self-reported recorder window, NOT a real MAP02 frame
or independent PlayStation hardware capture.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

from tools.publish_map02_blendg1_witness import _private_directory
from tools.verify_map02_frame_bundle import fields, number, parse_json
from tools.verify_map02_native_gpu_capture import (
    LOG, MAX_RECORDS, STATUS, private_file, verify_capture,
)
from tools.verify_map02_vram_timeline import VRAM_BYTES

INDEX = "gpu-native-window-index.json"
SCHEMA = "vh.map02.native-windows.v1"
MAX_WINDOWS = 2


def private_window_file(directory, name, *, expected=None, max_bytes=None):
    """Read the same open inode whose private metadata is verified.

    A pathname lstat followed by read_bytes permits an inode exchange
    between checks. Hold a private directory FD, open the evidence with
    NOFOLLOW and verify metadata before/after bounded reads, including
    that the directory entry still resolves to the opened inode.
    These checks do not authenticate the original GPU process.
    """
    if (type(name) is not str or not name or name in (".", "..") or
            "/" in name or "\x00" in name):
        raise ValueError("invalid native GPU capture filename")
    directory = Path(directory)
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    dirfd = os.open(directory, flags | os.O_DIRECTORY)
    try:
        d = os.fstat(dirfd)
        if (not stat.S_ISDIR(d.st_mode) or
                stat.S_IMODE(d.st_mode) != 0o700 or
                d.st_uid != os.geteuid()):
            raise ValueError("native GPU window directory is not owner-private")
        try:
            fd = os.open(name, flags, dir_fd=dirfd)
        except OSError as exc:
            # A symlink with O_NOFOLLOW raises ELOOP rather than the
            # ValueError expected by the public strict-verifier contract.
            raise ValueError("native GPU capture file missing or symlinked") from exc
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or
                    stat.S_IMODE(before.st_mode) != 0o600 or
                    before.st_nlink != 1 or
                    before.st_uid != os.geteuid()):
                raise ValueError(
                    "native GPU capture files require owner-only 0600 mode and one link")
            size = before.st_size
            if expected is not None and size != expected:
                raise ValueError("native GPU capture file has wrong size")
            if max_bytes is not None and not 0 < size <= max_bytes:
                raise ValueError("native GPU capture file empty or above limit")
            if expected is None and max_bytes is None:
                raise ValueError("native GPU read requires an explicit byte bound")
            chunks, total = [], 0
            while total <= size:
                chunk = os.read(fd, min(65536, size + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            after = os.fstat(fd)
            entry = os.stat(name, dir_fd=dirfd, follow_symlinks=False)
            identity = lambda st: (
                st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_nlink,
                st.st_size, st.st_mtime_ns, st.st_ctime_ns)
            if (total != size or identity(before) != identity(after) or
                    identity(after) != identity(entry)):
                raise ValueError("native GPU capture file changed during secure read")
            # Keep the directory pathname pinned as well as the file's
            # directory-relative name. Without this, an attacker could
            # rename the entire capture directory and replace it with
            # another owner-private directory while the held dirfd still
            # points to the original inode.
            try:
                named_directory = os.stat(directory, follow_symlinks=False)
            except OSError as exc:
                raise ValueError(
                    "native GPU capture directory moved during secure read") from exc
            if (identity(d) != identity(os.fstat(dirfd)) or
                    identity(d) != identity(named_directory)):
                raise ValueError("native GPU capture directory changed during secure read")
            return b"".join(chunks)
        finally:
            os.close(fd)
    finally:
        os.close(dirfd)


def verify_native_windows(directory, *, target_frame):
    root = _private_directory(directory)
    number(target_frame, "GPU DrawOTag frame", 1, 2**32 - 1)
    if (root / STATUS).exists() or (root / STATUS).is_symlink():
        raise ValueError("legacy native GPU receipt cannot be mixed with windowed capture")
    raw = private_window_file(root, INDEX, max_bytes=4096)
    status = parse_json(raw, INDEX)
    fields(status, (
        "schema", "gpu_draw_frame", "window_capacity_events",
        "configured_windows", "windows_written", "observed_hooks",
        "before_hooks", "after_hooks", "draw_before_hooks",
        "transfer_before_hooks", "indexed_hooks", "written_hooks",
        "limit_reached", "walk_finished", "hooks_balanced",
        "write_failed", "recorded_window_closed_without_detected_loss",
    ), INDEX, optional=("capture_session",))
    session = status.get("capture_session")
    if session is not None:
        if (type(session) is not str or len(session) != 32 or
                any(c not in "0123456789abcdef" for c in session)):
            raise ValueError("invalid in-process GPU capture session token")
    if status["schema"] != SCHEMA or number(
            status["gpu_draw_frame"], "GPU frame", 1, 2**32-1) != target_frame:
        raise ValueError("invalid native window schema/frame")
    if (number(status["window_capacity_events"], "capacity", 0, 128) !=
            MAX_RECORDS or number(status["configured_windows"],
            "configured window count", 1, MAX_WINDOWS) != MAX_WINDOWS):
        raise ValueError("native GPU window configuration mismatch")

    written = number(status["written_hooks"], "written hooks", 2, 128)
    indexed = number(status["indexed_hooks"], "indexed hooks", 0, 128)
    observed = number(status["observed_hooks"], "observed hooks", 0, 2**32-1)
    before = number(status["before_hooks"], "before hooks", 0, 2**32-1)
    after = number(status["after_hooks"], "after hooks", 0, 2**32-1)
    draws = number(status["draw_before_hooks"], "draw before hooks",
                   0, 2**32-1)
    transfers = number(status["transfer_before_hooks"],
                       "transfer before hooks", 0, 2**32-1)
    window_count = number(status["windows_written"], "written windows",
                          1, MAX_WINDOWS)
    for name in ("limit_reached", "walk_finished", "hooks_balanced",
                 "write_failed", "recorded_window_closed_without_detected_loss"):
        if type(status[name]) is not bool:
            raise ValueError("GPU window index contains a nonboolean status")
    if (window_count != (written + MAX_RECORDS - 1)//MAX_RECORDS or
            written % 2 or written >= MAX_WINDOWS * MAX_RECORDS or
            indexed != written or observed != written or
            before != after or observed != before + after or
            draws + transfers != before or
            status["limit_reached"] or not status["walk_finished"] or
            not status["hooks_balanced"] or status["write_failed"] or
            not status["recorded_window_closed_without_detected_loss"]):
        raise ValueError("GPU window capture incomplete, truncated or inconsistent")

    expected_root_entries = {INDEX} | {
        f"window-{i:03d}" for i in range(window_count)}
    if {item.name for item in root.iterdir()} != expected_root_entries:
        raise ValueError("unlisted native GPU window or unrelated capture files")
    total_draws = total_transfers = seen = 0
    last_vram = None
    # Source-pinned DrawOTag runs continuously through a window rollover.
    # A dropped DR_MODE transition can leave VRAM identical while forging
    # the texture window / draw mode at the next native event.
    last_operation = None
    last_draw_post_state = None
    last_draw_post_env = None
    logs_hash = hashlib.sha256()
    file_tree_hash = hashlib.sha256()
    inventory_digests = []
    for idx in range(window_count):
        window = _private_directory(root / f"window-{idx:03d}")
        if (window / STATUS).exists() or (window / STATUS).is_symlink():
            raise ValueError("legacy per-window receipt incorrectly asserts complete frame")
        log = private_window_file(window, LOG, max_bytes=128 * 1024)
        if (not log.endswith(b"\n") or b"\r" in log or
                any(not entry for entry in log.split(b"\n")[:-1])):
            raise ValueError("noncanonical native window JSONL")
        events = [parse_json(item, "native GPU window event") for item
                  in log.split(b"\n")[:-1]]
        count = min(MAX_RECORDS, written - idx * MAX_RECORDS)
        if len(events) != count or count % 2:
            raise ValueError("missing, duplicated or reordered native GPU window events")
        if any(type(e.get("snapshot")) is not str or
               type(e.get("upload")) is not str for e in events):
            raise ValueError("native GPU window event has nonstring file metadata")
        expected_files = {LOG} | {e.get("snapshot") for e in events}
        expected_files |= {e.get("upload") for e in events if e.get("upload")}
        if {item.name for item in window.iterdir()} != expected_files:
            raise ValueError("unlisted or missing files in native GPU capture window")
        # Hash ALL published capture bytes, not only JSONL: unreferenced or
        # replaced snapshots must never inherit the same source binding.
        # Freeze each bounded file's bytes for this verifier pass. The
        # cryptographic inventory, native transfer replay, and event/window
        # bridges must not observe different versions of the same pathname.
        inventory = {}
        for name in sorted(expected_files):
            data = private_window_file(window, name, max_bytes=VRAM_BYTES + 128 * 1024)
            inventory[name] = data
            file_tree_hash.update(f"window-{idx:03d}/{name}\0".encode("ascii"))
            file_tree_hash.update(hashlib.sha256(data).digest())
        if inventory[LOG] != log:
            raise ValueError("native GPU window journal changed before inventory snapshot")
        inventory_digests.append((
            window, tuple((name, hashlib.sha256(raw).digest())
                          for name, raw in sorted(inventory.items()))
        ))

        def inventory_file(directory, name, *, expected=None, max_bytes=None):
            if Path(directory).absolute() != window or name not in inventory:
                raise ValueError("native GPU verifier requested unbound inventory file")
            raw = inventory[name]
            if expected is not None and len(raw) != expected:
                raise ValueError("native GPU inventory file has wrong size")
            if max_bytes is not None and not 0 < len(raw) <= max_bytes:
                raise ValueError("native GPU inventory file exceeds byte bound")
            return raw

        # Reuse the full 1-MiB native raster/transfer validator, but feed
        # the very same immutable bytes that were included in the digest.
        # Missing terminal receipt still cannot certify a complete frame.
        checked = verify_capture(
            window, target_frame=target_frame, file_reader=inventory_file)
        if checked["capture_receipt_supplied"]:
            raise ValueError("window may not be certified as a full frame")
        total_draws += checked["draw_otag_primitive_pairs"]
        total_transfers += (
            checked["native_gpu_pairs_verified"] -
            checked["draw_otag_primitive_pairs"]
        )
        for offset in range(0, count, 2):
            first, second = events[offset:offset + 2]
            before_vram = inventory_file(
                window, first["snapshot"], expected=VRAM_BYTES)
            after_vram = inventory_file(
                window, second["snapshot"], expected=VRAM_BYTES)
            if idx and offset == 0 and last_operation == "draw":
                # Every transfer for target frame N happens while the
                # original C s_drawFrame is N-1. Once target DrawOTag
                # begins, frame N-1 transfers cannot reappear merely
                # because the bounded journal switched to window-001.
                if first["operation"] != "draw":
                    raise ValueError(
                        "native GPU transfer appears after DrawOTag across window boundary")
                if ((first["window"], first["draw_mode"]) !=
                        last_draw_post_state):
                    raise ValueError(
                        "GPU state continuity broken at native window boundary")
                if first.get("draw_env") != last_draw_post_env:
                    raise ValueError(
                        "DRAWENV continuity broken at native window boundary")
            if last_vram is not None and last_vram != hashlib.sha256(
                    before_vram).digest():
                raise ValueError("GPU VRAM continuity broken at native event/window boundary")
            last_vram = hashlib.sha256(after_vram).digest()
            last_operation = second["operation"]
            last_draw_post_state = (
                (second["window"], second["draw_mode"])
                if last_operation == "draw" else None
            )
            last_draw_post_env = (
                second.get("draw_env") if last_operation == "draw" else None
            )
            seen += 2
        logs_hash.update(log)
    if (root / f"window-{window_count:03d}").exists() or (
            root / f"window-{window_count:03d}").is_symlink():
        raise ValueError("unlisted native GPU window directory")
    if seen != written or total_draws != draws or total_transfers != transfers:
        raise ValueError("global native GPU event count does not match window evidence")
    # At the end of BOTH window audits, reject persistent mutations on disk.
    # A report can then be tied to one coherent, privately rechecked file
    # tree rather than a mixture of earlier hashes and later reads.
    for window, bound_files in inventory_digests:
        for name, digest in bound_files:
            fresh = private_window_file(
                window, name, max_bytes=VRAM_BYTES + 128 * 1024)
            if hashlib.sha256(fresh).digest() != digest:
                raise ValueError("native GPU evidence changed during window audit")
    # Preframe transfers alone cannot certify that the requested target
    # DrawOTag frame was ever reached by the native recorder.
    if total_draws == 0:
        raise ValueError("no target DrawOTag primitive in native GPU window capture")
    return {
        "native_window_schema": SCHEMA,
        "recorded_windows": window_count,
        "globally_ordered_native_gpu_events": seen,
        "native_draw_pairs": total_draws,
        "native_transfer_pairs": total_transfers,
        "vram_bridge_checks": seen // 2 - 1,
        "native_window_event_logs_sha256": logs_hash.hexdigest(),
        "native_window_all_files_sha256": file_tree_hash.hexdigest(),
        "capture_session_sha256": (
            hashlib.sha256(session.encode("ascii")).hexdigest()
            if session is not None else None),
        "recorded_window_closed_without_detected_loss": True,
        "whole_original_gameplay_frame_proven": False,
        "original_map02_authenticated": False,
        "physical_ps1_equivalence_proven": False,
        "raw_game_data_emitted": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_capture", type=Path)
    p.add_argument("--frame", type=int, required=True)
    args = p.parse_args()
    try:
        result = verify_native_windows(args.private_capture,
                                       target_frame=args.frame)
    except (OSError, ValueError) as exc:
        p.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
