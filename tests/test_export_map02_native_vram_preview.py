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
        # Derive the synthetic baseline before intentionally introducing
        # a forbidden hardlink; the patched exporter must then reject it.
        original = verify_native_windows(self.fixture.root, target_frame=7)
        os.link(last, twin)
        self.addCleanup(twin.unlink)
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



class CycleBoundNativeVramPreviewTests(unittest.TestCase):
    """Fake v5 sealed cycle + independent synthetic native GPU windows."""

    def setUp(self):
        fixture = NativeGpuWindowEvidenceTests(
            methodName="test_small_one_window_is_not_mislabeled_as_complete_gameplay")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.output = root / "private-preview"
        self.cycle = root / "cycle-receipt"
        self.output.mkdir(mode=0o700)
        self.cycle.mkdir(mode=0o700)
        self.token = "ab" * 16
        self.fixture.status["capture_session"] = self.token
        self.fixture.save_status()
        self.event = {
            "schema": "vh.map02.cycle-order.v5",
            "capture_session": self.token,
            "gpu_draw_frame": 7,
            "original_cd_raw_user_crc32": "a" * 8,
            "original_cd_raw_user_sha256": "a" * 64,
            "observed_draw_primitive_count": 2,
            "display_source_rect": [0, 0, 1, 1],
            "present_backend_is_hires": False,
            "pc_present_call_returned": True,
            "ordered_source_hooks_observed": True,
            "cd_payload_verified_by_this_receipt": False,
            "original_map02_rendering_proven": False,
            "physical_ps1_equivalence_proven": False,
        }
        self.save_cycle()

    def save_cycle(self):
        raw = (json.dumps(self.event, sort_keys=True) + "\n").encode()
        for name in ("map02-single-process-cycle.jsonl",
                     "map02-cycle-clean-exit.jsonl"):
            path = self.cycle / name
            path.write_bytes(raw)
            path.chmod(0o600)

    def run_cycle(self, **kwargs):
        return export_native_vram_preview(
            self.fixture.root, self.output, frame=7,
            cycle_directory=self.cycle, **kwargs)

    def test_same_session_native_rectangle_outputs_private_png(self):
        report = self.run_cycle()
        png = (self.output / PNG_NAME).read_bytes()
        self.assertEqual(decoded_rows(png), ((1, 1), b"\x00\x10\x00\x00"))
        self.assertEqual(report["cropped_vram_rectangle"], [0, 0, 1, 1])
        self.assertEqual(report["verified_native_draw_pairs"], 2)
        self.assertTrue(report["cycle_and_native_gpu_draw_count_matched"])
        self.assertTrue(report["observed_native_present_source_rect_matched"])
        self.assertTrue(report["native_present_call_returned"])
        self.assertFalse(report["presented_framebuffer_verified"])
        self.assertFalse(report["original_map02_authenticated"])
        self.assertNotIn(self.token, json.dumps(report))
        self.assertNotIn(str(self.cycle), json.dumps(report))

    def test_hires_presentation_rejected_without_export(self):
        self.event["present_backend_is_hires"] = True
        self.save_cycle()
        with self.assertRaisesRegex(ValueError, "HiresPresent uses"):
            self.run_cycle()
        self.assertFalse((self.output / PNG_NAME).exists())

    def test_capture_session_mismatch_or_missing_nonce_rejected(self):
        self.event["capture_session"] = "ef" * 16
        self.save_cycle()
        with self.assertRaisesRegex(ValueError, "session or native GPU draw count"):
            self.run_cycle()
        self.event["capture_session"] = self.token
        self.save_cycle()
        del self.fixture.status["capture_session"]
        self.fixture.save_status()
        with self.assertRaisesRegex(ValueError, "session or native GPU draw count"):
            self.run_cycle()
        self.assertFalse((self.output / PNG_NAME).exists())

    def test_draw_count_mismatch_with_native_gpu_events_rejected(self):
        self.event["observed_draw_primitive_count"] = 3
        self.save_cycle()
        with self.assertRaisesRegex(ValueError, "draw count differs"):
            self.run_cycle()
        self.assertFalse((self.output / PNG_NAME).exists())

    def test_missing_or_invalid_present_claim_rejected(self):
        for change in (
            {"pc_present_call_returned": False},
            {"display_source_rect": [0, 0, 0, 1]},
            {"display_source_rect": [1023, 0, 2, 1]},
            {"gpu_draw_frame": 8},
        ):
            with self.subTest(change=change):
                before = dict(self.event)
                self.event.update(change)
                self.save_cycle()
                with self.assertRaises(ValueError):
                    self.run_cycle()
                self.event = before
        self.assertFalse((self.output / PNG_NAME).exists())

    def test_unsealed_or_modified_cycle_rejected_before_png(self):
        seal = self.cycle / "map02-cycle-clean-exit.jsonl"
        seal.write_bytes(b"foreign")
        with self.assertRaises(ValueError):
            self.run_cycle()
        self.assertFalse((self.output / PNG_NAME).exists())

    def test_cycle_changed_during_second_audit_rejected_before_png(self):
        from tools.verify_map02_cycle_cd_gpu_join import _cycle_receipt
        original = _cycle_receipt(self.cycle, 7)
        altered = (original[0] + b" ", original[1], original[2])
        with patch("tools.export_map02_native_vram_preview._cycle_receipt",
                   side_effect=(original, altered)):
            with self.assertRaisesRegex(ValueError, "changed during PNG preparation"):
                self.run_cycle()
        self.assertFalse((self.output / PNG_NAME).exists())

    def test_manual_crop_and_nested_output_refused(self):
        with self.assertRaisesRegex(ValueError, "selects its own"):
            self.run_cycle(x=1)
        child = self.cycle / "exported"
        child.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "directories must be separate"):
            export_native_vram_preview(self.fixture.root, child,
                                       frame=7, cycle_directory=self.cycle)
        self.assertFalse((self.output / PNG_NAME).exists())


if __name__ == "__main__":
    unittest.main()
