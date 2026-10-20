#!/usr/bin/env python3
"""Export a PRIVATE diagnostic PNG from a fully audited native GPU VRAM endpoint.

This is the 1024x512 PC BGR555 VRAM memory plane (or an explicitly selected
rectangle), NOT the presented game framebuffer and NOT authenticated MAP02
artwork. The caller supplies private existing input/output directories.
Only a local owner-private PNG is created, never any public CI artifact.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import zlib

from tools.publish_map02_blendg1_witness import _private_directory
from tools.verify_map02_cycle_cd_gpu_join import CYCLE_RECEIPT, _cycle_receipt
from tools.verify_map02_frame_bundle import number, parse_json
from tools.verify_map02_native_gpu_windows import verify_native_windows
from tools.verify_map02_vram_timeline import VRAM_BYTES

WIDTH, HEIGHT = 1024, 512
PNG_NAME = "map02-native-vram-preview.png"
SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _stable_identity(info):
    # Output file size and timestamps change as expected while writing;
    # this identity is deliberately stable across those legitimate changes.
    return (info.st_dev, info.st_ino, info.st_uid, info.st_mode,
            info.st_nlink)


def _read_original_snapshot(path):
    """Pin pathname and descriptor; reject hardlinks, writes and inode swaps."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise ValueError("private MAP02 VRAM endpoint unavailable") from None
    try:
        before = os.fstat(fd)
        original = _identity(before)
        if (not stat.S_ISREG(before.st_mode) or
                before.st_uid != os.geteuid() or before.st_nlink != 1 or
                stat.S_IMODE(before.st_mode) & 0o022 or
                before.st_size != VRAM_BYTES):
            raise ValueError("MAP02 VRAM endpoint must be a private regular 1-MiB inode")
        raw = os.pread(fd, VRAM_BYTES, 0)
        if len(raw) != VRAM_BYTES or os.pread(fd, VRAM_BYTES, 0) != raw:
            raise ValueError("MAP02 VRAM endpoint bytes changed between reads")
        if (_identity(os.fstat(fd)) != original or
                _identity(os.stat(path, follow_symlinks=False)) != original):
            raise ValueError("MAP02 VRAM endpoint identity changed during read")
        return raw, original
    except OSError:
        raise ValueError("private MAP02 VRAM endpoint verification unavailable") from None
    finally:
        os.close(fd)


def _chunk(kind, raw):
    return (struct.pack(">I", len(raw)) + kind + raw +
            struct.pack(">I", zlib.crc32(kind + raw) & 0xffffffff))


def bgr555_png(vram, *, x=0, y=0, width=WIDTH, height=HEIGHT):
    """Convert little-endian PS1/PC BGR555 words to 8-bit RGB PNG.

    Native pixel bit 15 is STP/semi-transparency, not display alpha.
    It is intentionally ignored by this diagnostic, not composited.
    """
    if len(vram) != VRAM_BYTES:
        raise ValueError("expected exactly 1 MiB of original native VRAM")
    x = number(x, "VRAM crop x", 0, WIDTH - 1)
    y = number(y, "VRAM crop y", 0, HEIGHT - 1)
    width = number(width, "VRAM crop width", 1, WIDTH)
    height = number(height, "VRAM crop height", 1, HEIGHT)
    if x + width > WIDTH or y + height > HEIGHT:
        raise ValueError("VRAM preview rectangle exceeds native memory bounds")
    uncompressed = bytearray()
    for row in range(y, y + height):
        uncompressed.append(0)  # PNG filter NONE
        for col in range(x, x + width):
            off = 2 * (row * WIDTH + col)
            pixel = vram[off] | (vram[off + 1] << 8)
            r = pixel & 31
            g = (pixel >> 5) & 31
            b = (pixel >> 10) & 31
            uncompressed.extend(((r << 3) | (r >> 2),
                                 (g << 3) | (g >> 2),
                                 (b << 3) | (b >> 2)))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (SIGNATURE + _chunk(b"IHDR", header) +
            _chunk(b"IDAT", zlib.compress(uncompressed, 9)) +
            _chunk(b"IEND", b""))


