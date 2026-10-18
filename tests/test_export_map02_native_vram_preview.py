"""Asset-free diagnostics for the bounded, private native GPU VRAM PNG export.

The integration fixture is synthetic and its GPU events are fabricated.
No original game image, screenshot or MAP02 rendering is supplied.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from tests.test_verify_map02_native_gpu_windows import NativeGpuWindowEvidenceTests
from tools.export_map02_native_vram_preview import (
    PNG_NAME, SIGNATURE, WIDTH, bgr555_png, export_native_vram_preview,
)
from tools.verify_map02_native_gpu_windows import verify_native_windows
from tools.verify_map02_vram_timeline import VRAM_BYTES


def decoded_rows(data):
    if not data.startswith(SIGNATURE):
        raise AssertionError("missing PNG signature")
    offset = len(SIGNATURE)
    dimensions = None
    pixels = bytearray()
    while offset < len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        chunk = data[offset + 8:offset + 8 + length]
        crc = struct.unpack_from(">I", data, offset + 8 + length)[0]
        if zlib.crc32(kind + chunk) & 0xffffffff != crc:
            raise AssertionError("invalid PNG chunk CRC")
        offset += length + 12
        if kind == b"IHDR":
            dimensions = struct.unpack_from(">II", chunk)
        elif kind == b"IDAT":
            pixels.extend(chunk)
        elif kind == b"IEND":
            break
    raw = zlib.decompress(pixels)
    return dimensions, raw


class VramPngConversionTests(unittest.TestCase):
    def test_converts_ps1_rgb555_and_ignores_stp_alpha_bit(self):
        raw = bytearray(VRAM_BYTES)
        # 0x801f: red plus PS1 STP, 0x03e0: green, 0x7c00: blue
        raw[0:4] = (0x801f).to_bytes(2, "little") + (0x03e0).to_bytes(2, "little")
        raw[WIDTH * 2:WIDTH * 2 + 2] = (0x7c00).to_bytes(2, "little")
        png = bgr555_png(raw, x=0, y=0, width=2, height=2)
        bounds, pixels = decoded_rows(png)
        self.assertEqual(bounds, (2, 2))
        self.assertEqual(pixels, (
            b"\x00\xff\x00\x00\x00\xff\x00" +
            b"\x00\x00\x00\xff\x00\x00\x00"))
        self.assertEqual(png[:8], SIGNATURE)

    def test_crop_matches_exact_native_memory_pixel(self):
        raw = bytearray(VRAM_BYTES)
        index = 2 * (7 * WIDTH + 19)
        raw[index:index+2] = (0x4210).to_bytes(2, "little")
        dim, pixels = decoded_rows(bgr555_png(raw, x=19, y=7, width=1, height=1))
        self.assertEqual(dim, (1, 1))
        self.assertEqual(pixels, b"\x00\x84\x84\x84")

    def test_rejects_invalid_bounds_and_wrong_vram_size(self):
        full = bytes(VRAM_BYTES)
        for kw in ({"x": -1}, {"y": 512}, {"width": 1025},
                   {"height": 0}, {"x": 1023, "width": 2},
                   {"y": 511, "height": 2}, {"width": True}):
            with self.subTest(crop=kw), self.assertRaises(ValueError):
                bgr555_png(full, **kw)
        with self.assertRaisesRegex(ValueError, "1 MiB"):
            bgr555_png(full[:-1])


class PrivateNativeVramPreviewTests(unittest.TestCase):
    def setUp(self):
        fixture = NativeGpuWindowEvidenceTests(
            methodName="test_small_one_window_is_not_mislabeled_as_complete_gameplay")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / "private"
        self.output.mkdir(mode=0o700)

    def run_preview(self):
        return export_native_vram_preview(
            self.fixture.root, self.output, frame=7, x=0, y=0,
            width=1, height=1)

    def test_verified_final_vram_renders_only_local_private_png(self):
        report = self.run_preview()
        path = self.output / PNG_NAME
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(report["gpu_draw_frame"], 7)
        self.assertEqual(report["cropped_vram_rectangle"], [0, 0, 1, 1])
        self.assertEqual(report["final_native_vram_sha256"],
                         hashlib.sha256(self.fixture.snapshots[-1]).hexdigest())
        self.assertEqual(report["private_png_sha256"],
                         hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertFalse(report["full_original_gameplay_frame_proven"])
        self.assertFalse(report["presented_framebuffer_verified"])
        self.assertFalse(report["private_game_bytes_uploaded"])
        self.assertEqual(decoded_rows(path.read_bytes()),
                         ((1, 1), b"\x00\x10\x00\x00"))
        self.assertNotIn(str(self.fixture.root), json.dumps(report))
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.run_preview()

    def test_wrong_final_hash_never_writes_png(self):
        original = verify_native_windows(self.fixture.root, target_frame=7)
        wrong = dict(original, final_native_vram_sha256="f" * 64)
        with patch("tools.export_map02_native_vram_preview.verify_native_windows",
                   return_value=wrong):
            with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
                self.run_preview()
        self.assertFalse((self.output / PNG_NAME).exists())

    def test_changed_gpu_capture_during_second_audit_never_writes(self):
        original = verify_native_windows(self.fixture.root, target_frame=7)
        changed = dict(original, native_draw_pairs=3)
        with patch("tools.export_map02_native_vram_preview.verify_native_windows",
                   side_effect=(original, changed)):
            with self.assertRaisesRegex(ValueError, "changed while preparing"):
                self.run_preview()
        self.assertFalse((self.output / PNG_NAME).exists())

    def test_file_hardlink_rejected_and_no_png_written(self):
        last = self.fixture.window / "gpu-0003-vram.bin"
        twin = Path(self.tmp.name) / "gpu-vram-hardlink.bin"
        os.link(last, twin)
        self.addCleanup(twin.unlink)
        original = verify_native_windows(self.fixture.root, target_frame=7)
        with patch("tools.export_map02_native_vram_preview.verify_native_windows",
                   return_value=original):
            with self.assertRaisesRegex(ValueError, "private regular"):
                self.run_preview()
        self.assertFalse((self.output / PNG_NAME).exists())

    def test_unprivate_output_or_inside_capture_rejected(self):
        self.output.chmod(0o755)
        with self.assertRaises(ValueError):
            self.run_preview()
        self.output.chmod(0o700)
        with self.assertRaisesRegex(ValueError, "separate"):
            export_native_vram_preview(self.fixture.root, self.fixture.root,
                                       frame=7, width=1, height=1)
        self.assertFalse((self.output / PNG_NAME).exists())


if __name__ == "__main__":
    unittest.main()
