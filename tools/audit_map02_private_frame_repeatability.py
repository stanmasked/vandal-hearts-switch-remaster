#!/usr/bin/env python3
"""Audit two independent native ELF/GPU/BGR555 runs for repeatable output.

Both runs must already be separately captured with the same SHA-pinned ELF
and selected frame; each gets two full independent receipt+GPU-journal
replays. Report only aggregate differences and SHA-256 commitments.
Different PC frames can be useful diagnostic evidence; they do not
authenticate original PS1 pixels or actual retail gameplay rendering.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

from tools.prepare_map02_private_frame_pair import (
    _directory, _check_directory, _private_raw, WIDTH, HEIGHT,
)
from tools.replay_map02_live_frame_receipt import replay

SCHEMA = "vh.map02.private-two-elf-gpu-frame-repeatability.v1"
REPLAY_SCHEMA = "vh.map02.live-child-pipe-gpu-replayed.v1"


def _require_replay(data):
    if (type(data) is not dict or data.get("schema") != REPLAY_SCHEMA
            or type(data.get("frame")) is not int or not 1 <= data["frame"] <= 0xffffffff
            or (data.get("width"), data.get("height")) != (WIDTH, HEIGHT)
            or data.get("gpu_terminal_frame_equal") is not True
            or data.get("child_writable_gpu_journal_fd_observed") is not True
            or data.get("same_launcher_gpu_journal_operationally_checked") is not True
            or data.get("gpu_journal_writer_kernel_authenticated") is not False
            or data.get("native_gpu_log_same_process_authenticated") is not False
            or data.get("retail_disc_or_ps1_pixel_source_authenticated") is not False
            or data.get("hd_replacement_authorized") is not False
            or type(data.get("gpu_journal_pairs_verified")) is not int
            or not 1 <= data["gpu_journal_pairs_verified"] < 32):
        raise ValueError("MAP02 independent live GPU/frame replay is incomplete")
    for key in ("image_sha256", "executable_sha256",
                "terminal_gpu_after_vram_sha256", "gpu_journal_sha256"):
        v = data.get(key)
        if (type(v) is not str or len(v) != 64
                or any(c not in "0123456789abcdef" for c in v)):
            raise ValueError("MAP02 repeated capture digest format invalid")
    if data["image_sha256"] != data["terminal_gpu_after_vram_sha256"]:
        raise ValueError("MAP02 replayed terminal frame differs from final VRAM")


def _pinned_inventory(fd):
    """Capture every regular file's identity before any replay begins.

    Replaying a valid digest alone cannot detect a fully replaced same-byte
    file if a new inode is installed before the first post-replay read.
    Directory descriptors are held through the entire two-run comparison.
    """
    root = os.fstat(fd)
    names = os.listdir(fd)
    if not names or len(names) > 129:
        raise ValueError("MAP02 repeatability private inventory invalid")
    identities = []
    for name in sorted(names):
        if name in ("", ".", "..") or "/" in name or "\\" in name:
            raise ValueError("MAP02 repeatability private filename invalid")
        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1):
            raise ValueError("MAP02 repeatability evidence file not private")
        identities.append((
            name, st.st_dev, st.st_ino, st.st_uid, st.st_mode,
            st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns))
    after = os.fstat(fd)
    if (root.st_dev, root.st_ino, root.st_mtime_ns, root.st_ctime_ns) != (
            after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns
    ) or set(os.listdir(fd)) != set(names):
        raise ValueError("MAP02 repeatability private inventory changed")
    return tuple(identities)


def _private_difference(first, second):
    """Bounded full 16-bit pixel comparison without publishing coordinates."""
    if len(first) != WIDTH * HEIGHT * 2 or len(second) != len(first):
        raise ValueError("MAP02 repeatability frame dimensions differ")
    different = 0
    changed_lines = 0
    stp_changes = 0
    for y in range(HEIGHT):
        changes_here = 0
        start = y * WIDTH * 2
        for off in range(start, start + WIDTH * 2, 2):
            left = first[off] | (first[off + 1] << 8)
            right = second[off] | (second[off + 1] << 8)
            if left != right:
                changes_here += 1
                stp_changes += bool((left ^ right) & 0x8000)
        different += changes_here
        changed_lines += bool(changes_here)
    return different, changed_lines, stp_changes


def audit(first_frame, first_journal, second_frame, second_journal, executable):
    folders = tuple(Path(x).absolute() for x in (
        first_frame, first_journal, second_frame, second_journal))
    opened = []
    sessions = []
    try:
        for folder in folders:
            fd, identity = _directory(folder)
            opened.append(fd)
            sessions.append((folder, identity))
        if len({identity[:2] for _, identity in sessions}) != 4:
            raise ValueError("MAP02 independent run directory roles overlap")

        # Pin all four complete inventories BEFORE any independent replay,
        # including nonterminal GPU snapshots and JSONL journal inodes.
        inventory_before = tuple(_pinned_inventory(fd) for fd in opened)
        def check_inventories():
            if tuple(_pinned_inventory(fd) for fd in opened) != inventory_before:
                raise ValueError("MAP02 independent GPU/frame file identity changed")

        evidence = []
        for index in (0, 1):
            image_dir, journal_dir = folders[index*2:index*2+2]
            first = replay(image_dir, executable=executable,
                           gpu_journal_dir=journal_dir)
            _require_replay(first)
            check_inventories()
            raw, original_identity = _private_raw(
                opened[index*2], "process-frame.bgr555")
            if hashlib.sha256(raw).hexdigest() != first["image_sha256"]:
                raise ValueError("MAP02 independent native frame bytes changed")
            second = replay(image_dir, executable=executable,
                            gpu_journal_dir=journal_dir)
            check_inventories()
            raw_again, confirmed_identity = _private_raw(
                opened[index*2], "process-frame.bgr555")
            if (first != second or original_identity != confirmed_identity
                    or raw_again != raw):
                raise ValueError("MAP02 independent run changed during replay")
            evidence.append((first, raw))

        a, b = (v[0] for v in evidence)
        if (a["frame"] != b["frame"]
                or a["executable_sha256"] != b["executable_sha256"]):
            raise ValueError("MAP02 independent runs differ in frame or ELF identity")
        different, lines, stp = _private_difference(
            evidence[0][1], evidence[1][1])
        check_inventories()
        for fd, (path, identity) in zip(opened, sessions):
            _check_directory(fd, path, identity)
        return {
            "schema": SCHEMA,
            "frame": a["frame"], "width": WIDTH, "height": HEIGHT,
            "executable_sha256": a["executable_sha256"],
            "first_image_sha256": a["image_sha256"],
            "second_image_sha256": b["image_sha256"],
            "first_gpu_journal_sha256": a["gpu_journal_sha256"],
            "second_gpu_journal_sha256": b["gpu_journal_sha256"],
            "first_gpu_pairs_verified": a["gpu_journal_pairs_verified"],
            "second_gpu_pairs_verified": b["gpu_journal_pairs_verified"],
            "different_bgr555_pixels": different,
            "changed_scanlines": lines,
            "stp_bit_differences": stp,
            "repeated_native_frame_pixels_identical": different == 0,
            "repeated_gpu_final_vram_identical": different == 0,
            "repeated_gpu_event_journal_identical":
                a["gpu_journal_sha256"] == b["gpu_journal_sha256"],
            "two_full_replays_per_capture_verified": True,
            "four_private_file_inventories_stable_through_replays": True,
            "actual_gameplay_rendering_authenticated": False,
            "ps1_hardware_pixel_equivalence_verified": False,
            "gpu_journal_writer_kernel_authenticated": False,
            "hd_replacement_authorized": False,
            "private_pixel_bytes_or_paths_emitted": False,
        }
    finally:
        for fd in reversed(opened):
            os.close(fd)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--first-frame", type=Path, required=True)
    p.add_argument("--first-journal", type=Path, required=True)
    p.add_argument("--second-frame", type=Path, required=True)
    p.add_argument("--second-journal", type=Path, required=True)
    p.add_argument("--executable", type=Path, required=True)
    ns = p.parse_args()
    try:
        report = audit(
            ns.first_frame, ns.first_journal,
            ns.second_frame, ns.second_journal, ns.executable)
    except (OSError, ValueError):
        p.error("MAP02 independent native run repeatability audit failed")
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
