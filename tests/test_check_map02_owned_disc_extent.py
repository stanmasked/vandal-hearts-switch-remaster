"""Asset-free original MAP02 raw-sector extent and source pin regressions."""
from pathlib import Path
import hashlib
import tempfile
import unittest
from unittest.mock import patch

from tools.check_map02_owned_disc_extent import (
    BOOT_LBA_US, SECTOR_RAW, RESOURCE, _bcd, _raw_sector,
    extract_layout, verify_map02_disc_extent,
)
from tools.prepare_map02_pcport import git_blob_sha1


class OwnedMap02DiscExtentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.upstream = root / "original-upstream"
        source = self.upstream / "src/core/cd.c"
        source.parent.mkdir(parents=True)
        self.source = source
        self.source.write_text(
            "CdFileInfo gCdFiles[712] = {"
            "[CDF_M_MAP02_PRS] = {0x1bcc, 0x0c, gScratch1_801317c0},"
            "};\n", encoding="utf-8")
        self.pin = patch.dict(
            "tools.check_map02_owned_disc_extent.SOURCE_BLOBS",
            {"src/core/cd.c": git_blob_sha1(self.source.read_bytes())})
        self.pin.start()
        self.addCleanup(self.pin.stop)
        upstream_check = patch(
            "tools.check_map02_owned_disc_extent.verify_pinned_upstream",
            return_value="a" * 64)
        upstream_check.start()
        self.addCleanup(upstream_check.stop)
        self.image = root / "synthetic-owned-us-raw.bin"
        self.first = 0x1bcc
        self.count = 0x0c
        with self.image.open("wb") as f:
            f.truncate((self.first + self.count) * SECTOR_RAW)
        with self.image.open("r+b") as f:
            for lba in (BOOT_LBA_US, *range(self.first, self.first + self.count)):
                raw = bytearray(SECTOR_RAW)
                raw[:12] = b"\x00" + b"\xff" * 10 + b"\x00"
                pos = lba + 150
                raw[12:15] = bytes((_bcd(pos // 4500),
                                    _bcd(pos // 75 % 60), _bcd(pos % 75)))
                if lba == BOOT_LBA_US:
                    raw[24:32] = b"PS-X EXE"
                else:
                    raw[24:32] = lba.to_bytes(8, "little")
                f.seek(lba * SECTOR_RAW)
                f.write(raw)
        self.image.chmod(0o600)

    def check(self):
        return verify_map02_disc_extent(self.image, self.upstream)

    def test_private_original_map02_extent_with_12_real_sector_frames(self):
        report = self.check()
        self.assertEqual(report["resource"], RESOURCE)
        self.assertEqual(report["resource_lba"], self.first)
        self.assertEqual(report["resource_sector_count"], self.count)
        self.assertEqual(report["resource_user_data_bytes_checked"], 24576)
        self.assertFalse(report["original_gameplay_resource_read_observed"])
        self.assertFalse(report["retail_image_authenticity_proven"])
        self.assertEqual(len(report["resource_user_data_sha256"]), 64)

    def test_rejects_modified_sector_sync_and_msf(self):
        with self.image.open("r+b") as f:
            f.seek(self.first * SECTOR_RAW)
            f.write(b"\x03")
        with self.assertRaisesRegex(ValueError, "synchronization"):
            self.check()
        with self.image.open("r+b") as f:
            f.seek(self.first * SECTOR_RAW)
            f.write(b"\x00")
            f.seek(self.first * SECTOR_RAW + 12)
            f.write(b"\x00")
        with self.assertRaisesRegex(ValueError, "MSF"):
            self.check()

    def test_rejects_truncated_and_nonprivate_or_linked_images(self):
        with self.image.open("r+b") as f:
            f.truncate((self.first + self.count - 1) * SECTOR_RAW)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.check()
        with self.image.open("r+b") as f:
            f.truncate((self.first + self.count) * SECTOR_RAW)
        self.image.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "owner-private"):
            self.check()
        link = self.image.parent / "alias.bin"
        link.symlink_to(self.image)
        with self.assertRaises(ValueError):
            verify_map02_disc_extent(link, self.upstream)

    def test_rejects_other_disc_without_us_boot_signature(self):
        with self.image.open("r+b") as f:
            f.seek(BOOT_LBA_US * SECTOR_RAW + 24)
            f.write(b"XXXXXXXX")
        with self.assertRaisesRegex(ValueError, "boot signature"):
            self.check()

    def test_source_table_drift_must_not_change_original_map02_lba(self):
        self.assertEqual(extract_layout(self.source.read_text()), (0x1bcc, 0x0c))
        with self.assertRaisesRegex(ValueError, "resource LBA/count"):
            extract_layout("[CDF_M_MAP02_PRS] = {0x1bcd, 0x0c, gScratch1_801317c0}")
        with self.assertRaisesRegex(ValueError, "anchor"):
            extract_layout("[CDF_NOT_MAP02] = {0x1bcc, 0x0c, 0}")
        self.source.write_text(
            "[CDF_M_MAP02_PRS] = {0x1bcc, 0x0d, gScratch1_801317c0}")
        with self.assertRaisesRegex(ValueError, "no longer pinned"):
            self.check()

    def test_new_disc_user_data_byte_changes_cryptographic_digest(self):
        first = self.check()["resource_user_data_sha256"]
        with self.image.open("r+b") as f:
            f.seek(self.first * SECTOR_RAW + 24)
            f.write(b"changed!")
        self.assertNotEqual(first, self.check()["resource_user_data_sha256"])


if __name__ == "__main__":
    unittest.main()
