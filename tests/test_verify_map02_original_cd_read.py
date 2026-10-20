"""Private actual original MAP02 CdRead receipt vs synthetic US raw CD test.

GPU join is mocked in this narrow unit test; full original GPU/same-process
verification is independently exercised by the existing MAP02 suites.
No retail game assets are used.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

from tests.test_check_map02_owned_disc_extent import OwnedMap02DiscExtentTests
from tools.check_map02_owned_disc_extent import _raw_sector
from tools.audit_map02_disc_prs import xa_edc
from tools.verify_map02_original_cd_read import verify_map02_original_cd_read
from tools.verify_map02_window_scoped_join import CD_READ


class OriginalCdReadReceiptTests(unittest.TestCase):
    def setUp(self):
        fixture = OwnedMap02DiscExtentTests(
            methodName="test_private_original_map02_extent_with_12_real_sector_frames")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root = Path(fixture.tmp.name)
        self.scoped, self.native = self.root / "scoped", self.root / "native"
        self.scoped.mkdir(mode=0o700)
        self.native.mkdir(mode=0o700)
        crc = 0
        with fixture.image.open("rb") as fd:
            for lba in range(0x1bcc, 0x1bcc + 12):
                fd.seek(lba * 2352)
                block = fd.read(2352)
                crc = zlib.crc32(block[24:24 + 2048], crc)
        self.event = {
            "schema": "vh.map02.original-cd-read.v1",
            "capture_session": "bc" * 16,
            "source": "original-CdRead-and-ContinueLoadingCdFile",
            "cdf": "CDF_M_MAP02_PRS",
            "lba": 0x1bcc,
            "sectors": 12,
            "bytes": 24576,
            "raw_user_crc32": f"{crc:08x}",
            "returned_user_crc32": f"{crc:08x}",
            "loader_completed": True,
        }
        self.save()
        self.report = {
            "original_map02_cd_read_receipt_present": True,
            "original_map02_cd_read_receipt_sha256":
                hashlib.sha256((self.scoped / CD_READ).read_bytes()).hexdigest(),
            "capture_session_sha256": "d" * 64,
        }
        mock = patch(
            "tools.verify_map02_original_cd_read.verify_window_scoped_join",
            return_value=self.report)
        self.join = mock.start()
        self.addCleanup(mock.stop)

    def save(self):
        receipt = self.scoped / CD_READ
        receipt.write_bytes(
            (json.dumps(self.event, separators=(",", ":"), sort_keys=True)
             + "\n").encode())
        receipt.chmod(0o600)

    def check(self):
        return verify_map02_original_cd_read(
            self.scoped, self.native, self.fixture.image,
            self.fixture.upstream, frame=7)

    def test_completed_read_matches_private_raw_image_and_manifest(self):
        result = self.check()
        self.assertTrue(result["original_map02_cd_read_observed"])
        self.assertTrue(result["original_game_loader_completion_observed"])
        self.assertEqual(result["original_map02_resource_sector_count"], 12)
        self.assertEqual(result["original_map02_resource_lba"], 0x1bcc)
        self.assertFalse(result["original_map02_gameplay_frame_authenticated"])
        self.assertFalse(result["physical_ps1_equivalence_proven"])
        self.assertEqual(self.join.call_count, 2)

    def test_wrong_sector_crc_rejected(self):
        self.event["raw_user_crc32"] = "00000000"
        self.event["returned_user_crc32"] = "00000000"
        self.save()
        with self.assertRaisesRegex(ValueError, "payload differs"):
            self.check()

    def test_missing_original_cdread_receipt_rejected(self):
        self.report["original_map02_cd_read_receipt_present"] = False
        with self.assertRaisesRegex(ValueError, "missing actual"):
            self.check()

    def test_mutated_raw_disc_data_rejected(self):
        # EDC must still be valid to exercise the independent original
        # CdRead receipt versus owned-disc CRC comparison.
        with self.fixture.image.open("r+b") as f:
            f.seek(0x1bcc * 2352)
            sector = bytearray(f.read(2352))
            sector[24:32] = b"changed!"
            sector[0x818:0x81c] = xa_edc(
                sector[0x10:0x818]).to_bytes(4, "little")
            f.seek(0x1bcc * 2352)
            f.write(sector)
        with self.assertRaisesRegex(ValueError, "payload differs"):
            self.check()

    def test_mutated_raw_disc_without_updated_edc_rejected_first(self):
        # Independently ensure that a damaged Mode 2 Form 1 sector is
        # refused before it can be treated as valid user data.
        with self.fixture.image.open("r+b") as f:
            f.seek(0x1bcc * 2352 + 24)
            f.write(b"changed!")
        with self.assertRaisesRegex(ValueError, "EDC mismatch"):
            self.check()

    def test_nonprivate_cd_receipt_rejected(self):
        (self.scoped / CD_READ).chmod(0o644)
        with self.assertRaises(ValueError):
            self.check()


if __name__ == "__main__":
    unittest.main()
