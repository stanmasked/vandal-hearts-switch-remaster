#!/usr/bin/env python3
"""Independent replay of one private MAP02 Linux ELF BGR555 pipe receipt.

Checks original private bytes, fixed schema and current executable hash.
This is a byte/integrity audit, NOT authentication of which renderer wrote the
pixels, original game assets, PS1 video or a shared GPU-event process session.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from tools.capture_map02_live_frame_pipe import SCHEMA
from tools.compare_map02_private_bgr555_frames import _object_pairs

HEX64 = re.compile(r"[0-9a-f]{64}\Z")
IMAGE_NAME = "process-frame.bgr555"
RECEIPT_NAME = "process-frame.json"
RECEIPT_KEYS = frozenset((
    "schema", "frame", "width", "height", "pixel_format",
    "image_sha256", "executable_sha256",
    "kernel_observed_pinned_elf_before_stream",
    "child_stdout_pipe_frame_received",
    "retail_gameplay_authenticated",
    "ps1_reference_capture_authenticated",
    "native_renderer_origin_authenticated",
    "hd_replacement_authorized",
))
MAX_PIXELS = 1024 * 1024
MAX_BYTES = 2 * MAX_PIXELS
MAX_RECEIPT = 4096


def _identity(info):
    return tuple(getattr(info, key) for key in (
        "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"))


def _read_private_file(root, name, *, max_bytes, exact_bytes=None):
    path = root / name
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                 dir_fd=None)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode)
                or stat.S_IMODE(before.st_mode) != 0o600
                or not 0 < before.st_size <= max_bytes
                or (exact_bytes is not None and before.st_size != exact_bytes)):
            raise ValueError("MAP02 private live frame file size, type or mode invalid")
        chunks = []
        remaining = before.st_size
        while remaining:
            part = os.read(fd, min(65536, remaining))
            if not part:
                raise ValueError("MAP02 private live frame file truncated")
            chunks.append(part)
            remaining -= len(part)
        if (_identity(os.fstat(fd)) != _identity(before)
                or _identity(os.stat(path, follow_symlinks=False)) != _identity(before)):
            raise ValueError("MAP02 private live frame file changed during replay")
        return b"".join(chunks), _identity(before)
    finally:
        os.close(fd)


def _executable_sha(path):
    if path.is_symlink():
        raise ValueError("MAP02 executable cannot be a symlink")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or not before.st_mode & 0o111
                or not 0 < before.st_size <= 1024 * 1024 * 1024):
            raise ValueError("MAP02 executable has invalid file type/size/mode")
        dig = hashlib.sha256()
        count = 0
        while True:
            raw = os.read(fd, 65536)
            if not raw:
                break
            count += len(raw)
            dig.update(raw)
            if count > before.st_size:
                raise ValueError("MAP02 executable changed during replay")
        if (count != before.st_size
                or _identity(os.fstat(fd)) != _identity(before)
                or _identity(os.stat(path, follow_symlinks=False)) != _identity(before)):
            raise ValueError("MAP02 executable changed during replay")
        return dig.hexdigest()
    finally:
        os.close(fd)


def replay(directory, *, executable):
    root = Path(directory).absolute()
    if root.is_symlink():
        raise ValueError("MAP02 live frame directory is a symlink")
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        state = os.fstat(root_fd)
        if (not stat.S_ISDIR(state.st_mode)
                or stat.S_IMODE(state.st_mode) & 0o077):
            raise ValueError("MAP02 live frame directory must be owner-only")
        if set(os.listdir(root_fd)) != {IMAGE_NAME, RECEIPT_NAME}:
            raise ValueError("MAP02 live frame must have exact file inventory")
        raw_receipt, receipt_identity = _read_private_file(
            root, RECEIPT_NAME, max_bytes=MAX_RECEIPT)
        if (not raw_receipt.endswith(b"\n") or b"\r" in raw_receipt
                or b"\x00" in raw_receipt):
            raise ValueError("MAP02 live receipt is not canonical JSON")
        try:
            metadata = json.loads(raw_receipt.decode("utf-8"),
                                  object_pairs_hook=_object_pairs,
                                  parse_constant=lambda _: (_ for _ in ()).throw(
                                      ValueError("nonfinite JSON number")))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("MAP02 live receipt JSON invalid") from exc
        if type(metadata) is not dict or set(metadata) != RECEIPT_KEYS:
            raise ValueError("MAP02 live receipt schema/fields invalid")
        if (metadata["schema"] != SCHEMA
                or metadata["pixel_format"] != "bgr555_le"
                or type(metadata["frame"]) is not int
                or not 1 <= metadata["frame"] <= 0xffffffff
                or type(metadata["width"]) is not int
                or type(metadata["height"]) is not int
                or not 1 <= metadata["width"] <= 1024
                or not 1 <= metadata["height"] <= 1024
                or metadata["width"] * metadata["height"] > MAX_PIXELS):
            raise ValueError("MAP02 live frame metadata invalid")
        if (any(metadata[key] is not True for key in (
                    "kernel_observed_pinned_elf_before_stream",
                    "child_stdout_pipe_frame_received"))
                or any(metadata[key] is not False for key in (
                    "retail_gameplay_authenticated",
                    "ps1_reference_capture_authenticated",
                    "native_renderer_origin_authenticated",
                    "hd_replacement_authorized"))):
            raise ValueError("MAP02 live frame evidence flags invalid")
        if any(type(metadata[key]) is not str or not HEX64.fullmatch(metadata[key])
               for key in ("image_sha256", "executable_sha256")):
            raise ValueError("MAP02 live frame digest format invalid")
        # Enforce actual producer encoding, not a self-consistent altered JSON.
        if raw_receipt != (json.dumps(metadata, sort_keys=True) + "\n").encode():
            raise ValueError("MAP02 live frame receipt is not canonical encoding")

        expected_size = metadata["width"] * metadata["height"] * 2
        image, image_identity = _read_private_file(
            root, IMAGE_NAME, max_bytes=MAX_BYTES, exact_bytes=expected_size)
        image_hash = hashlib.sha256(image).hexdigest()
        if image_hash != metadata["image_sha256"]:
            raise ValueError("MAP02 live BGR555 image SHA-256 mismatch")
        binary_hash = _executable_sha(Path(executable).absolute())
        if binary_hash != metadata["executable_sha256"]:
            raise ValueError("MAP02 live executable SHA-256 mismatch")

        # Re-read and compare identities so a replaced receipt/image cannot
        # be accepted while an independent executable audit runs.
        recheck, same_receipt_identity = _read_private_file(
            root, RECEIPT_NAME, max_bytes=MAX_RECEIPT)
        second_image, same_image_identity = _read_private_file(
            root, IMAGE_NAME, max_bytes=MAX_BYTES, exact_bytes=expected_size)
        if (recheck != raw_receipt or same_receipt_identity != receipt_identity
                or second_image != image or same_image_identity != image_identity
                or _identity(os.fstat(root_fd)) != _identity(state)
                or set(os.listdir(root_fd)) != {IMAGE_NAME, RECEIPT_NAME}):
            raise ValueError("MAP02 live frame changed during independent replay")
        return {
            "schema": "vh.map02.live-child-pipe-replayed.v1",
            "frame": metadata["frame"],
            "width": metadata["width"],
            "height": metadata["height"],
            "image_sha256": image_hash,
            "executable_sha256": binary_hash,
            "receipt_sha256": hashlib.sha256(raw_receipt).hexdigest(),
            "private_frame_integrity_replayed": True,
            "pinned_executable_bytes_rechecked": True,
            "native_gpu_log_same_process_authenticated": False,
            "retail_disc_or_ps1_pixel_source_authenticated": False,
            "hd_replacement_authorized": False,
        }
    finally:
        os.close(root_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-frame", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = replay(args.live_frame, executable=args.executable)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
