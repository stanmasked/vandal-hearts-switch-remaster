"""Synthetic private witness publication regressions; no game assets."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.publish_map02_blendg1_witness import (
    publish_blendg1_witness, MANIFEST, LOG, STAGED_LOG, PIXEL_LOG,
    PIXEL_MANIFEST, SCHEMA, PIXEL_SCHEMA,
)


def _line(row):
    return (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()


def fixture(root):
    source = root / "source"
    native = root / "native"
    source.mkdir(mode=0o700)
    native.mkdir(mode=0o700)
    pixel = {
        "stage": "native_putpixel", "step": 0, "frame": 7,
        "primitive_ordinal": 2, "primitive_type": 4, "x": 20, "y": 40,
        "before": 31, "front": 31744, "after": 992, "abr": 0,
        "semi": 1, "textured": 1, "accurate": 1,
    }
    blend = {
        "stage": "native_blendg1", "putpixel_step": 0,
        "frame": pixel["frame"], "primitive_ordinal": 2,
        "primitive_type": 4, "x": 20, "y": 40,
        "accurate": 1, "abr": 0, "before": 31,
        "front": 31744, "after": 992,
        "blend_fg": 64512, "blend_bg": 31, "blend_result": 992,
    }
    pixel_raw = _line(pixel)
    (native / PIXEL_LOG).write_bytes(pixel_raw)
    (native / STAGED_LOG).write_bytes(_line(blend))
    pixel_meta = {
        "schema": PIXEL_SCHEMA,
        "putpixel_events_sha256": hashlib.sha256(pixel_raw).hexdigest(),
    }
    (source / PIXEL_MANIFEST).write_bytes(_line(pixel_meta))
    return source, native, pixel, blend


class PrivateWitnessPublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source, self.native, self.pixel, self.blend = fixture(
            Path(self.tmp.name))
        self.verification = patch(
            "tools.publish_map02_blendg1_witness.verify_pixel_ot",
            return_value={"observed_native_putpixel_calls": 1})
        self.mock_verify = self.verification.start()
        self.addCleanup(self.verification.stop)

    def test_exclusive_sha_bound_publish_and_retry_denied(self):
        result = publish_blendg1_witness(self.source, self.native)
        self.assertEqual(result["blendg1_events"], 1)
        self.assertFalse(result["original_gameplay_authenticated"])
        self.assertEqual(self.mock_verify.call_count, 1)
        manifest_raw = (self.source / MANIFEST).read_bytes()
        m = json.loads(manifest_raw)
        self.assertEqual(m["schema"], SCHEMA)
        self.assertEqual(m["pixel_ot_manifest_sha256"], hashlib.sha256(
            (self.source / PIXEL_MANIFEST).read_bytes()).hexdigest())
        self.assertEqual(m["blendg1_events_sha256"], hashlib.sha256(
            (self.native / LOG).read_bytes()).hexdigest())
        self.assertEqual((self.native / LOG).read_bytes(),
                         (self.native / STAGED_LOG).read_bytes())
        self.assertEqual((self.source / MANIFEST).stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.native / LOG).stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            publish_blendg1_witness(self.source, self.native)

    def test_rejects_tampered_staged_blend_and_preserves_absence(self):
        altered = dict(self.blend, blend_fg=0)
        (self.native / STAGED_LOG).write_bytes(_line(altered))
        with self.assertRaises(ValueError):
            publish_blendg1_witness(self.source, self.native)
        self.assertFalse((self.source / MANIFEST).exists())
        self.assertFalse((self.native / LOG).exists())
        self.mock_verify.assert_not_called()

    def test_rejects_noncanonical_staged_line_endings(self):
        staged = self.native / STAGED_LOG
        original = staged.read_bytes()
        for damaged in (original.rstrip(b"\n"),
                        original.replace(b"\n", b"\r\n"),
                        original + b"\n"):
            staged.write_bytes(damaged)
            with self.subTest(damaged=damaged[-12:]), self.assertRaises(ValueError):
                publish_blendg1_witness(self.source, self.native)
            self.assertFalse((self.source / MANIFEST).exists())
            self.assertFalse((self.native / LOG).exists())
        self.mock_verify.assert_not_called()

    def test_rejects_stale_pixel_digest_before_publication(self):
        (self.native / PIXEL_LOG).write_bytes(_line(dict(self.pixel, abr=3)))
        with self.assertRaises(ValueError):
            publish_blendg1_witness(self.source, self.native)
        self.assertFalse((self.source / MANIFEST).exists())

    def test_rejects_unverified_native_evidence(self):
        self.mock_verify.side_effect = ValueError("VRAM mismatch")
        with self.assertRaisesRegex(ValueError, "VRAM mismatch"):
            publish_blendg1_witness(self.source, self.native)
        self.assertFalse((self.native / LOG).exists())
        self.assertFalse((self.source / MANIFEST).exists())

    def test_private_directory_and_symlink_requirements(self):
        os.chmod(self.native, 0o755)
        with self.assertRaises(ValueError):
            publish_blendg1_witness(self.source, self.native)
        os.chmod(self.native, 0o700)
        (self.native / STAGED_LOG).unlink()
        (self.native / STAGED_LOG).symlink_to(self.native / PIXEL_LOG)
        with self.assertRaises(ValueError):
            publish_blendg1_witness(self.source, self.native)

    def test_failed_manifest_publish_does_not_leave_final_log(self):
        actual_link = os.link
        calls = [0]

        def fail_second(src, dst):
            calls[0] += 1
            if calls[0] == 2:
                raise OSError("simulated manifest publication failure")
            return actual_link(src, dst)

        with patch("tools.publish_map02_blendg1_witness.os.link",
                   side_effect=fail_second):
            with self.assertRaises(OSError):
                publish_blendg1_witness(self.source, self.native)
        self.assertFalse((self.native / LOG).exists())
        self.assertFalse((self.source / MANIFEST).exists())
        self.assertFalse(list(self.native.glob(".*.tmp")))
        self.assertFalse(list(self.source.glob(".*.tmp")))


if __name__ == "__main__":
    unittest.main()
