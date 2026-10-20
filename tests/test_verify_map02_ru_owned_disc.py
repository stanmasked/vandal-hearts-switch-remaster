"""Asset-free tests for owned RU disc verification: no original 665MB disc required."""
import copy
from contextlib import ExitStack, nullcontext
import json
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_check_map02_ru_receipt import fixture as receipt_fixture
from tools.check_map02_ru_receipt import EXPECTED_HASHES
from tools.verify_map02_ru_owned_disc import (
    PRS_BYTES, SECTOR_COUNT, DAT_SECTOR_COUNT, EXPECTED_DISC_BYTES,
    _readonly_disc_digest, _open_verified_disc, _validate_audit, verify_owned_ru_disc,
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
        with patch("tools.verify_map02_ru_owned_disc._open_verified_disc") as digest:
            with self.assertRaises(ValueError):
                verify_owned_ru_disc(self.disc, self.receipt)
            digest.assert_not_called()

    def test_original_decoder_is_reused_without_exporting_assets(self):
        prs = b"a" * PRS_BYTES
        dat = b"b" * 238336
        descriptor = object()
        with ExitStack() as stack:
            digest = stack.enter_context(patch(
                "tools.verify_map02_ru_owned_disc._open_verified_disc",
                side_effect=lambda path: nullcontext((descriptor, os.stat(self.disc)))))
            reader = stack.enter_context(patch(
                "tools.verify_map02_ru_owned_disc.read_sectors_from_stream",
                side_effect=[prs, dat]))
            auditor = stack.enter_context(patch(
                "tools.verify_map02_ru_owned_disc.audit_prs",
                return_value=audit_fixture()))
            outcome = verify_owned_ru_disc(self.disc, self.receipt)
        digest.assert_called_once_with(self.disc)
        self.assertEqual(reader.call_count, 2)
        self.assertIs(reader.call_args_list[0].args[0], descriptor)
        self.assertIs(reader.call_args_list[1].args[0], descriptor)
        self.assertEqual(reader.call_args_list[0].kwargs["start_sector"], 7116)
        self.assertEqual(reader.call_args_list[1].kwargs["start_sector"], 6999)
        auditor.assert_called_once_with(prs, dat=dat)
        self.assertEqual(outcome["mode2_form1_edc_verified_sectors"],
                         SECTOR_COUNT + DAT_SECTOR_COUNT)
        self.assertTrue(outcome["pinned_ru_disc_sha256_verified"])
        self.assertFalse(outcome["pc_capture_present"])
        self.assertFalse(outcome["same_owned_disc_used_by_executable_proven"])
        self.assertFalse(outcome["native_gpu_vram_pixels_verified"])
        self.assertNotIn(str(self.disc), json.dumps(outcome))

    def test_bad_sector_read_is_not_reported_as_success(self):
        with ExitStack() as stack:
            stack.enter_context(patch(
                "tools.verify_map02_ru_owned_disc._open_verified_disc",
                side_effect=lambda path: nullcontext((object(), os.stat(self.disc)))))
            stack.enter_context(patch(
                "tools.verify_map02_ru_owned_disc.read_sectors_from_stream",
                side_effect=ValueError("MODE2 sector EDC mismatch")))
            with self.assertRaisesRegex(ValueError, "EDC mismatch"):
                verify_owned_ru_disc(self.disc, self.receipt)

    def test_optional_trace_remains_unattested(self):
        with ExitStack() as stack:
            stack.enter_context(patch(
                "tools.verify_map02_ru_owned_disc._open_verified_disc",
                side_effect=lambda path: nullcontext((object(), os.stat(self.disc)))))
            stack.enter_context(patch(
                "tools.verify_map02_ru_owned_disc.read_sectors_from_stream",
                side_effect=[b"x" * PRS_BYTES, b"y" * 238336]))
            stack.enter_context(patch(
                "tools.verify_map02_ru_owned_disc.audit_prs",
                return_value=audit_fixture()))
            stack.enter_context(patch(
                "tools.verify_map02_ru_owned_disc.reconcile",
                return_value={
                    "capture_stdout_independently_replayed": True,
                    "pc_trace_consistent_variant": "PRS",
                    "capture_report_sha256": "f" * 64,
                    "capture_executable_sha256": "e" * 64,
                    "separate_map_loads_checked": 1,
                }))
            result = verify_owned_ru_disc(
                self.disc, self.receipt, capture_directory=self.disc.parent)
        self.assertTrue(result["pc_capture_present"])
        self.assertEqual(result["pc_trace_consistent_variant"], "PRS")
        self.assertFalse(result["same_owned_disc_used_by_executable_proven"])

    def test_single_descriptor_detects_filename_swap_during_sector_read(self):
        fake = b"sample-owned-disc"
        self.disc.write_bytes(fake)
        with ExitStack() as stack:
            stack.enter_context(patch("tools.verify_map02_ru_owned_disc.EXPECTED_DISC_BYTES", len(fake)))
            stack.enter_context(patch(
                "tools.verify_map02_ru_owned_disc.EXPECTED_DISC_SHA256",
                hashlib.sha256(fake).hexdigest()))
            original = self.disc.with_name("first.bin")
            with self.assertRaisesRegex(ValueError, "changed"):
                with _open_verified_disc(self.disc) as (handle, _):
                    self.assertEqual(handle.read(2), fake[:2])
                    self.disc.rename(original)
                    self.disc.write_bytes(b"another-file-byte")
            original.unlink()

    def test_single_descriptor_detects_in_place_mutation(self):
        fake = b"original-owned-file"
        self.disc.write_bytes(fake)
        with ExitStack() as stack:
            stack.enter_context(patch("tools.verify_map02_ru_owned_disc.EXPECTED_DISC_BYTES", len(fake)))
            stack.enter_context(patch(
                "tools.verify_map02_ru_owned_disc.EXPECTED_DISC_SHA256",
                hashlib.sha256(fake).hexdigest()))
            with self.assertRaisesRegex(ValueError, "changed"):
                with _open_verified_disc(self.disc) as (handle, _):
                    with self.disc.open("r+b") as writer:
                        writer.seek(0)
                        writer.write(b"modified")

    def test_changed_disc_metadata_rejected(self):
        first = os.stat(self.disc)
        self.disc.write_bytes(b"changed")
        from tools.verify_map02_ru_owned_disc import _unchanged
        with self.assertRaisesRegex(ValueError, "changed"):
            _unchanged(self.disc, first)


if __name__ == "__main__":
    unittest.main()
