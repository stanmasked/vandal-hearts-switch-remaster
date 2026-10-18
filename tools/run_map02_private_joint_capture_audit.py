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
import subprocess

from tools.capture_map02_live_frame_pipe import capture
from tools.replay_map02_live_frame_receipt import replay
from tools.compare_map02_private_bgr555_frames import compare
from tools.bridge_map02_private_frame_native import _private_frame_pair_identity
from tools.join_map02_live_frame_native import join as join_original_native

SCHEMA = "vh.map02.private-joint-elf-run-two-replays.v1"
WIDTH, HEIGHT = 1024, 512
EXPECTED_CAPTURE = "vh.map02.live-child-pipe-bgr555-gpu.v1"
EXPECTED_REPLAY = "vh.map02.live-child-pipe-gpu-replayed.v1"


def _require_owner_private_claimed_pair(frame_pair_dir):
    """Require exactly three owner-only regular files before reading PS1 claims.

    Called before the ELF launch: refuse accidentally shared directories,
    extra files, symlinks, and hardlinks instead of quietly accepting an
    unprotected allegedly private reference or candidate image.
    """
    path = Path(frame_pair_dir).absolute()
    directory_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY |
                           os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        root = os.fstat(directory_fd)
        if (not stat.S_ISDIR(root.st_mode) or root.st_uid != os.getuid()
                or stat.S_IMODE(root.st_mode) & 0o077):
            raise ValueError("MAP02 claimed frame pair directory must be owner-private")
        expected = {"frames.json", "reference.bgr555", "candidate.bgr555"}
        if set(os.listdir(directory_fd)) != expected:
            raise ValueError("MAP02 claimed frame pair has unexpected file inventory")
        for name in sorted(expected):
            entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if (not stat.S_ISREG(entry.st_mode)
                    or entry.st_uid != os.getuid()
                    or stat.S_IMODE(entry.st_mode) != 0o600
                    or entry.st_nlink != 1):
                raise ValueError("MAP02 claimed frame pair file must be owner-private and singly linked")
        if (root.st_dev, root.st_ino) != (
                os.stat(path, follow_symlinks=False).st_dev,
                os.stat(path, follow_symlinks=False).st_ino):
            raise ValueError("MAP02 claimed frame pair directory replaced")
    finally:
        os.close(directory_fd)


def _preflight_original_source_files(native_capture_dir, source_capture_dir,
                                     launch_receipt, preflight_report,
                                     output_dir, gpu_journal_dir,
                                     frame_pair_dir):
    """Validate private FT4/VRAM input roles before any child is launched.

    The full independent source replay remains responsible for checking
    authenticated contents. This preliminary check refuses missing files,
    symlinks, public modes, shared roles, and incorrectly typed inputs so
    a foreseeable source-input failure never publishes a new BGR555 frame.
    """
    identities = set()
    expected_dirs = (
        native_capture_dir, source_capture_dir,
        output_dir, gpu_journal_dir, frame_pair_dir,
    )
    for value in expected_dirs:
        directory = Path(value).absolute()
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY |
                     os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(fd)
            path_info = os.stat(directory, follow_symlinks=False)
            key = (info.st_dev, info.st_ino)
            if (not stat.S_ISDIR(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) & 0o077
                    or key != (path_info.st_dev, path_info.st_ino)):
                raise ValueError("MAP02 original source directory is not private")
            if key in identities:
                raise ValueError("MAP02 original source directory roles overlap")
            identities.add(key)
        finally:
            os.close(fd)
    for value in (launch_receipt, preflight_report):
        path = Path(value).absolute()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW |
                     os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            info = os.fstat(fd)
            path_info = os.stat(path, follow_symlinks=False)
            key = (info.st_dev, info.st_ino)
            if (not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_nlink != 1
                    or not 0 < info.st_size <= 16 * 1024 * 1024
                    or key != (path_info.st_dev, path_info.st_ino)):
                raise ValueError("MAP02 original source witness file not private")
            if key in identities:
                raise ValueError("MAP02 original source roles overlap")
            identities.add(key)
        finally:
            os.close(fd)


