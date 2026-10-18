#!/usr/bin/env python3
"""One private Linux MAP02 GPU+terminal-frame run followed by two full replays.

Requires a user-supplied, SHA-pinned native ELF and two existing empty owner-
private directories. Uses no bundled game/disc resources and never prints
native BGR555 pixels, private filenames, or filesystem inode numbers.

This is an operational integrity convenience, NOT retail PC/PS1 authenticity,
process-writer attestation, gameplay certification or HD authorization.
"""
import argparse
import json
from pathlib import Path

from tools.capture_map02_live_frame_pipe import capture
from tools.replay_map02_live_frame_receipt import replay

SCHEMA = "vh.map02.private-joint-elf-run-two-replays.v1"
WIDTH, HEIGHT = 1024, 512
EXPECTED_CAPTURE = "vh.map02.live-child-pipe-bgr555-gpu.v1"
EXPECTED_REPLAY = "vh.map02.live-child-pipe-gpu-replayed.v1"


def run(executable, output_dir, gpu_journal_dir, *, frame, executable_sha256,
        timeout=10, args=()):
    """Run one pinned Linux ELF, then independently audit the same bytes twice.

    The output/journal directories must already exist, be empty, and have
    owner-private permissions. On failure, the launcher's fail-closed
    publication and the independent replay checks determine refusal.
    """
    captured = capture(
        executable, output_dir, frame=frame, width=WIDTH, height=HEIGHT,
        executable_sha256=executable_sha256, timeout=timeout, args=args,
        gpu_journal_dir=gpu_journal_dir)
    if (captured.get("schema") != EXPECTED_CAPTURE
            or captured.get("frame") != frame
            or captured.get("width") != WIDTH
            or captured.get("height") != HEIGHT
            or captured.get("child_writable_gpu_journal_fd_observed") is not True
            or captured.get("terminal_after_vram_matched") is not True
            or captured.get("gpu_journal_writer_kernel_authenticated") is not False
            or captured.get("hd_replacement_authorized") is not False):
        raise ValueError("MAP02 native joint launch returned incomplete evidence")

    # Do not rely solely on capture's receipt or trust a caller-supplied
    # hash: independently reopen all private original files, journal
    # snapshots and the pinned executable in TWO separate audit passes.
    first = replay(output_dir, executable=executable,
                   gpu_journal_dir=gpu_journal_dir)
    second = replay(output_dir, executable=executable,
                    gpu_journal_dir=gpu_journal_dir)
    if first != second:
        raise ValueError("MAP02 private GPU/frame evidence changed between replays")
    if (first.get("schema") != EXPECTED_REPLAY
            or first.get("frame") != frame
            or (first.get("width"), first.get("height")) != (WIDTH, HEIGHT)
            or first.get("image_sha256") != captured.get("image_sha256")
            or first.get("executable_sha256") != captured.get("executable_sha256")
            or first.get("gpu_journal_sha256") != captured.get("gpu_journal_sha256")
            or first.get("terminal_gpu_after_vram_sha256") !=
               captured.get("terminal_gpu_after_vram_sha256")
            or first.get("gpu_journal_pairs_verified") !=
               captured.get("gpu_journal_pairs_verified")
            or first.get("gpu_terminal_frame_equal") is not True
            or first.get("child_writable_gpu_journal_fd_observed") is not True
            or first.get("same_launcher_gpu_journal_operationally_checked") is not True
            or first.get("gpu_journal_writer_kernel_authenticated") is not False
            or first.get("retail_disc_or_ps1_pixel_source_authenticated") is not False
            or first.get("native_gpu_log_same_process_authenticated") is not False
            or first.get("hd_replacement_authorized") is not False):
        raise ValueError("MAP02 joint capture and independent replays disagree")
    return {
        "schema": SCHEMA,
        "frame": frame,
        "width": WIDTH,
        "height": HEIGHT,
        "executable_sha256": first["executable_sha256"],
        "terminal_bgr555_sha256": first["image_sha256"],
        "gpu_journal_sha256": first["gpu_journal_sha256"],
        "terminal_gpu_after_vram_sha256":
            first["terminal_gpu_after_vram_sha256"],
        "gpu_journal_pairs_verified": first["gpu_journal_pairs_verified"],
        "two_full_independent_private_replays_equal": True,
        "child_writable_gpu_journal_fd_observed": True,
        "terminal_frame_exactly_equals_gpu_after_vram": True,
        "retail_gameplay_or_ps1_pixels_authenticated": False,
        "native_gpu_log_same_process_authenticated": False,
        "gpu_journal_writer_kernel_authenticated": False,
        "hd_replacement_authorized": False,
        "private_pixel_bytes_or_paths_emitted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--executable-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--gpu-journal-dir", type=Path, required=True)
    parser.add_argument("--frame", type=int, required=True)
    parser.add_argument("--timeout", type=int, default=10)
    ns = parser.parse_args()
    try:
        report = run(
            ns.executable, ns.output_dir, ns.gpu_journal_dir,
            frame=ns.frame, executable_sha256=ns.executable_sha256,
            timeout=ns.timeout)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
