"""Replay a private native MAP02 launch receipt against current raw capture bytes.

This is an integrity comparison, not a cryptographic signature, proof of the
game assets that were loaded, proof of physical PS1 GPU parity, or authorization
to replace textures. Does not launch the game or expose private pixels/paths.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

from tools.verify_map02_private_capture_session import verify_session, _unique_pairs

def _identity(path, *, max_bytes=None):
    """Read a private file from a no-follow fd and freeze its filesystem identity.

    This prevents accepting equal-bytes inode replacements while a receipt
    is being independently replayed. It is not process authentication.
    """
    path = Path(path)
    if path.is_symlink():
        raise ValueError("private replay input cannot be a symlink")
    # Nonblocking open is essential: a malicious FIFO substituted for a
    # private JSON file must fail as nonregular, not hang the audit.
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("private replay input must be a regular file")
        if before.st_size <= 0 or (max_bytes is not None and
                                   before.st_size > max_bytes):
            raise ValueError("private replay input has invalid size")
        if max_bytes is None:
            # Native binaries can be large; full SHA-256 verification is
            # already performed by verify_session(). Metadata here binds
            # the pathname and inode through that verification.
            content = None
        else:
            content = handle.read(max_bytes + 1)
        after = os.fstat(handle.fileno())
    current = os.stat(path, follow_symlinks=False)
    keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, key) != getattr(after, key)
           or getattr(before, key) != getattr(current, key)
           for key in keys):
        raise ValueError("private replay input changed during inspection")
    if not stat.S_ISREG(current.st_mode):
        raise ValueError("private replay input replaced by a nonregular file")
    if content is not None and len(content) != before.st_size:
        raise ValueError("private replay input changed while reading")
    return (tuple(getattr(before, key) for key in keys),
            hashlib.sha256(content).hexdigest() if content is not None else None,
            content)


def _inputs(receipt_file, preflight_report, executable):
    # Keep all identities private: no paths, per-file hashes or stat values
    # escape into the public result.
    return (
        _identity(receipt_file, max_bytes=16384),
        _identity(preflight_report, max_bytes=4096),
        _identity(executable),
    )


RECEIPT_KEYS = frozenset((
    "schema", "capture_frame", "executable_sha256", "preflight_created",
    "process_started", "process_exit_code", "capture_verified",
    "verification", "failure_category", "retail_map02_verified",
    "hd_replacement_authorized",
))


def replay_receipt(directory, *, receipt_file, preflight_report, executable):
    identities_before = _inputs(receipt_file, preflight_report, executable)
    raw = identities_before[0][2]
    if b"\x00" in raw:
        raise ValueError("invalid private receipt size")
    try:
        receipt = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (UnicodeError, ValueError) as exc:
        raise ValueError("malformed original process receipt") from exc
    if type(receipt) is not dict or receipt.keys() != RECEIPT_KEYS:
        raise ValueError("wrong original process receipt schema")
    if receipt["schema"] != "map02_private_native_process_receipt_v1":
        raise ValueError("unsupported original receipt version")
    if (receipt["preflight_created"] is not True
            or receipt["process_started"] is not True
            or type(receipt["process_exit_code"]) is not int
            or receipt["process_exit_code"] != 0
            or receipt["capture_verified"] is not True
            or receipt["failure_category"] is not None
            or receipt["retail_map02_verified"] is not False
            or receipt["hd_replacement_authorized"] is not False):
        raise ValueError("original process did not have a valid completed capture")
    frame = receipt["capture_frame"]
    if type(frame) is not int or not 1 <= frame <= 0xffffffff:
        raise ValueError("invalid frame in original process receipt")
    if type(receipt["executable_sha256"]) is not str:
        raise ValueError("invalid executable fingerprint in original receipt")
    current = verify_session(directory, native_frame=frame,
                             preflight_report=preflight_report,
                             executable=executable)
    if current["executable_sha256"] != receipt["executable_sha256"]:
        raise ValueError("process receipt executable SHA-256 changed")
    if type(receipt["verification"]) is not dict or current != receipt["verification"]:
        raise ValueError("private GPU DDA VRAM evidence no longer matches process receipt")
    if _inputs(receipt_file, preflight_report, executable) != identities_before:
        raise ValueError("private launcher receipt, preflight or executable changed during replay")
    return {
        "schema": "map02_private_capture_receipt_replay_v1",
        "original_receipt_sha256": hashlib.sha256(raw).hexdigest(),
        "frame": frame,
        "native_gpu_event_log_sha256":
            current["native_gpu_binding"]["gpu_events_sha256"],
        "native_gpu_pairs_verified": current["native_gpu_pairs_verified"],
        "draw_boundary_vram_checks": current["draw_boundary_vram_checks"],
        "draw_boundary_gpu_state_checks": current["draw_boundary_gpu_state_checks"],
        "move_pairs_with_verified_vram_effect":
            current["move_pairs_with_verified_vram_effect"],
        "clear_pairs_with_verified_vram_effect":
            current["clear_pairs_with_verified_vram_effect"],
        "vram_snapshot_sha256_list_sha256":
            current["vram_snapshot_sha256_list_sha256"],
        "dda_observation_mode": current["dda_observation_mode"],
        "raw_evidence_matches_original_receipt": True,
        "original_game_assets_authenticated": False,
        "ps1_or_switch_rendering_verified": False,
        "hd_replacement_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_capture_directory", type=Path)
    parser.add_argument("--receipt-file", required=True, type=Path)
    parser.add_argument("--preflight-report", required=True, type=Path)
    parser.add_argument("--executable", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = replay_receipt(args.private_capture_directory,
                                receipt_file=args.receipt_file,
                                preflight_report=args.preflight_report,
                                executable=args.executable)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
