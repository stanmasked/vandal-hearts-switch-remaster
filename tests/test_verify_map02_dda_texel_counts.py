"""Asset-free, SHA-bound native FT4 DDA sample counter regressions."""
import hashlib
import json
import unittest

from test_verify_map02_native_gpu_capture import NativeGpuCaptureValidationTests
from tools.verify_map02_dda_texel_counts import verify_dda_counts


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class NativeDdaCountAuditTests(unittest.TestCase):
    def setUp(self):
        self.native = NativeGpuCaptureValidationTests("test_two_native_pairs_and_hashes")
        self.native.setUp()
        self.addCleanup(self.native.doCleanups)
        self.root = self.native.root
        self.rows = [self.row(0, 0, 17, 5, 68)]
        self.save()

    def row(self, step, ordinal, zero, stp, opaque):
        return {
            "stage": "native_dda_ft4_texel_counts",
            "step": step, "frame": 12, "primitive_ordinal": ordinal,
            "primitive_type": 2, "zero": zero, "stp": stp, "opaque": opaque,
        }

    def save(self):
        self.native.save()
        counts = b"".join(
            (json.dumps(row, sort_keys=True) + "\n").encode()
            for row in self.rows
        )
        (self.root / "native-dda-ft4-texel-counts.jsonl").write_bytes(counts)
        event_bytes = (self.root / "gpu-native-events.jsonl").read_bytes()
        manifest = {
            "schema": "vh.map02.native-dda-ft4-texel-counts.v1",
            "gpu_draw_frame": 12,
            "native_events_sha256": sha(event_bytes),
            "texel_counts_sha256": sha(counts),
        }
        (self.root / "native-dda-ft4-counts.json").write_text(
            json.dumps(manifest, sort_keys=True), encoding="utf-8"
        )

    def verify(self):
        return verify_dda_counts(self.root, target_frame=12)

    def test_correlates_after_transfer_using_draw_only_ordinal(self):
        report = self.verify()
        self.assertEqual(report["native_ft4_primitives_correlated"], 1)
        self.assertEqual(report["native_dda_bgr555_zero_samples"], 17)
        self.assertEqual(report["native_dda_nonzero_stp_samples"], 5)
        self.assertEqual(report["native_dda_nonzero_opaque_samples"], 68)
        self.assertEqual(report["native_ft4_primitives_without_dda_samples"], 0)
        self.assertTrue(report["all_sampling_decisions_in_original_dda"])
        self.assertFalse(report["primitive_pixel_write_count_inferred"])
        self.assertFalse(report["original_gameplay_authenticated"])
        for forbidden in ('"x"', '"y"', '"clut"', "31978", 'bgr555":', '"uv"'):
            self.assertNotIn(forbidden, json.dumps(report))

    def test_zero_samples_are_valid_for_fully_clipped_ft4(self):
        self.rows[0] = self.row(0, 0, 0, 0, 0)
        self.save()
        report = self.verify()
        self.assertEqual(report["native_ft4_primitives_without_dda_samples"], 1)
        self.assertEqual(report["native_dda_bgr555_zero_samples"], 0)

    def test_corrupted_hash_and_wrong_frame_refused(self):
        log = self.root / "native-dda-ft4-texel-counts.jsonl"
        log.write_bytes(log.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.verify()
        self.save()
        self.rows[0]["frame"] = 13
        self.save()
        with self.assertRaisesRegex(ValueError, "wrong GPU frame"):
            self.verify()

    def test_negative_counts_wrong_ordinal_and_type_rejected(self):
        for name, value, reason in [
            ("zero", -1, "expected integer"),
            ("stp", True, "expected integer"),
            ("opaque", 2**64, "expected integer"),
            ("primitive_ordinal", 1, "ordinal"),
            ("primitive_type", 3, "not an FT4"),
        ]:
            with self.subTest(name=name):
                previous = self.rows[0][name]
                self.rows[0][name] = value
                self.save()
                with self.assertRaisesRegex(ValueError, reason):
                    self.verify()
                self.rows[0][name] = previous

    def test_missing_or_record_cap_rejected(self):
        self.rows = []
        self.save()
        with self.assertRaisesRegex(ValueError, "empty|over size limit"):
            self.verify()
        self.rows = [self.row(i, 0, 0, 0, 0) for i in range(64)]
        self.save()
        with self.assertRaisesRegex(ValueError, "record cap|at cap"):
            self.verify()

    def test_non_native_ft4_primitive_cannot_be_correlated(self):
        self.native.events[2]["ft4"] = None
        self.native.events[3]["ft4"] = None
        # F4 is a real drawing packet that may modify VRAM but is not FT4.
        # DR_MODE (type 5) cannot modify VRAM: substituting it here would
        # fail an earlier, unrelated GPU-state integrity assertion.
        self.native.events[2]["primitive_type"] = 1
        self.native.events[3]["primitive_type"] = 1
        self.save()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