def _session_inode_witness(output_dir, gpu_journal_dir, *,
                           held_output_fd=None, held_journal_fd=None):
    """Return private in-memory identity of both full replay inventories.

    Names and inodes are only used for local equality, never returned
    in the public two-replay digest-only report.
    """
    witness = []
    for root, expected, held in (
        (output_dir, {"process-frame.bgr555", "process-frame.json"},
         held_output_fd),
        (gpu_journal_dir, None, held_journal_fd),
    ):
        path = Path(root).absolute()
        fd = (os.dup(held) if held is not None
              else os.open(path, os.O_RDONLY | os.O_DIRECTORY |
                           os.O_NOFOLLOW | os.O_CLOEXEC))
        try:
            first = os.fstat(fd)
            if (not stat.S_ISDIR(first.st_mode)
                    or first.st_uid != os.getuid()
                    or stat.S_IMODE(first.st_mode) & 0o077):
                raise ValueError("MAP02 two-pass directory is not owner-private")
            names = set(os.listdir(fd))
            if ((expected is not None and names != expected)
                    or not names or len(names) > 129):
                raise ValueError("MAP02 private two-pass inventory invalid")
            def inspect_inventory():
                identities = []
                for name in sorted(names):
                    if name in ("", ".", "..") or "/" in name or "\\" in name:
                        raise ValueError("MAP02 private two-pass filename invalid")
                    state = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    if (not stat.S_ISREG(state.st_mode)
                            or state.st_uid != os.getuid()
                            or stat.S_IMODE(state.st_mode) != 0o600
                            or state.st_nlink != 1):
                        raise ValueError("MAP02 private two-pass file not owner-private")
                    identities.append((
                        name, state.st_dev, state.st_ino, state.st_uid,
                        state.st_mode, state.st_nlink, state.st_size,
                        state.st_mtime_ns, state.st_ctime_ns))
                return tuple(identities)

            # Stat every name twice through the SAME held directory FD.
            # A concurrent modification of a nonterminal GPU snapshot can
            # otherwise escape a one-pass stat inventory even if no bytes
            # are ultimately leaked into the digest-only report.
            identities = inspect_inventory()
            if inspect_inventory() != identities:
                raise ValueError("MAP02 private two-pass file identity changed during inventory")
            last = os.fstat(fd)
            routed = os.stat(path, follow_symlinks=False)
            def dir_id(info):
                return (info.st_dev, info.st_ino, info.st_mode,
                        info.st_mtime_ns, info.st_ctime_ns)
            if (dir_id(first) != dir_id(last)
                    or dir_id(first) != dir_id(routed)
                    or set(os.listdir(fd)) != names):
                raise ValueError("MAP02 private two-pass directory changed")
            witness.append((dir_id(first), identities))
        finally:
            os.close(fd)
    return tuple(witness)



