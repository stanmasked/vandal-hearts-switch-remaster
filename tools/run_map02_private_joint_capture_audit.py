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
import os
from pathlib import Path
import stat

from tools.capture_map02_live_frame_pipe import capture
from tools.replay_map02_live_frame_receipt import replay

SCHEMA = "vh.map02.private-joint-elf-run-two-replays.v1"
WIDTH, HEIGHT = 1024, 512
EXPECTED_CAPTURE = "vh.map02.live-child-pipe-bgr555-gpu.v1"
EXPECTED_REPLAY = "vh.map02.live-child-pipe-gpu-replayed.v1"


def _session_inode_witness(output_dir, gpu_journal_dir):
    """Return private in-memory identity of both full replay inventories.

    Names and inodes are only used for local equality, never returned
    in the public two-replay digest-only report.
    """
    witness = []
    for root, expected in (
        (output_dir, {"process-frame.bgr555", "process-frame.json"}),
        (gpu_journal_dir, None),
    ):
        path = Path(root).absolute()
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY |
                     os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            first = os.fstat(fd)
            if (not stat.S_ISDIR(first.st_mode)
                    or stat.S_IMODE(first.st_mode) & 0o077):
                raise ValueError("MAP02 two-pass directory is not private")
            names = set(os.listdir(fd))
            if ((expected is not None and names != expected)
                    or not names or len(names) > 129):
                raise ValueError("MAP02 private two-pass inventory invalid")
            identities = []
            for name in sorted(names):
                if name in ("", ".", "..") or "/" in name or "\\" in name:
                    raise ValueError("MAP02 private two-pass filename invalid")
                state = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if (not stat.S_ISREG(state.st_mode)
                        or stat.S_IMODE(state.st_mode) != 0o600
                        or state.st_nlink != 1):
                    raise ValueError("MAP02 private two-pass file not owner-private")
                identities.append((
                    name, state.st_dev, state.st_ino, state.st_mode,
                    state.st_nlink, state.st_size,
                    state.st_mtime_ns, state.st_ctime_ns))
            last = os.fstat(fd)
            routed = os.stat(path, follow_symlinks=False)
            def dir_id(info):
                return (info.st_dev, info.st_ino, info.st_mode,
                        info.st_mtime_ns, info.st_ctime_ns)
            if (dir_id(first) != dir_id(last)
                    or dir_id(first) != dir_id(routed)
                    or set(os.listdir(fd)) != names):
                raise ValueError("MAP02 private two-pass directory changed")
            witness.append((dir_id(first), tuple(identities)))
        finally:
            os.close(fd)
    return tuple(witness)



def run(executable, output_dir, gpu_journal_dir, *, frame, executable_sha256,
        timeout=10, args=()):
    """Run one pinned Linux ELF, then independently audit the same bytes twice.

    The output/journal directories must already exist, be empty, and have
    owner-private permissions. On failure, the launcher's fail-closed
    publication and the independent replay checks determine refusal.
    """
    # A capture-success reply alone cannot pin a filesystem inode.
    # Take the inventory witness BEFORE the launcher's held directory FDs
    # close; a same-byte replacement before the first offline replay must
    # then fail even when all SHA-256 digests remain identical.
    publication_witness = []
    def pin_at_publication():
        publication_witness.append(
            _session_inode_witness(output_dir, gpu_journal_dir))

    captured = capture(
        executable, output_dir, frame=frame, width=WIDTH, height=HEIGHT,
        executable_sha256=executable_sha256, timeout=timeout, args=args,
        gpu_journal_dir=gpu_journal_dir,
        post_publish_witness=pin_at_publication)
    if len(publication_witness) != 1:
        raise ValueError("MAP02 missing same-launch private publication identity")
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
    pinned_session = publication_witness[0]
    if _session_inode_witness(output_dir, gpu_journal_dir) != pinned_session:
        raise ValueError("MAP02 private GPU/frame files changed after publication")
    first = replay(output_dir, executable=executable,
                   gpu_journal_dir=gpu_journal_dir)
    if _session_inode_witness(output_dir, gpu_journal_dir) != pinned_session:
        raise ValueError("MAP02 private GPU/frame files changed between replays")
    second = replay(output_dir, executable=executable,
                    gpu_journal_dir=gpu_journal_dir)
    if (first != second
            or _session_inode_witness(output_dir, gpu_journal_dir)
               != pinned_session):
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
        "private_frame_and_journal_inodes_stable_through_replays": True,
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
