#!/usr/bin/env python3
"""Check native GPU journal terminal VRAM against the live BGR555 stdout bytes.

All private journal files are opened through a held directory FD without
following links, hashed before and after independent native GPU replay, and
verified against a fixed file inventory. This is evidence integrity, NOT a
trusted kernel record of the journal's process writer or PS1 authenticity.
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


def _read_pinned(directory_fd, name, *, keep=False):
    """Open relative to the held private directory and verify stable identity."""
    if (type(name) is not str or "/" in name or "\\" in name
            or name in ("", ".", "..")):
        raise ValueError("MAP02 joint journal unsafe filename")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    file_fd = os.open(name, flags, dir_fd=directory_fd)
    try:
        first = os.fstat(file_fd)
        if name == LOG:
            minimum, maximum = 1, MAX_EVENT_BYTES
        elif name.startswith("gpu-") and name.endswith("-vram.bin"):
            minimum = maximum = VRAM_BYTES
        elif name.startswith("gpu-") and name.endswith("-upload.bin"):
            minimum, maximum = 1, 32768
        else:
            raise ValueError("MAP02 joint journal unexpected file name")
        if (not stat.S_ISREG(first.st_mode) or first.st_nlink != 1
                or stat.S_IMODE(first.st_mode) != 0o600
                or not minimum <= first.st_size <= maximum):
            raise ValueError("MAP02 joint journal file type, mode or size invalid")
        digest = hashlib.sha256()
        data = bytearray() if keep else None
        remaining = first.st_size
        while remaining:
            part = os.read(file_fd, min(65536, remaining))
            if not part:
                raise ValueError("MAP02 joint journal file truncated during replay")
            digest.update(part)
            if data is not None:
                data.extend(part)
            remaining -= len(part)
        if (_stat_id(first) != _stat_id(os.fstat(file_fd))
                or _stat_id(first) != _stat_id(
                    os.stat(name, dir_fd=directory_fd, follow_symlinks=False))):
            raise ValueError("MAP02 joint journal file replaced while reading")
        return (_stat_id(first), digest.hexdigest()), (
            bytes(data) if data is not None else None)
    finally:
        os.close(file_fd)


def _inventory_digest(directory_fd, names, *, retain=()):
    if len(names) > 129:
        raise ValueError("MAP02 joint journal inventory exceeds bounded limit")
    results, retained = {}, {}
    for name in sorted(names):
        results[name], data = _read_pinned(
            directory_fd, name, keep=name in retain)
        if data is not None:
            retained[name] = data
    return results, retained


def audit(journal_dir, *, frame, final_pixels):
    if type(frame) is not int or not 1 <= frame <= 0xffffffff:
        raise ValueError("MAP02 joint GPU journal requires positive frame")
    if type(final_pixels) is not bytes or len(final_pixels) != VRAM_BYTES:
        raise ValueError("MAP02 joint GPU requires full 1024x512 native BGR555")
    root = Path(journal_dir).absolute()
    directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        first_dir = os.fstat(directory_fd)
        if (not stat.S_ISDIR(first_dir.st_mode)
                or stat.S_IMODE(first_dir.st_mode) & 0o077):
            raise ValueError("MAP02 joint GPU journal directory not private")
        names = set(os.listdir(directory_fd))
        if LOG not in names:
            raise ValueError("MAP02 joint GPU native event journal missing")
        initial, retained = _inventory_digest(
            directory_fd, names, retain=(LOG,))
        log_bytes = retained[LOG]
        if (not log_bytes.endswith(b"\n") or b"\r" in log_bytes
                or b"\x00" in log_bytes):
            raise ValueError("MAP02 joint GPU journal has invalid line framing")

        # Independent event/snapshot verification is retained unchanged.
        report = verify_capture(root, target_frame=frame)
        if (report["record_cap_reached"]
                or report["draw_otag_primitive_pairs"] < 1
                or report["native_gpu_pairs_verified"] < 1):
            raise ValueError("MAP02 joint GPU trace incomplete or capped")
        count = report["native_gpu_pairs_verified"] * 2
        events = [
            json.loads(line, object_pairs_hook=_object_pairs)
            for line in log_bytes.splitlines()
        ]
        if len(events) != count:
            raise ValueError("MAP02 joint GPU trace changed during replay")
        last = events[-1]
        final_name = f"gpu-{count - 1:04d}-vram.bin"
        if (last["operation"] != "draw" or last["phase"] != "after"
                or last["frame"] != frame or last["snapshot"] != final_name):
            raise ValueError("MAP02 joint GPU lacks final DrawOTag after-VRAM witness")
        required = {LOG}
        for i, event in enumerate(events):
            if event["snapshot"] != f"gpu-{i:04d}-vram.bin":
                raise ValueError("MAP02 joint GPU snapshot inventory drift")
            required.add(event["snapshot"])
            if event["upload"]:
                required.add(event["upload"])
        if required != names or required != set(os.listdir(directory_fd)):
            raise ValueError("MAP02 joint GPU contains unexpected or missing files")
        _, last_bytes = _read_pinned(directory_fd, final_name, keep=True)
        if last_bytes != final_pixels:
            raise ValueError("MAP02 live frame differs from last journaled GPU after-VRAM")
        final_hash = hashlib.sha256(last_bytes).hexdigest()
        if (report["native_gpu_events_sha256"] != hashlib.sha256(log_bytes).hexdigest()
                or final_hash != initial[final_name][1]):
            raise ValueError("MAP02 joint native GPU journal hash drift")

        # Re-check ALL journal files rather than trusting the event log's
        # before/after image names; this detects replacement of even a
        # nonterminal snapshot while the native validator was running.
        if verify_capture(root, target_frame=frame) != report:
            raise ValueError("MAP02 joint native GPU replay changed")
        afterward, _ = _inventory_digest(directory_fd, required)
        if (afterward != initial or set(os.listdir(directory_fd)) != required
                or _stat_id(os.fstat(directory_fd)) != _stat_id(first_dir)
                or _stat_id(os.stat(root, follow_symlinks=False))
                != _stat_id(first_dir)):
            raise ValueError("MAP02 joint GPU journal files/directory changed during replay")
        return {
            "schema": "vh.map02.joint-native-gpu-terminal-frame.v1",
            "frame": frame,
            "gpu_journal_sha256": report["native_gpu_events_sha256"],
            "terminal_gpu_after_vram_sha256": final_hash,
            "gpu_pairs_verified": report["native_gpu_pairs_verified"],
            "gpu_draw_pairs_verified": report["draw_otag_primitive_pairs"],
            "terminal_after_vram_exactly_matches_live_pipe": True,
            "gpu_record_cap_not_reached": True,
            "private_journal_fd_inventory_stable": True,
            "actual_gameplay_or_ps1_pixels_authenticated": False,
            "journal_writer_kernel_authenticated": False,
            "hd_replacement_authorized": False,
        }
    finally:
        os.close(directory_fd)