def export_native_vram_preview(capture_directory, output_directory, *,
                               frame, x=0, y=0, width=WIDTH, height=HEIGHT,
                               cycle_directory=None):
    # Do not write inside the capture tree: it is an exact-file-set witness.
    capture = _private_directory(capture_directory)
    output = _private_directory(output_directory)
    if (capture.resolve() == output.resolve() or
            capture.resolve() in output.resolve().parents or
            output.resolve() in capture.resolve().parents):
        raise ValueError("MAP02 preview output must be a separate private directory")
    destination = output / PNG_NAME
    if destination.exists() or destination.is_symlink():
        raise ValueError("refusing to overwrite existing private VRAM preview")
    frame = number(frame, "selected native GPU frame", 1, 2**32 - 1)
    cycle = None
    cycle_proof = None
    cycle_event = None
    if cycle_directory is not None:
        cycle = _private_directory(cycle_directory)
        # All three directories must remain disjoint: the native verifier
        # requires exact capture-file membership; the cycle receipt is sealed.
        roots = (capture.resolve(), output.resolve(), cycle.resolve())
        if any(a == b or a in b.parents or b in a.parents
               for i, a in enumerate(roots) for b in roots[i + 1:]):
            raise ValueError("MAP02 cycle, native GPU and preview directories must be separate")
        if (x, y, width, height) != (0, 0, WIDTH, HEIGHT):
            raise ValueError("cycle-bound VRAM preview selects its own verified display rectangle")
        cycle_proof = _cycle_receipt(cycle, frame)
        cycle_event = parse_json(cycle_proof[0][:-1], CYCLE_RECEIPT)
        if cycle_event["present_backend_is_hires"]:
            raise ValueError("HiresPresent uses a separate framebuffer, not native VRAM")
        x, y, width, height = cycle_event["display_source_rect"]

    # This audit checks every before/after snapshot, transfer, frame, event,
    # capture counter, upload, and the continuity across GPU windows.
    first = verify_native_windows(capture, target_frame=frame)
    if cycle_event is not None:
        if (first["capture_session_sha256"] != cycle_proof[1] or
                first["native_draw_pairs"] !=
                cycle_event["observed_draw_primitive_count"]):
            raise ValueError("MAP02 cycle session or native GPU draw count differs")
    count = first["globally_ordered_native_gpu_events"]
    idx = (count - 1) // 64
    local = (count - 1) % 64
    endpoint = (capture / f"window-{idx:03d}" /
                f"gpu-{local:04d}-vram.bin")
    raw, pinned = _read_original_snapshot(endpoint)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != first["final_native_vram_sha256"]:
        raise ValueError("final native GPU VRAM endpoint SHA-256 differs")
    # Verify all original evidence again after reading the selected endpoint.
    if (verify_native_windows(capture, target_frame=frame) != first or
            _read_original_snapshot(endpoint) != (raw, pinned)):
        raise ValueError("native GPU capture changed while preparing VRAM preview")
    # Verify sealed cycle bytes AND both distinct inode identities again
    # before any output file can be created. An internally consistent,
    # synthetic cycle alone does not authenticate a retail scene.
    if cycle is not None and _cycle_receipt(cycle, frame) != cycle_proof:
        raise ValueError("MAP02 cycle receipt changed during PNG preparation")
    png = bgr555_png(raw, x=x, y=y, width=width, height=height)

    # Never overwrite, never follow a final symlink, and never remove a
    # concurrent foreign replacement. The directory itself must be pinned.
    dfd = os.open(output, os.O_RDONLY | os.O_DIRECTORY |
                  os.O_NOFOLLOW | os.O_CLOEXEC)
    fd = -1
    created = None
    try:
        dir_id = _stable_identity(os.fstat(dfd))
        if (_stable_identity(os.stat(output, follow_symlinks=False)) != dir_id or
                os.fstat(dfd).st_uid != os.geteuid() or
                stat.S_IMODE(os.fstat(dfd).st_mode) != 0o700):
            raise ValueError("private VRAM preview output directory changed")
        fd = os.open(PNG_NAME, os.O_RDWR | os.O_CREAT | os.O_EXCL |
                     os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dfd)
        os.fchmod(fd, 0o600)
        created = _stable_identity(os.fstat(fd))
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(png)
            stream.flush()
        os.fsync(fd)
        if (_stable_identity(os.fstat(fd)) != created or
                os.fstat(fd).st_size != len(png) or
                os.pread(fd, len(png), 0) != png or
                _stable_identity(os.stat(PNG_NAME, dir_fd=dfd,
                                         follow_symlinks=False)) != created or
                _stable_identity(os.stat(output, follow_symlinks=False)) != dir_id):
            raise ValueError("private VRAM preview output identity changed")
        os.fsync(dfd)
    except BaseException:
        if fd >= 0 and created is not None:
            try:
                if (_stable_identity(os.stat(PNG_NAME, dir_fd=dfd,
                                             follow_symlinks=False)) == created):
                    os.unlink(PNG_NAME, dir_fd=dfd)
            except OSError:
                pass
        raise
    finally:
        if fd >= 0:
            os.close(fd)
        os.close(dfd)
    result = {
        "schema": "vh.map02.native-vram-preview.v1",
        "gpu_draw_frame": frame,
        "final_native_vram_sha256": digest,
        "private_png_sha256": hashlib.sha256(png).hexdigest(),
        "cropped_vram_rectangle": [x, y, width, height],
        "full_original_gameplay_frame_proven": False,
        "presented_framebuffer_verified": False,
        "private_game_bytes_uploaded": False,
    }
    if cycle_event is not None:
        result.update({
            "schema": "vh.map02.cycle-bound-native-vram-preview.v1",
            "cycle_receipt_sha256": hashlib.sha256(cycle_proof[0]).hexdigest(),
            "capture_session_sha256": cycle_proof[1],
            "cycle_and_native_gpu_draw_count_matched": True,
            "verified_native_draw_pairs": first["native_draw_pairs"],
            "observed_native_present_source_rect_matched": True,
            "native_present_call_returned": True,
            "original_map02_authenticated": False,
        })
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_native_gpu_windows", type=Path)
    p.add_argument("existing_private_output_directory", type=Path)
    p.add_argument("--frame", type=int, required=True)
    p.add_argument("--cycle-directory", type=Path, default=None,
                   help="require same-session v5 clean-exit receipt; reject hi-res and use observed native display rectangle")
    p.add_argument("--x", type=int, default=0)
    p.add_argument("--y", type=int, default=0)
    p.add_argument("--width", type=int, default=WIDTH)
    p.add_argument("--height", type=int, default=HEIGHT)
    args = p.parse_args()
    try:
        report = export_native_vram_preview(
            args.private_native_gpu_windows,
            args.existing_private_output_directory, frame=args.frame,
            x=args.x, y=args.y, width=args.width, height=args.height,
            cycle_directory=args.cycle_directory)
    except (OSError, ValueError):
        p.error("private MAP02 native VRAM preview verification failed")
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
