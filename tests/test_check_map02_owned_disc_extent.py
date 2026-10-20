"""Asset-free original MAP02 raw-sector extent and source pin regressions."""
from pathlib import Path
import hashlib
import os
import shutil
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
                raw[15] = 2  # CD-ROM XA Mode 2
                raw[16:20] = b"\x01\x00\x08\x00"
                raw[20:24] = raw[16:20]  # mirrored XA Form 1 subheader
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

    def test_rejects_mode1_sectors_even_with_valid_sync_and_msf(self):
        with self.image.open("r+b") as f:
            f.seek(self.first * SECTOR_RAW + 15)
            f.write(b"\x01")
        with self.assertRaisesRegex(ValueError, "not XA Mode 2"):
            self.check()

    def test_rejects_form2_payload_masquerading_as_2048_byte_form1(self):
        with self.image.open("r+b") as f:
            for offset in (18, 22):  # both mirrored submode bytes
                f.seek(self.first * SECTOR_RAW + offset)
                f.write(b"\x28")  # FORM2 (0x20) plus DATA (0x08)
        with self.assertRaisesRegex(ValueError, "Form 2, not Form 1"):
            self.check()

    def test_rejects_inconsistent_xa_subheader_copies(self):
        with self.image.open("r+b") as f:
            f.seek(self.first * SECTOR_RAW + 21)
            f.write(b"\x07")
        with self.assertRaisesRegex(ValueError, "subheader copies differ"):
            self.check()

    def test_matching_nonzero_form1_subheaders_are_accepted(self):
        # Ordinary Form 1 headers can carry nonzero file/channel/coding
        # information; only malformed copies or Form 2 are rejected.
        header = b"\x04\x02\x08\x01"
        with self.image.open("r+b") as f:
            f.seek(self.first * SECTOR_RAW + 16)
            f.write(header + header)
        self.assertEqual(self.check()["resource_sector_count"], self.count)

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

    def test_rejects_byte_identical_path_inode_swap_during_sector_reads(self):
        original_sector = _raw_sector
        saved = self.image.with_name("original-private-disc.bin")
        switched = []

        def swap_path_after_open(fd, lba):
            payload = original_sector(fd, lba)
            if not switched:
                self.image.replace(saved)
                shutil.copyfile(saved, self.image)
                self.image.chmod(0o600)
                self.assertNotEqual(saved.stat().st_ino, self.image.stat().st_ino)
                switched.append(True)
            return payload

        try:
            with patch("tools.check_map02_owned_disc_extent._raw_sector",
                       side_effect=swap_path_after_open):
                with self.assertRaisesRegex(ValueError, "changed during sector read|pathname or inode changed"):
                    self.check()
        finally:
            if saved.exists():
                self.image.unlink(missing_ok=True)
                saved.replace(self.image)
        self.assertEqual(switched, [True])

    def test_rejects_in_place_mutation_after_first_full_disc_hash(self):
        original_sector = _raw_sector
        modified = []

        def mutate_while_reading(fd, lba):
            result = original_sector(fd, lba)
            if lba == self.first and not modified:
                writefd = os.open(self.image, os.O_WRONLY | os.O_NOFOLLOW)
                try:
                    os.pwrite(writefd, b"changed!", self.first * SECTOR_RAW + 24)
                finally:
                    os.close(writefd)
                modified.append(True)
            return result

        with patch("tools.check_map02_owned_disc_extent._raw_sector",
                   side_effect=mutate_while_reading):
            with self.assertRaisesRegex(ValueError, "changed during sector read"):
                self.check()
        self.assertEqual(modified, [True])

    def test_second_full_disc_hash_must_match_first_pass_same_fd(self):
        actual_pread = os.pread
        same_offset_passes = []

        def corrupt_only_second_full_pass(fd, length, offset):
            content = actual_pread(fd, length, offset)
            if offset == 0 and length == (1 << 20):
                same_offset_passes.append(True)
                if len(same_offset_passes) == 2:
                    return bytes([content[0] ^ 1]) + content[1:]
            return content

        with patch("tools.check_map02_owned_disc_extent.os.pread",
                   side_effect=corrupt_only_second_full_pass):
            with self.assertRaisesRegex(ValueError, "changed while reading MAP02 sectors"):
                self.check()
        self.assertEqual(len(same_offset_passes), 2)

    def test_rejects_disc_hardlinks_even_with_identical_private_bytes(self):
        alias = self.image.with_name("another-private-disc-hardlink.bin")
        os.link(self.image, alias)
        try:
            with self.assertRaisesRegex(ValueError, "exactly one hardlink"):
                self.check()
        finally:
            alias.unlink()

    def test_new_disc_user_data_byte_changes_cryptographic_digest(self):
        first = self.check()["resource_user_data_sha256"]
        with self.image.open("r+b") as f:
            f.seek(self.first * SECTOR_RAW + 24)
            f.write(b"changed!")
        self.assertNotEqual(first, self.check()["resource_user_data_sha256"])


if __name__ == "__main__":
    unittest.main()
