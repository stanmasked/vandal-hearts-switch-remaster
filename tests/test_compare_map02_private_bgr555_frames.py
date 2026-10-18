"""Synthetic private MAP02 BGR555 frame differential tests; no game assets."""
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tools import compare_map02_private_bgr555_frames as diff


class PrivateBgr555FramesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vh-map02-fake-frame-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.width, self.height, self.frame = 4, 3, 77
        self.ref = [0] * (self.width * self.height)
        self.cand = list(self.ref)
        self.write()

    def write(self):
        def encode(words):
            return struct.pack("<" + "H" * len(words), *words)
        a, b = encode(self.ref), encode(self.cand)
        (self.folder / "reference.bgr555").write_bytes(a)
        (self.folder / "candidate.bgr555").write_bytes(b)
        self.meta = {
            "schema": diff.SCHEMA,
            "frame": self.frame,
            "width": self.width, "height": self.height,
            "pixel_format": "bgr555_le",
            "images": {
                "reference.bgr555": {
                    "sha256": hashlib.sha256(a).hexdigest(),
                    "frame": self.frame,
                    "origin": "ps1_reference_claimed"},
                "candidate.bgr555": {
                    "sha256": hashlib.sha256(b).hexdigest(),
                    "frame": self.frame,
                    "origin": "pc_port_candidate_claimed"},
            },
        }
        self.save_meta()

    def save_meta(self):
        (self.folder / "frames.json").write_text(
            json.dumps(self.meta, sort_keys=True), encoding="utf-8")

    def test_identical_frames_only_prove_byte_equality(self):
        out = diff.compare(self.folder)
        self.assertEqual(out["pixel_count"], 12)
        self.assertEqual(out["exact_bgr555_pixel_matches"], 12)
        self.assertEqual(out["different_bgr555_pixels"], 0)
        self.assertEqual(out["changed_16x16_blocks"], 0)
        self.assertEqual(out["changed_scanlines"], 0)
        self.assertEqual(out["sum_absolute_bgr5_channel_error"], 0)
        self.assertEqual(out["stp_bit_differences"], 0)
        self.assertEqual(len(out["difference_mask_sha256"]), 64)
        self.assertFalse(out["capture_source_authenticated"])
        self.assertFalse(out["ps1_hardware_pixel_equivalence_verified"])
        self.assertFalse(out["hd_replacement_authorized"])
        text = json.dumps(out)
        self.assertNotIn(str(self.folder), text)
        self.assertNotIn("reference.bgr555", text)

    def test_two_differences_channel_error_and_stp_are_exact(self):
        self.cand[5] = 0x7fff
        self.cand[6] = 0x8000
        self.write()
        out = diff.compare(self.folder)
        self.assertEqual(out["different_bgr555_pixels"], 2)
        self.assertEqual(out["exact_bgr555_pixel_matches"], 10)
        self.assertEqual(out["changed_scanlines"], 1)
        self.assertEqual(out["changed_16x16_blocks"], 1)
        self.assertEqual(out["stp_bit_differences"], 1)
        self.assertEqual(out["sum_absolute_bgr5_channel_error"], 93)
        self.assertEqual(out["maximum_bgr5_pixel_channel_error"], 93)

    def test_difference_mask_changes_even_when_changed_count_same(self):
        self.cand[0] = 1
        self.write()
        left = diff.compare(self.folder)
        self.cand[0], self.cand[11] = 0, 1
        self.write()
        right = diff.compare(self.folder)
        self.assertEqual(left["different_bgr555_pixels"],
                         right["different_bgr555_pixels"])
        self.assertNotEqual(left["difference_mask_sha256"],
                            right["difference_mask_sha256"])

    def test_frame_candidate_hash_mismatch_fails(self):
        (self.folder / "candidate.bgr555").write_bytes(b"\x00\x80" * 12)
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            diff.compare(self.folder)

    def test_candidate_wrong_frame_fails(self):
        self.meta["images"]["candidate.bgr555"]["frame"] += 1
        self.save_meta()
        with self.assertRaisesRegex(ValueError, "identity/hash metadata"):
            diff.compare(self.folder)

    def test_reference_label_is_only_a_claim(self):
        self.meta["images"]["reference.bgr555"]["origin"] = "proven_retail_ps1"
        self.save_meta()
        with self.assertRaisesRegex(ValueError, "identity/hash metadata"):
            diff.compare(self.folder)

    def test_invalid_dimensions_and_booleans_fail(self):
        for bad in (True, -1, 0, 1025):
            self.meta["width"] = bad
            self.save_meta()
            with self.assertRaisesRegex(ValueError, "dimensions invalid"):
                diff.compare(self.folder)
        self.meta["width"] = self.width
        self.meta["frame"] = False
        self.save_meta()
        with self.assertRaisesRegex(ValueError, "identifier invalid"):
            diff.compare(self.folder)

    def test_extra_manifest_field_fails(self):
        self.meta["retail_ps1_frame_verified"] = True
        self.save_meta()
        with self.assertRaisesRegex(ValueError, "metadata fields invalid"):
            diff.compare(self.folder)

    def test_duplicate_json_keys_fail(self):
        (self.folder / "frames.json").write_bytes(
            b'{"schema":"a","schema":"b"}')
        with self.assertRaisesRegex(ValueError, "duplicate keys"):
            diff.compare(self.folder)

    def test_truncated_frame_refused(self):
        (self.folder / "reference.bgr555").write_bytes(b"\x00" * 2)
        with self.assertRaisesRegex(ValueError, "size or type invalid"):
            diff.compare(self.folder)

    def test_symlink_frame_or_manifest_refused(self):
        path = self.folder / "candidate.bgr555"
        displaced = self.folder / "moved"
        path.rename(displaced)
        path.symlink_to(displaced)
        with self.assertRaisesRegex(ValueError, "symlink"):
            diff.compare(self.folder)
        path.unlink()
        displaced.rename(path)
        path = self.folder / "frames.json"
        displaced = self.folder / "manifest-backup"
        path.rename(displaced)
        path.symlink_to(displaced)
        with self.assertRaisesRegex(ValueError, "symlink"):
            diff.compare(self.folder)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO required")
    def test_fifo_substitution_refused_without_blocking(self):
        path = self.folder / "reference.bgr555"
        path.unlink()
        os.mkfifo(path)
        with self.assertRaisesRegex(ValueError, "size or type invalid"):
            diff.compare(self.folder)

    def test_manifest_after_snapshot_change_is_detected_next_run(self):
        first = diff.compare(self.folder)
        self.meta["frame"] += 1
        for name in diff.FILE_NAMES:
            self.meta["images"][name]["frame"] = self.meta["frame"]
        self.save_meta()
        second = diff.compare(self.folder)
        self.assertNotEqual(first["manifest_sha256"],
                            second["manifest_sha256"])
        self.assertEqual(second["frame"], 78)

    def test_private_frame_directory_symlink_refused(self):
        alias = self.folder.parent / (self.folder.name + "-alias")
        alias.symlink_to(self.folder)
        self.addCleanup(alias.unlink)
        with self.assertRaisesRegex(ValueError, "symlink"):
            diff.compare(alias)


if __name__ == "__main__":
    unittest.main()