def run(executable, output_dir, gpu_journal_dir, *, frame, executable_sha256,
        timeout=10, args=(), frame_pair_dir=None, native_capture_dir=None,
        source_capture_dir=None, launch_receipt=None, preflight_report=None,
        compiler="gcc"):
    """Run one pinned Linux ELF, then independently audit the same bytes twice.

    The output/journal directories must already exist, be empty, and have
    owner-private permissions. On failure, the launcher's fail-closed
    publication and the independent replay checks determine refusal.
    """
    # The four inputs form ONE all-or-nothing independent original-source
    # FT4/VRAM witness. A partial argument set must fail before executing
    # or publishing a native ELF frame.
    source_inputs = (native_capture_dir, source_capture_dir,
                     launch_receipt, preflight_report)
    source_requested = any(v is not None for v in source_inputs)
    if (compiler not in ("gcc", "clang")
            or (source_requested and
                (not all(v is not None for v in source_inputs)
                 or frame_pair_dir is None))):
        raise ValueError("MAP02 original FT4/VRAM witness arguments incomplete")
    if source_requested:
        _preflight_original_source_files(
            native_capture_dir, source_capture_dir,
            launch_receipt, preflight_report,
            output_dir, gpu_journal_dir, frame_pair_dir)
    # The optional claimed pair is independent of the same-launch frame.
    # Observe its inode inventory and exact claimed hashes BEFORE launching.
    # A comparison with an independently captured reference is informative
    # but never authenticates PS1 hardware or original retail assets.
    pair_witness = None
    pair_report = None
    if frame_pair_dir is not None:
        _require_owner_private_claimed_pair(frame_pair_dir)
        pair_witness = _private_frame_pair_identity(frame_pair_dir)
        pair_report = compare(frame_pair_dir)
        if (_private_frame_pair_identity(frame_pair_dir) != pair_witness
                or (pair_report["frame"], pair_report["width"],
                    pair_report["height"]) != (frame, WIDTH, HEIGHT)):
            raise ValueError("MAP02 private reference frame pair changed or has wrong labels")

    # A capture-success reply alone cannot pin a filesystem inode.
    # Take the inventory witness BEFORE the launcher's held directory FDs
    # close; a same-byte replacement before the first offline replay must
    # then fail even when all SHA-256 digests remain identical.
    publication_witness = []
    def pin_at_publication(held_output_fd, held_journal_fd):
        if held_journal_fd is None:
            raise ValueError("MAP02 joint publication lacks pinned GPU directory")
        publication_witness.append(_session_inode_witness(
            output_dir, gpu_journal_dir, held_output_fd=held_output_fd,
            held_journal_fd=held_journal_fd))

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
    claimed_pair = {}
    if frame_pair_dir is not None:
        _require_owner_private_claimed_pair(frame_pair_dir)
        # The two independent source claims are still only claims.
        # Preserve inode identity across launch/replays and require the
        # claimant candidate to be exactly the same raw BGR555 frame
        # that came from the pinned native Linux child stdout.
        after_pair = compare(frame_pair_dir)
        if (after_pair != pair_report
                or _private_frame_pair_identity(frame_pair_dir) != pair_witness):
            raise ValueError("MAP02 private reference frame pair changed during capture")
        if after_pair["candidate_sha256"] != first["image_sha256"]:
            raise ValueError("MAP02 claimed candidate differs from same-launch BGR555 frame")
        claimed_pair = {
            "claimed_reference_sha256": after_pair["reference_sha256"],
            "claimed_reference_difference_mask_sha256":
                after_pair["difference_mask_sha256"],
            "claimed_reference_different_bgr555_pixels":
                after_pair["different_bgr555_pixels"],
            "claimed_reference_changed_scanlines":
                after_pair["changed_scanlines"],
            "claimed_reference_stp_bit_differences":
                after_pair["stp_bit_differences"],
            "claimed_reference_exact_pixel_matches":
                after_pair["exact_bgr555_pixel_matches"],
            "claimed_reference_raw_bgr555_equal_to_live_candidate":
                after_pair["different_bgr555_pixels"] == 0,
            "claimed_reference_ps1_hardware_authenticated": False,
        }

    original_source = {}
    if source_requested:
        # Reuse the *existing independent* original-source native bridge:
        # it validates the separate original FT4/GTE/OT/VRAM evidence,
        # strict executable witness, claimed frame pair, and the live GPU
        # journal through two more full replays, not a caller-made summary.
        joined = join_original_native(
            frame_pair_dir, output_dir, native_capture_dir,
            source_capture_dir, launch_receipt=launch_receipt,
            preflight_report=preflight_report, executable=executable,
            compiler=compiler, gpu_journal_dir=gpu_journal_dir)
        if (type(joined) is not dict or joined.get("schema") !=
                "vh.map02.live-frame-claimed-pair-native-digest-join.v1"
                or joined.get("frame") != frame
                or (joined.get("width"), joined.get("height")) != (WIDTH, HEIGHT)
                or joined.get("candidate_sha256") != first["image_sha256"]
                or joined.get("claimed_reference_sha256")
                   != pair_report["reference_sha256"]
                or joined.get("same_launcher_gpu_journal_sha256")
                   != first["gpu_journal_sha256"]
                or joined.get("same_launcher_gpu_terminal_vram_sha256")
                   != first["terminal_gpu_after_vram_sha256"]
                or joined.get("same_launcher_gpu_journal_pairs_verified")
                   != first["gpu_journal_pairs_verified"]
                or joined.get("candidate_pixels_match_replayed_live_pipe") is not True
                or joined.get("native_gpu_trace_independently_replayed") is not True
                or joined.get("live_pipe_stable_during_native_replay") is not True
                or joined.get("child_writable_gpu_journal_fd_observed") is not True
                or joined.get("same_launcher_terminal_frame_equal_gpu_after_vram")
                   is not True
                or joined.get("same_process_gpu_event_and_frame_causality_authenticated")
                   is not False
                or joined.get("retail_disc_or_ps1_reference_authenticated") is not False
                or joined.get("gpu_journal_writer_kernel_authenticated") is not False
                or joined.get("hd_replacement_authorized") is not False):
            raise ValueError("MAP02 independent source witness disagrees with same-launch frame")
        # The extra independent source replay is not allowed to swap any
        # of the files the original launcher bound through its held FDs.
        if (_session_inode_witness(output_dir, gpu_journal_dir) != pinned_session
                or _private_frame_pair_identity(frame_pair_dir) != pair_witness
                or compare(frame_pair_dir) != pair_report):
            raise ValueError("MAP02 private capture changed during original FT4/VRAM witness")
        original_source = {
            "source_keyed_native_ft4_vram_independently_replayed": True,
            "source_original_launch_receipt_sha256":
                _require_source_sha256(joined, "original_launch_receipt_sha256"),
            "source_native_gpu_event_log_sha256":
                _require_source_sha256(joined, "native_gpu_event_log_sha256"),
            "source_original_trace_same_session_as_live_elf_authenticated": False,
        }

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
        **claimed_pair,
        **original_source,
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



