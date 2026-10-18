"""Private actual original MAP02 CdRead receipt vs synthetic US raw CD test.

GPU join is mocked in this narrow unit test; full original GPU/same-process
verification is independently exercised by the existing MAP02 suites.
No retail game assets are used.
"""
import hashlib
import json
import os
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

from tests.test_check_map02_owned_disc_extent import OwnedMap02DiscExtentTests
from tools.check_map02_owned_disc_extent import _raw_sector
import tools.verify_map02_original_cd_read as cd_module
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
        payload_sha = hashlib.sha256()
        with fixture.image.open("rb") as fd:
            for lba in range(0x1bcc, 0x1bcc + 12):
                fd.seek(lba * 2352)
                block = fd.read(2352)
                crc = zlib.crc32(block[24:24 + 2048], crc)
                payload_sha.update(block[24:24 + 2048])
        self.event = {
            "schema": "vh.map02.original-cd-read.v2",
            "capture_session": "bc" * 16,
            "source": "original-CdRead-and-ContinueLoadingCdFile",
            "cdf": "CDF_M_MAP02_PRS",
            "lba": 0x1bcc,
            "sectors": 12,
            "bytes": 24576,
            "raw_user_crc32": f"{crc:08x}",
            "returned_user_crc32": f"{crc:08x}",
            "raw_user_sha256": payload_sha.hexdigest(),
            "returned_user_sha256": payload_sha.hexdigest(),
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

    def test_correct_crc_but_wrong_native_sha256_rejected(self):
        self.event["raw_user_sha256"] = "f" * 64
        self.event["returned_user_sha256"] = "f" * 64
        self.save()
        with self.assertRaisesRegex(ValueError, "payload differs"):
            self.check()

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
        with self.fixture.image.open("r+b") as f:
            f.seek(0x1bcc * 2352 + 24)
            f.write(b"changed!")
        with self.assertRaisesRegex(ValueError, "payload differs"):
            self.check()

    def test_cd_comparison_rejects_same_bytes_replaced_disc_inode(self):
        image = self.fixture.image
        saved = self.root / "owned-original-backup.bin"
        original_inode = image.stat().st_ino
        original_sector = _raw_sector
        swapped = []

        def replace_path_during_cd_comparison(fd, lba):
            sector = original_sector(fd, lba)
            if not swapped:
                image.replace(saved)
                shutil.copyfile(saved, image)
                image.chmod(0o600)
                self.assertNotEqual(image.stat().st_ino, original_inode)
                swapped.append(True)
            return sector

        try:
            with patch("tools.verify_map02_original_cd_read._raw_sector",
                       side_effect=replace_path_during_cd_comparison):
                with self.assertRaisesRegex(ValueError, "identity changed during CdRead comparison"):
                    self.check()
        finally:
            if saved.exists():
                image.unlink(missing_ok=True)
                saved.replace(image)
        self.assertEqual(swapped, [True])
        self.assertEqual(image.stat().st_ino, original_inode)

    def test_cd_comparison_rejects_disc_changed_after_first_extent_pass(self):
        image = self.fixture.image
        saved = self.root / "pre-cd-replacement.bin"
        original_extent = cd_module.verify_map02_disc_extent
        calls = []

        def swap_after_complete_extent(*args, **kwargs):
            report = original_extent(*args, **kwargs)
            calls.append(1)
            if len(calls) == 1:
                image.replace(saved)
                shutil.copyfile(saved, image)
                image.chmod(0o600)
            return report

        try:
            with patch("tools.verify_map02_original_cd_read.verify_map02_disc_extent",
                       side_effect=swap_after_complete_extent):
                with self.assertRaisesRegex(ValueError, "identity changed before CdRead comparison"):
                    self.check()
        finally:
            if saved.exists():
                image.unlink(missing_ok=True)
                saved.replace(image)
        self.assertEqual(calls, [1])

    def test_cd_comparison_rejects_inplace_mutation_after_extent_audit(self):
        original_sector = _raw_sector
        modified = []

        def modify_while_reading(fd, lba):
            sector = original_sector(fd, lba)
            if not modified:
                writer = os.open(self.fixture.image, os.O_WRONLY | os.O_NOFOLLOW)
                try:
                    os.pwrite(writer, b"changed!", lba * 2352 + 24)
                finally:
                    os.close(writer)
                modified.append(True)
            return sector

        with patch("tools.verify_map02_original_cd_read._raw_sector",
                   side_effect=modify_while_reading):
            with self.assertRaisesRegex(ValueError, "identity changed during CdRead comparison"):
                self.check()
        self.assertEqual(modified, [True])

    def test_byte_identical_cd_receipt_inode_swap_during_disc_audit_rejected(self):
        receipt = self.scoped / CD_READ
        original_inode = receipt.stat().st_ino
        backup = self.root / "saved-original-cd-receipt.jsonl"
        original_audit = cd_module.verify_map02_disc_extent
        replaced = []

        def replace_after_first_extent(*args, **kwargs):
            result = original_audit(*args, **kwargs)
            if not replaced:
                receipt.replace(backup)
                shutil.copyfile(backup, receipt)
                receipt.chmod(0o600)
                self.assertEqual(receipt.read_bytes(), backup.read_bytes())
                self.assertNotEqual(receipt.stat().st_ino, original_inode)
                replaced.append(True)
            return result

        try:
            with patch("tools.verify_map02_original_cd_read.verify_map02_disc_extent",
                       side_effect=replace_after_first_extent):
                with self.assertRaisesRegex(ValueError, "CD receipt or GPU capture changed"):
                    self.check()
        finally:
            if backup.exists():
                receipt.unlink(missing_ok=True)
                backup.replace(receipt)
        self.assertEqual(replaced, [True])
        self.assertEqual(receipt.stat().st_ino, original_inode)

    def test_hardlinked_cd_receipt_rejected_even_when_private(self):
        receipt = self.scoped / CD_READ
        alias = self.root / "receipt-hardlink.jsonl"
        os.link(receipt, alias)
        self.addCleanup(alias.unlink)
        with self.assertRaisesRegex(ValueError, "single-link 0600"):
            self.check()

    def test_same_bytes_changed_receipt_timestamp_rejected(self):
        receipt = self.scoped / CD_READ
        original_audit = cd_module.verify_map02_disc_extent
        modified = []

        def touch_after_first_extent(*args, **kwargs):
            result = original_audit(*args, **kwargs)
            if not modified:
                st = receipt.stat()
                os.utime(receipt, ns=(st.st_atime_ns, st.st_mtime_ns - 1000000000))
                modified.append(True)
            return result

        with patch("tools.verify_map02_original_cd_read.verify_map02_disc_extent",
                   side_effect=touch_after_first_extent):
            with self.assertRaisesRegex(ValueError, "CD receipt or GPU capture changed"):
                self.check()
        self.assertEqual(modified, [True])

    def test_nonprivate_cd_receipt_rejected(self):
        (self.scoped / CD_READ).chmod(0o644)
        with self.assertRaises(ValueError):
            self.check()


if __name__ == "__main__":
    unittest.main()
