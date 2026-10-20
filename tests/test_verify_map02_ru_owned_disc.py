"""Asset-free tests for owned RU disc verification: no original 665MB disc required."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_check_map02_ru_receipt import fixture as receipt_fixture
from tools.check_map02_ru_receipt import EXPECTED_HASHES
from tools.verify_map02_ru_owned_disc import (
    PRS_BYTES, SECTOR_COUNT, DAT_SECTOR_COUNT, EXPECTED_DISC_BYTES,
    _readonly_disc_digest, _validate_audit, verify_owned_ru_disc,
)


def audit_fixture():
    return {
        "matches_prior_logical_compressed_sha256": True,
        "matches_prior_padded_compressed_sha256": True,
        "matches_prior_decompressed_sha256": True,
        "matches_prior_target_gfx": True,
        "compressed_logical_sha256": EXPECTED_HASHES["prs_logical"],
        "compressed_padded_sha256": EXPECTED_HASHES["prs_file"],
        "decompressed_sha256": EXPECTED_HASHES["prs_unpacked"],
        "compressed_byte_count": 22779,
        "logical_prs_byte_count": PRS_BYTES,
        "available_bytes": PRS_BYTES,
        "dat_comparison": {
            "matches_prior_dat_sha256": True,
            "matches_prior_disc_audit": True,
            "matches_prior_disc_audit_with_provenance": True,
            "dat_sha256": EXPECTED_HASHES["dat_file"],
            "dat_byte_count": 238336,
            "difference_count": 2,
            "target_faces": [
                {"record_index": 243, "prs_local_gfx": 241, "dat_local_gfx": 98},
                {"record_index": 319, "prs_local_gfx": 243, "dat_local_gfx": 150},
            ],
        },
    }


class OriginalDiscMap02Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.receipt = root / "map02_ru.json"
        self.receipt.write_text(json.dumps(receipt_fixture()), encoding="utf-8")
        self.disc = root / "owned.bin"
        self.disc.write_bytes(b"not an actual PS1 image")

    def test_audit_accepts_consistent_metadata(self):
        self.assertTrue(_validate_audit(audit_fixture()))

    def test_audit_rejects_modified_prs_digest(self):
        audit = audit_fixture()
        audit["compressed_logical_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "PRS logical"):
            _validate_audit(audit)

    def test_audit_rejects_incomplete_dat_evidence(self):
        audit = audit_fixture()
        audit["dat_comparison"]["matches_prior_disc_audit_with_provenance"] = False
        with self.assertRaisesRegex(ValueError, "DAT evidence"):
            _validate_audit(audit)

    def test_audit_rejects_mismatched_target_face(self):
        audit = audit_fixture()
        audit["dat_comparison"]["target_faces"][1]["dat_local_gfx"] = 149
        with self.assertRaisesRegex(ValueError, "face mapping"):
            _validate_audit(audit)

    def test_invalid_disc_size_fails_before_any_sector_read(self):
        with self.assertRaisesRegex(ValueError, "unexpected length"):
            _readonly_disc_digest(self.disc)

    def test_symlink_disc_fails_closed(self):
        link = self.disc.with_suffix(".link")
        link.symlink_to(self.disc)
        with self.assertRaisesRegex(ValueError, "symlink"):
            _readonly_disc_digest(link)

    def test_invalid_receipt_prevents_disc_access(self):
        data = receipt_fixture()
        data["comparison"]["difference_count"] = 3
        self.receipt.write_text(json.dumps(data), encoding="utf-8")
        with patch("tools.verify_map02_ru_owned_disc._readonly_disc_digest") as digest:
            with self.assertRaises(ValueError):
                verify_owned_ru_disc(self.disc, self.receipt)
            digest.assert_not_called()

    def test_original_decoder_is_reused_without_exporting_assets(self):
        prs = b"a" * PRS_BYTES
        dat = b"b" * 238336
        with (patch("tools.verify_map02_ru_owned_disc._readonly_disc_digest",
                    return_value=os.stat(self.disc)) as digest,
              patch("tools.verify_map02_ru_owned_disc.read_sectors",
                    side_effect=[prs, dat]) as reader,
              patch("tools.verify_map02_ru_owned_disc.audit_prs",
                    return_value=audit_fixture()) as auditor,
              patch("tools.verify_map02_ru_owned_disc._unchanged") as unchanged):
            outcome = verify_owned_ru_disc(self.disc, self.receipt)
        digest.assert_called_once()
        self.assertEqual(reader.call_count, 2)
        self.assertEqual(reader.call_args_list[0].kwargs["start_sector"], 7116)
        self.assertEqual(reader.call_args_list[1].kwargs["start_sector"], 6999)
        auditor.assert_called_once_with(prs, dat=dat)
        unchanged.assert_called_once()
        self.assertEqual(outcome["mode2_form1_edc_verified_sectors"],
                         SECTOR_COUNT + DAT_SECTOR_COUNT)
        self.assertTrue(outcome["pinned_ru_disc_sha256_verified"])
        self.assertFalse(outcome["pc_capture_present"])
        self.assertFalse(outcome["same_owned_disc_used_by_executable_proven"])
        self.assertFalse(outcome["native_gpu_vram_pixels_verified"])
        self.assertNotIn(str(self.disc), json.dumps(outcome))

    def test_bad_sector_read_is_not_reported_as_success(self):
        with (patch("tools.verify_map02_ru_owned_disc._readonly_disc_digest",
                    return_value=os.stat(self.disc)),
              patch("tools.verify_map02_ru_owned_disc.read_sectors",
                    side_effect=ValueError("MODE2 sector EDC mismatch"))):
            with self.assertRaisesRegex(ValueError, "EDC mismatch"):
                verify_owned_ru_disc(self.disc, self.receipt)

    def test_optional_trace_remains_unattested(self):
        with (patch("tools.verify_map02_ru_owned_disc._readonly_disc_digest",
                    return_value=os.stat(self.disc)),
              patch("tools.verify_map02_ru_owned_disc.read_sectors",
                    side_effect=[b"x" * PRS_BYTES, b"y" * 238336]),
              patch("tools.verify_map02_ru_owned_disc.audit_prs",
                    return_value=audit_fixture()),
              patch("tools.verify_map02_ru_owned_disc._unchanged"),
              patch("tools.verify_map02_ru_owned_disc.reconcile",
                    return_value={
                        "capture_stdout_independently_replayed": True,
                        "pc_trace_consistent_variant": "PRS",
                        "capture_report_sha256": "f" * 64,
                        "capture_executable_sha256": "e" * 64,
                        "separate_map_loads_checked": 1,
                    })):
            result = verify_owned_ru_disc(
                self.disc, self.receipt, capture_directory=self.disc.parent)
        self.assertTrue(result["pc_capture_present"])
        self.assertEqual(result["pc_trace_consistent_variant"], "PRS")
        self.assertFalse(result["same_owned_disc_used_by_executable_proven"])

    def test_changed_disc_metadata_rejected(self):
        first = os.stat(self.disc)
        self.disc.write_bytes(b"changed")
        from tools.verify_map02_ru_owned_disc import _unchanged
        with self.assertRaisesRegex(ValueError, "changed"):
            _unchanged(self.disc, first)


if __name__ == "__main__":
    unittest.main()