def _require_source_sha256(report, key):
    """Fail closed on untrusted source-replay digest fields.

    The returned summary intentionally exposes only independently checked
    lowercase hex digests. Never relay an arbitrary private file path or
    untrusted string as if it were an SHA-256 commitment.
    """
    value = report.get(key) if type(report) is dict else None
    if (type(value) is not str or len(value) != 64
            or any(ch not in "0123456789abcdef" for ch in value)):
        raise ValueError("MAP02 independent source witness has invalid SHA-256 digest")
    return value


def _safe_cli_failure(exc):
    """Reveal a bounded reason, never a private file path from OSError/JSON.

    An exception can contain a caller's private full pathname (including
    os.open FileNotFoundError) or an untrusted source-witness string.
    Only recognized, path-free categories reach stdout/stderr.
    """
    if isinstance(exc, subprocess.TimeoutExpired):
        return "MAP02 private ELF execution timed out"
    if isinstance(exc, OSError):
        return "MAP02 private capture I/O failed"
    detail = str(exc)
    if "SHA-256 mismatch" in detail:
        return "MAP02 private SHA-256 mismatch"
    if "arguments incomplete" in detail:
        return "MAP02 original FT4/VRAM witness arguments incomplete"
    if "timed out" in detail:
        return "MAP02 private capture timed out"
    if "frame pair changed" in detail:
        return "MAP02 private claimed frame pair changed"
    if "replays disagree" in detail:
        return "MAP02 private GPU/frame replays disagree"
    return "MAP02 private capture validation failed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--executable-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--gpu-journal-dir", type=Path, required=True)
    parser.add_argument("--frame", type=int, required=True)
    parser.add_argument("--frame-pair-dir", type=Path)
    parser.add_argument("--native-capture", type=Path)
    parser.add_argument("--source-capture", type=Path)
    parser.add_argument("--launch-receipt", type=Path)
    parser.add_argument("--preflight-report", type=Path)
    parser.add_argument("--compiler", choices=("gcc", "clang"), default="gcc")
    parser.add_argument("--timeout", type=int, default=10)
    ns = parser.parse_args()
    try:
        report = run(
            ns.executable, ns.output_dir, ns.gpu_journal_dir,
            frame=ns.frame, executable_sha256=ns.executable_sha256,
            timeout=ns.timeout, frame_pair_dir=ns.frame_pair_dir,
            native_capture_dir=ns.native_capture,
            source_capture_dir=ns.source_capture,
            launch_receipt=ns.launch_receipt,
            preflight_report=ns.preflight_report, compiler=ns.compiler)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.error(_safe_cli_failure(exc))
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
