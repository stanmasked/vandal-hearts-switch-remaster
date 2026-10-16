"""Synthetic private PutPixel staged-promotion tests; no real game content."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from tools.promote_map02_putpixel_stage import (
    promote_staged_putpixel, PENDING, MANIFEST, PIXEL_LOG, SCHEMA,
)


def as_line(value):
    return (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode()


class StagedPutPixelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / "source"
        self.native = root / "native"
        self.source.mkdir(mode=0o700)
        self.native.mkdir(mode=0o700)
        self.event = {
            "stage": "native_putpixel", "step": 0, "frame": 7,
            "primitive_ordinal": 0, "primitive_type": 4,
            "x": 20, "y": 40, "before": 31, "front": 31744,
            "after": 992, "abr": 0, "semi": 1, "textured": 1,
            "accurate": 1,
        }
        self.raw = as_line(self.event)
        (self.native / PENDING).write_bytes(self.raw)
        self.meta = {
            "schema": SCHEMA,
            "source_frame": 7,
            "gpu_draw_frame": 7,
            "overdraw_manifest_sha256": "0" * 64,
            "native_events_sha256": "1" * 64,
            "putpixel_events_sha256": hashlib.sha256(self.raw).hexdigest(),
        }
        self.save_manifest()
        self.patch = patch(
            "tools.promote_map02_putpixel_stage.verify_pixel_ot",
            return_value={"observed_native_putpixel_calls": 1})
        self.verifier = self.patch.start()
        self.addCleanup(self.patch.stop)

    def save_manifest(self):
        (self.source / MANIFEST).write_bytes(as_line(self.meta))

    def test_verified_publish_and_refuse_overwrite(self):
        report = promote_staged_putpixel(self.source, self.native)
        self.assertTrue(report["source_keyed_drawotag_vram_verified"])
        self.assertFalse(report["original_gameplay_authenticated"])
        self.verifier.assert_called_once()
        final = self.native / PIXEL_LOG
        self.assertEqual(final.read_bytes(), self.raw)
        self.assertEqual(stat.S_IMODE(final.stat().st_mode), 0o600)
        with self.assertRaises(ValueError):
            promote_staged_putpixel(self.source, self.native)

    def test_rejects_missing_newline_and_corrupted_digest(self):
        (self.native / PENDING).write_bytes(self.raw.rstrip(b"\n"))
        with self.assertRaises(ValueError):
            promote_staged_putpixel(self.source, self.native)
        self.meta["putpixel_events_sha256"] = hashlib.sha256(
            self.raw.rstrip(b"\n")).hexdigest()
        self.save_manifest()
        with self.assertRaises(ValueError):
            promote_staged_putpixel(self.source, self.native)
        self.assertFalse((self.native / PIXEL_LOG).exists())
        self.verifier.assert_not_called()

    def test_fail_closed_on_mismatched_step_or_fields(self):
        for bad in (dict(self.event, step=1),
                    dict(self.event, stage="native_blendg1"),
                    dict(self.event, primitive_type=257)):
            staged = as_line(bad)
            (self.native / PENDING).write_bytes(staged)
            self.meta["putpixel_events_sha256"] = hashlib.sha256(staged).hexdigest()
            self.save_manifest()
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                promote_staged_putpixel(self.source, self.native)
            self.assertFalse((self.native / PIXEL_LOG).exists())

    def test_rolls_back_failed_original_vram_verification(self):
        self.verifier.side_effect = ValueError("source-keyed VRAM mismatch")
        with self.assertRaisesRegex(ValueError, "source-keyed VRAM mismatch"):
            promote_staged_putpixel(self.source, self.native)
        self.assertFalse((self.native / PIXEL_LOG).exists())
        self.assertFalse(list(self.native.glob(".*.tmp")))

    def test_rejects_changed_input_after_verification(self):
        def mutate(*args, **kwargs):
            (self.native / PENDING).write_bytes(b"replacement\n")
            return {"observed_native_putpixel_calls": 1}
        self.verifier.side_effect = mutate
        with self.assertRaises(ValueError):
            promote_staged_putpixel(self.source, self.native)
        self.assertFalse((self.native / PIXEL_LOG).exists())

    def test_rejects_nonprivate_directory_and_symlink(self):
        os.chmod(self.native, 0o755)
        with self.assertRaises(ValueError):
            promote_staged_putpixel(self.source, self.native)
        os.chmod(self.native, 0o700)
        (self.native / PENDING).unlink()
        (self.native / PENDING).symlink_to(self.source / MANIFEST)
        with self.assertRaises(ValueError):
            promote_staged_putpixel(self.source, self.native)
        self.assertFalse((self.native / PIXEL_LOG).exists())


if __name__ == "__main__":
    unittest.main()
