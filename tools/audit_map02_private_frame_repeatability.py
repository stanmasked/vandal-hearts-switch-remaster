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
from tools.verify_map02_native_gpu_capture import LOG, MAX_EVENT_BYTES, MAX_RECORDS

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


def _private_gpu_event_lines(directory_fd, expected_digest):
    """Read a bounded original GPU JSONL journal through its held directory FD.

    The original GPU verifier already validated each event and metadata
    pair during the independent receipts' full replays. This pass compares
    byte-exact *records*, not sensitive FT4 arrays, pixel locations or
    user-supplied parsing directives.
    """
    fd = os.open(LOG, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                 os.O_CLOEXEC, dir_fd=directory_fd)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_nlink != 1
                or not 0 < before.st_size <= MAX_EVENT_BYTES):
            raise ValueError("MAP02 repeatability private GPU event log invalid")
        raw = bytearray()
        offset = 0
        while offset < before.st_size:
            chunk = os.pread(fd, min(65536, before.st_size - offset), offset)
            if not chunk:
                raise ValueError("MAP02 repeatability GPU event log truncated")
            raw.extend(chunk)
            offset += len(chunk)
        after = os.fstat(fd)
        routed = os.stat(LOG, dir_fd=directory_fd, follow_symlinks=False)
        fields = ("st_dev", "st_ino", "st_uid", "st_mode",
                  "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
        if (tuple(getattr(before, k) for k in fields) !=
                tuple(getattr(after, k) for k in fields)
                or tuple(getattr(before, k) for k in fields) !=
                   tuple(getattr(routed, k) for k in fields)
                or hashlib.sha256(raw).hexdigest() != expected_digest):
            raise ValueError("MAP02 repeatability GPU event evidence changed")
        if (not raw.endswith(b"\n") or b"\r" in raw
                or b"\x00" in raw):
            raise ValueError("MAP02 repeatability GPU event log noncanonical")
        lines = bytes(raw).split(b"\n")[:-1]
        if (not 2 <= len(lines) <= MAX_RECORDS
                or len(lines) % 2
                or any(not item for item in lines)):
            raise ValueError("MAP02 repeatability GPU event count invalid")
        return lines
    finally:
        os.close(fd)


def _gpu_event_differences(first_fd, second_fd, first_digest,
                           second_digest, first_pairs, second_pairs,
                           check_inventories):
    left = _private_gpu_event_lines(first_fd, first_digest)
    right = _private_gpu_event_lines(second_fd, second_digest)
    if len(left) != 2 * first_pairs or len(right) != 2 * second_pairs:
        raise ValueError("MAP02 repeatability GPU event count disagrees with replay")
    common = min(len(left), len(right))
    first_difference = None
    changed = 0
    for index in range(common):
        if left[index] != right[index]:
            changed += 1
            if first_difference is None:
                first_difference = index
    check_inventories()
    return {
        "first_gpu_event_count": len(left),
        "second_gpu_event_count": len(right),
        "gpu_event_records_compared": common,
        "different_gpu_event_records_in_common_prefix": changed,
        "unmatched_gpu_event_records": abs(len(left) - len(right)),
        "first_different_gpu_event_record_index": first_difference,
        "first_different_gpu_event_pair_index": (
            None if first_difference is None else first_difference // 2),
        "first_different_gpu_event_phase": (
            None if first_difference is None else (
                "before" if first_difference % 2 == 0 else "after")),
        "repeated_gpu_event_records_identical":
            changed == 0 and len(left) == len(right),
    }


def _gpu_snapshot_differences(first_fd, second_fd, first_pairs,
                              second_pairs, check_inventories):
    """Compare independent *intermediate* GPU VRAM, not only final frames.

    The JSONL event sequence may be identical while a draw produces
    different BGR555 memory. Names are derived exclusively from validated
    replay pair counts, and each raw snapshot is reread through the pinned
    journal directory FD (including full owner/mode/inode checks).
    """
    first_count, second_count = 2 * first_pairs, 2 * second_pairs
    common = min(first_count, second_count)
    # Domain-separated, fully ordered commitments for every native VRAM
    # snapshot, including unmatched trailing events. Distinct from the
    # JSONL event-log hash: the log can match while native pixels differ.
    first_commit = hashlib.sha256(b"vh.map02.native-vram-timeline.v1\x00")
    second_commit = hashlib.sha256(b"vh.map02.native-vram-timeline.v1\x00")
    first_commit.update(first_count.to_bytes(4, "little"))
    second_commit.update(second_count.to_bytes(4, "little"))
    changed = 0
    changed_before = 0
    changed_after = 0
    first_change = None
    first_changed_pixels = None
    first_changed_scanlines = None
    first_changed_stp_bits = None
    last_change = None
    first_reconvergence = None
    divergence_reappeared = False
    divergence_transitions = 0
    previous_different = None
    for step in range(max(first_count, second_count)):
        name = f"gpu-{step:04d}-vram.bin"
        left = right = None
        if step < first_count:
            left, _ = _private_raw(first_fd, name)
            first_commit.update(step.to_bytes(4, "little"))
            first_commit.update(left)
        if step < second_count:
            right, _ = _private_raw(second_fd, name)
            second_commit.update(step.to_bytes(4, "little"))
            second_commit.update(right)
        if step >= common:
            check_inventories()
            continue
        different_here = left != right
        if previous_different is not None and different_here != previous_different:
            divergence_transitions += 1
        if (not different_here and last_change is not None
                and first_reconvergence is None):
            first_reconvergence = step
        if different_here:
            if first_reconvergence is not None:
                divergence_reappeared = True
            last_change = step
            changed += 1
            if step % 2 == 0:
                changed_before += 1
            else:
                changed_after += 1
            if first_change is None:
                first_change = step
                first_changed_pixels, first_changed_scanlines, first_changed_stp_bits = (
                    _private_difference(left, right))
        previous_different = different_here
        check_inventories()
    return {
        "first_gpu_vram_snapshot_count": first_count,
        "second_gpu_vram_snapshot_count": second_count,
        "first_gpu_vram_timeline_sha256": first_commit.hexdigest(),
        "second_gpu_vram_timeline_sha256": second_commit.hexdigest(),
        "gpu_vram_timeline_commitments_identical":
            first_commit.digest() == second_commit.digest(),
        "gpu_vram_snapshots_compared": common,
        "different_gpu_vram_snapshots_in_common_prefix": changed,
        "different_gpu_before_vram_snapshots": changed_before,
        "different_gpu_after_vram_snapshots": changed_after,
        "unmatched_gpu_vram_snapshots": abs(first_count - second_count),
        "first_different_gpu_vram_snapshot_index": first_change,
        "last_different_gpu_vram_snapshot_index": last_change,
        "first_reconverged_gpu_vram_snapshot_index": first_reconvergence,
        "gpu_vram_equal_different_state_transitions": divergence_transitions,
        "gpu_vram_divergence_reappeared_after_reconvergence":
            divergence_reappeared,
        "gpu_vram_reconverged_at_common_prefix_end":
            changed > 0 and previous_different is False,
        "first_different_gpu_draw_pair_index": (
            None if first_change is None else first_change // 2),
        "first_different_gpu_snapshot_phase": (
            None if first_change is None else (
                "before" if first_change % 2 == 0 else "after")),
        "first_different_gpu_snapshot_changed_pixels": first_changed_pixels,
        "first_different_gpu_snapshot_changed_scanlines": first_changed_scanlines,
        "first_different_gpu_snapshot_stp_bit_differences": first_changed_stp_bits,
        "repeated_full_gpu_vram_snapshot_sequence_identical":
            first_count == second_count and changed == 0
            and first_commit.digest() == second_commit.digest(),
    }



def _joint_gpu_vram_first_divergence(snapshots, events):
    """Localize the first disagreement in aligned, replay-verified GPU pairs.

    Event JSONL and VRAM snapshots each contain before/after entries for
    the same verified GPU pair. Compare ordinals, never private content.
    An unmatched tail is a mismatch even if every common entry agrees.
    """
    # Validate the aggregate replay witness before composing it. A
    # refactor must not turn malformed/odd counts or missing first-change
    # evidence into an apparent bit-exact pair of private captures.
    fields = (
        (events, "first_gpu_event_count", True),
        (events, "second_gpu_event_count", True),
        (events, "gpu_event_records_compared", True),
        (events, "unmatched_gpu_event_records", False),
        (snapshots, "first_gpu_vram_snapshot_count", True),
        (snapshots, "second_gpu_vram_snapshot_count", True),
        (snapshots, "gpu_vram_snapshots_compared", True),
        (snapshots, "unmatched_gpu_vram_snapshots", False),
    )
    if (type(events) is not dict or type(snapshots) is not dict
            or any(type(report.get(key)) is not int
                   or not (2 if paired else 0) <= report[key] <= MAX_RECORDS
                   or report[key] % 2
                   for report, key, paired in fields)):
        raise ValueError("MAP02 GPU event and VRAM timeline counts invalid")
    first_count = events["first_gpu_event_count"]
    second_count = events["second_gpu_event_count"]
    common = events["gpu_event_records_compared"]
    unmatched = events["unmatched_gpu_event_records"]
    if (first_count != snapshots["first_gpu_vram_snapshot_count"]
            or second_count != snapshots["second_gpu_vram_snapshot_count"]
            or common != snapshots["gpu_vram_snapshots_compared"]
            or unmatched != snapshots["unmatched_gpu_vram_snapshots"]
            or common != min(first_count, second_count)
            or unmatched != abs(first_count - second_count)):
        raise ValueError("MAP02 GPU event and VRAM timeline counts disagree")
    first_event = events["first_different_gpu_event_record_index"]
    first_vram = snapshots["first_different_gpu_vram_snapshot_index"]
    # First-divergence ordinals must agree with the independently counted
    # common-prefix differences. Never silently accept "no first change"
    # when the replay auditor has counted one or more differences.
    for report, changed_key, first_index in (
        (events, "different_gpu_event_records_in_common_prefix", first_event),
        (snapshots, "different_gpu_vram_snapshots_in_common_prefix", first_vram),
    ):
        changed = report.get(changed_key)
        if (type(changed) is not int or not 0 <= changed <= common
                or (first_index is None) != (changed == 0)):
            raise ValueError("MAP02 GPU divergence count/first index disagree")
    for index in (first_event, first_vram):
        if index is not None and (type(index) is not int
                                  or not 0 <= index < common):
            raise ValueError("MAP02 GPU divergence ordinal invalid")
    candidates = [i for i in (first_event, first_vram) if i is not None]
    if unmatched:
        candidates.append(common)
    first = min(candidates) if candidates else None
    if first is None:
        kind = None
    elif first == common:
        kind = "unmatched-tail"
    elif first_event == first and first_vram == first:
        kind = "event-and-vram"
    elif first_event == first:
        kind = "event-only"
    else:
        kind = "vram-only"
    return {
        "first_joint_gpu_divergence_index": first,
        "first_joint_gpu_divergence_pair_index": (
            None if first is None else first // 2),
        "first_joint_gpu_divergence_phase": (
            None if first is None else (
                "before" if first % 2 == 0 else "after")),
        "first_joint_gpu_divergence_kind": kind,
    }


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
        # A bit-exact terminal frame is not enough: earlier DrawOTag
        # snapshots can diverge and later converge again. Audit every
        # replay-validated before/after native GPU VRAM snapshot.
        snapshots = _gpu_snapshot_differences(
            opened[1], opened[3],
            a["gpu_journal_pairs_verified"], b["gpu_journal_pairs_verified"],
            check_inventories)
        event_records = _gpu_event_differences(
            opened[1], opened[3],
            a["gpu_journal_sha256"], b["gpu_journal_sha256"],
            a["gpu_journal_pairs_verified"], b["gpu_journal_pairs_verified"],
            check_inventories)
        # A matching raw JSONL SHA is a global digest, while the new
        # event-record comparison independently localizes any change.
        if ((a["gpu_journal_sha256"] == b["gpu_journal_sha256"])
                != event_records["repeated_gpu_event_records_identical"]):
            raise ValueError("MAP02 GPU event digests disagree with records")
        joint = _joint_gpu_vram_first_divergence(snapshots, event_records)
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
            **snapshots,
            **event_records,
            **joint,
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
