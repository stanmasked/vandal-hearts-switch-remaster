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
from pathlib import Path

from tools.publish_map02_blendg1_witness import _private_directory
from tools.verify_map02_frame_bundle import fields, number, parse_json
from tools.verify_map02_native_gpu_capture import (
    LOG, MAX_RECORDS, STATUS, private_file, verify_capture,
)
from tools.verify_map02_vram_timeline import VRAM_BYTES

INDEX = "gpu-native-window-index.json"
SCHEMA = "vh.map02.native-windows.v1"
MAX_WINDOWS = 2


def verify_native_windows(directory, *, target_frame):
    root = _private_directory(directory)
    number(target_frame, "GPU DrawOTag frame", 1, 2**32 - 1)
    if (root / STATUS).exists() or (root / STATUS).is_symlink():
        raise ValueError("legacy native GPU receipt cannot be mixed with windowed capture")
    raw, index_identity = private_file(
        root, INDEX, max_bytes=4096, _with_identity=True)
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
    logs_hash = hashlib.sha256()
    file_tree_hash = hashlib.sha256()
    audited_files = {}
    for idx in range(window_count):
        window = _private_directory(root / f"window-{idx:03d}")
        if (window / STATUS).exists() or (window / STATUS).is_symlink():
            raise ValueError("legacy per-window receipt incorrectly asserts complete frame")
        log = private_file(window, LOG, max_bytes=128 * 1024)
        if (not log.endswith(b"\n") or b"\r" in log or
                any(not entry for entry in log.split(b"\n")[:-1])):
            raise ValueError("noncanonical native window JSONL")
        events = [parse_json(item, "native GPU window event") for item
                  in log.split(b"\n")[:-1]]
        count = min(MAX_RECORDS, written - idx * MAX_RECORDS)
        if len(events) != count or count % 2:
            raise ValueError("missing, duplicated or reordered native GPU window events")
        expected_files = {LOG} | {e.get("snapshot") for e in events}
        expected_files |= {e.get("upload") for e in events if e.get("upload")}
        if {item.name for item in window.iterdir()} != expected_files:
            raise ValueError("unlisted or missing files in native GPU capture window")
        # Hash ALL published capture bytes, not only JSONL: unreferenced or
        # replaced snapshots must never inherit the same source binding.
        for name in sorted(expected_files):
            data, inode = private_file(
                window, name, max_bytes=VRAM_BYTES + 128 * 1024,
                _with_identity=True)
            digest = hashlib.sha256(data).digest()
            audited_files[(idx, name)] = (digest, inode)
            file_tree_hash.update(f"window-{idx:03d}/{name}\0".encode("ascii"))
            file_tree_hash.update(digest)
        # The existing full 1-MiB VRAM auditor is reused, but its
        # missing-receipt result is deliberately not interpreted as a
        # complete original frame.
        checked = verify_capture(window, target_frame=target_frame)
        if checked["capture_receipt_supplied"]:
            raise ValueError("window may not be certified as a full frame")
        total_draws += checked["draw_otag_primitive_pairs"]
        total_transfers += (
            checked["native_gpu_pairs_verified"] -
            checked["draw_otag_primitive_pairs"]
        )
        for offset in range(0, count, 2):
            first, second = events[offset:offset + 2]
            before_vram = private_file(
                window, first["snapshot"], expected=VRAM_BYTES)
            after_vram = private_file(
                window, second["snapshot"], expected=VRAM_BYTES)
            if last_vram is not None and last_vram != hashlib.sha256(
                    before_vram).digest():
                raise ValueError("GPU VRAM continuity broken at native event/window boundary")
            last_vram = hashlib.sha256(after_vram).digest()
            seen += 2
        logs_hash.update(log)
    if (root / f"window-{window_count:03d}").exists() or (
            root / f"window-{window_count:03d}").is_symlink():
        raise ValueError("unlisted native GPU window directory")
    if seen != written or total_draws != draws or total_transfers != transfers:
        raise ValueError("global native GPU event count does not match window evidence")
    # The original tree hashes, the full window audits and the continuity
    # checks must refer to the same inode for every file. No game bytes
    # are returned; only hashes and file identity are retained temporarily.
    if {item.name for item in root.iterdir()} != expected_root_entries:
        raise ValueError("native GPU window root changed during audit")
    latest_index, latest_identity = private_file(
        root, INDEX, max_bytes=4096, _with_identity=True)
    if latest_index != raw or latest_identity != index_identity:
        raise ValueError("native GPU window index changed during audit")
    for idx in range(window_count):
        window = _private_directory(root / f"window-{idx:03d}")
        expected_names = {name for number, name in audited_files if number == idx}
        if {item.name for item in window.iterdir()} != expected_names:
            raise ValueError("native GPU window file set changed during audit")
        for name in sorted(expected_names):
            data, identity = private_file(
                window, name, max_bytes=VRAM_BYTES + 128 * 1024,
                _with_identity=True)
            digest, original_identity = audited_files[(idx, name)]
            if (hashlib.sha256(data).digest() != digest or
                    identity != original_identity):
                raise ValueError("native GPU window evidence changed during audit")
    return {
        "native_window_schema": SCHEMA,
        "recorded_windows": window_count,
        "globally_ordered_native_gpu_events": seen,
        "native_draw_pairs": total_draws,
        "native_transfer_pairs": total_transfers,
        "vram_bridge_checks": seen // 2 - 1,
        "native_window_event_logs_sha256": logs_hash.hexdigest(),
        "native_window_all_files_sha256": file_tree_hash.hexdigest(),
        # Raw 1-MiB post-event VRAM endpoint. This does not establish an
        # on-screen framebuffer location or original game authenticity.
        "final_native_vram_sha256": last_vram.hex(),
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
