"""No-retail-assets regressions for MAP02 self-reported digest-only receipt."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.check_map02_local_disc_receipt import (
    FIELDS, MAP02_PRS_SHA256, RAW_BYTES, validate_receipt,
    verify_receipt_file,
)


class LocalDiscReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "digest.json"
        self.data = {
            "schema": "vh.map02.local-ru-disc-digest.v1",
            "raw_image_bytes": RAW_BYTES,
            "raw_image_sectors": RAW_BYTES // 2352,
            "raw_image_sha256": "a" * 64,
            "cue_single_mode2_2352": True,
            "checked_xa_form1_sectors": 13,
            "map02_prs_lba": 0x1bcc,
            "map02_prs_sectors": 12,
            "map02_prs_bytes": 22783,
            "map02_prs_sha256": MAP02_PRS_SHA256,
            "map02_matches_prior_ru_audit": True,
            "byte_exact_original_us_executable_proven": False,
            "real_gameplay_capture_proven": False,
            "physical_ps1_pixel_parity_proven": False,
            "game_bytes_in_receipt": False,
        }

    def raw(self):
        return (json.dumps(self.data, sort_keys=True) + "\n").encode()

    def test_good_structure_does_not_automatically_authenticate_disc(self):
        self.path.write_bytes(self.raw())
        self.path.chmod(0o600)
        v = verify_receipt_file(self.path)
        self.assertTrue(v["receipt_schema_verified"])
        self.assertFalse(v["self_reported_disc_bytes_independently_verified"])
        self.assertFalse(v["actual_gameplay_frame_verified"])
        self.assertEqual(v["reported_raw_image_sha256"], "a" * 64)

    def test_rejects_unknown_missing_or_duplicated_field(self):
        self.assertEqual(self.data.keys(), FIELDS)
        for mutation in ("delete", "extra"):
            data = dict(self.data)
            if mutation == "delete":
                del data["map02_prs_sha256"]
            else:
                data["private_local_path"] = "/private/game.bin"
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "fields"):
                validate_receipt((json.dumps(data) + "\n").encode())
        duplicate = self.raw().replace(b'"schema": ', b'"schema": "forged", "schema": ', 1)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_receipt(duplicate)

    def test_rejects_overclaims_and_changed_prs_digest(self):
        for key, wrong in (
            ("real_gameplay_capture_proven", True),
            ("physical_ps1_pixel_parity_proven", True),
            ("game_bytes_in_receipt", True),
            ("byte_exact_original_us_executable_proven", True),
            ("map02_prs_sha256", "b" * 64),
            ("cue_single_mode2_2352", False),
            ("map02_matches_prior_ru_audit", False),
        ):
            with self.subTest(key=key):
                old = self.data[key]
                self.data[key] = wrong
                with self.assertRaisesRegex(ValueError, "unsupported"):
                    validate_receipt(self.raw())
                self.data[key] = old

    def test_rejects_inconsistent_sector_count_type_and_bad_hash(self):
        for key, bad in (("raw_image_sectors", 123),
                         ("raw_image_bytes", RAW_BYTES + 1),
                         ("checked_xa_form1_sectors", 12),
                         ("map02_prs_lba", 7115),
                         ("map02_prs_sectors", True),
                         ("raw_image_sha256", "A" * 64)):
            old = self.data[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.data[key] = bad
                validate_receipt(self.raw())
            self.data[key] = old

    def test_rejects_public_or_linked_parent_directory(self):
        self.path.write_bytes(self.raw())
        self.path.chmod(0o600)
        parent = self.path.parent
        parent.chmod(0o755)
        try:
            with self.assertRaisesRegex(ValueError, "directory must be owner-private"):
                verify_receipt_file(self.path)
        finally:
            parent.chmod(0o700)
        linked_parent = parent.parent / (parent.name + "-alias")
        linked_parent.symlink_to(parent, target_is_directory=True)
        self.addCleanup(linked_parent.unlink)
        with self.assertRaises((ValueError, OSError)):
            verify_receipt_file(linked_parent / self.path.name)
        self.assertTrue(verify_receipt_file(self.path)["receipt_schema_verified"])

    def test_rejects_insecure_file_symlink_and_wrong_framing(self):
        self.path.write_bytes(self.raw())
        self.path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "owner-private"):
            verify_receipt_file(self.path)
        self.path.chmod(0o600)
        alias = self.path.parent / "alias.json"
        alias.symlink_to(self.path)
        with self.assertRaises((OSError, ValueError)):
            verify_receipt_file(alias)
        for bad in (self.raw()[:-1], self.raw().replace(b"\n", b"\r\n")):
            with self.assertRaisesRegex(ValueError, "framing"):
                validate_receipt(bad)


if __name__ == "__main__":
    unittest.main()
