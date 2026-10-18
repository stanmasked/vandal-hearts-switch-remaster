#!/usr/bin/env python3
"""Compare final PC native GPU journal snapshot to live BGR555 pipe bytes.

The source-pinned combined debug hook operates at DrawOTag completion, but
this offline audit alone cannot authenticate file writers or disc resources.
Full private VRAM files are never exposed in the report.
"""
import hashlib
import json
import os
from pathlib import Path
import stat

from tools.verify_map02_native_gpu_capture import (
    verify_capture, LOG, VRAM_BYTES, MAX_EVENT_BYTES
)
from tools.compare_map02_private_bgr555_frames import _object_pairs


def _stat_id(info):
    return tuple(getattr(info, name) for name in (
        "st_dev", "st_ino", "st_size", "st_ctime_ns", "st_mtime_ns"))


def audit(journal_dir, *, frame, final_pixels):
    if type(frame) is not int or not 1 <= frame <= 0xffffffff:
        raise ValueError("MAP02 joint GPU journal requires positive frame")
    if type(final_pixels) is not bytes or len(final_pixels) != VRAM_BYTES:
        raise ValueError("MAP02 joint GPU requires full 1024x512 native BGR555")
    root = Path(journal_dir).absolute()
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISDIR(before.st_mode)
                or stat.S_IMODE(before.st_mode) & 0o077):
            raise ValueError("MAP02 joint GPU journal directory not private")
        seen_before = set(os.listdir(fd))
        if LOG not in seen_before:
            raise ValueError("MAP02 joint GPU native event journal missing")
        # Existing validator independently replays all primitive/transfer
        # before/after VRAM snapshots against source-pinned operation rules.
        report = verify_capture(root, target_frame=frame)
        if (report["record_cap_reached"]
                or report["draw_otag_primitive_pairs"] < 1
                or report["native_gpu_pairs_verified"] < 1):
            raise ValueError("MAP02 joint GPU trace incomplete or capped")
        count = report["native_gpu_pairs_verified"] * 2
        log_path = root / LOG
        if log_path.is_symlink():
            raise ValueError("MAP02 joint GPU log is a symlink")
        log_bytes = log_path.read_bytes()
        if not 0 < len(log_bytes) <= MAX_EVENT_BYTES:
            raise ValueError("MAP02 joint GPU journal length invalid")
        events = [
            json.loads(line, object_pairs_hook=_object_pairs)
            for line in log_bytes.splitlines()
        ]
        if len(events) != count:
            raise ValueError("MAP02 joint GPU trace changed during replay")
        last = events[-1]
        if (last["operation"] != "draw" or last["phase"] != "after"
                or last["frame"] != frame
                or last["snapshot"] != f"gpu-{count - 1:04d}-vram.bin"):
            raise ValueError("MAP02 joint GPU lacks final DrawOTag after-VRAM witness")
        required = {LOG}
        for i, event in enumerate(events):
            if event["snapshot"] != f"gpu-{i:04d}-vram.bin":
                raise ValueError("MAP02 joint GPU snapshot inventory drift")
            required.add(event["snapshot"])
            if event["upload"]:
                required.add(event["upload"])
        if required != seen_before or required != set(os.listdir(fd)):
            raise ValueError("MAP02 joint GPU contains unexpected or missing files")
        # The last source-event snapshot must equal the bytes actually
        # delivered by the same one-shot launcher over stdout, not merely
        # a caller-authored frame label/hash. Stronger kernel writer
        # authentication would require an independent trusted observer.
        last_snapshot = root / last["snapshot"]
        if last_snapshot.is_symlink():
            raise ValueError("MAP02 final VRAM journal witness is a symlink")
        raw = last_snapshot.read_bytes()
        if len(raw) != VRAM_BYTES or raw != final_pixels:
            raise ValueError("MAP02 live frame differs from last journaled GPU after-VRAM")
        final_hash = hashlib.sha256(raw).hexdigest()
        if (final_hash != hashlib.sha256(final_pixels).hexdigest()
                or report["native_gpu_events_sha256"] != hashlib.sha256(log_bytes).hexdigest()):
            raise ValueError("MAP02 joint native GPU journal hash drift")
        # Catch mutation during this independent audit by replaying the full
        # native validator and checking directory identity and inventory.
        if (verify_capture(root, target_frame=frame) != report
                or _stat_id(os.fstat(fd)) != _stat_id(before)
                or set(os.listdir(fd)) != required):
            raise ValueError("MAP02 joint GPU journal changed during replay")
        return {
            "schema": "vh.map02.joint-native-gpu-terminal-frame.v1",
            "frame": frame,
            "gpu_journal_sha256": report["native_gpu_events_sha256"],
            "terminal_gpu_after_vram_sha256": final_hash,
            "gpu_pairs_verified": report["native_gpu_pairs_verified"],
            "gpu_draw_pairs_verified": report["draw_otag_primitive_pairs"],
            "terminal_after_vram_exactly_matches_live_pipe": True,
            "gpu_record_cap_not_reached": True,
            "actual_gameplay_or_ps1_pixels_authenticated": False,
            "journal_writer_kernel_authenticated": False,
            "hd_replacement_authorized": False,
        }
    finally:
        os.close(fd)
