"""Asset-free private BIN/CUE receipt producer and consumer regressions."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.audit_map02_disc_prs import xa_edc
from tools import check_map02_local_disc_receipt as verifier
from tools.emit_map02_local_disc_receipt import (
    RECEIPT, inspect, publish, MAP02_LBA, MAP02_SECTORS,
    MAP02_PRS_BYTES, BOOT_LBA_US, SECTOR_RAW,
)


def mode2_sector(lba, payload=b""):
    raw = bytearray(SECTOR_RAW)
    raw[:12] = b"\x00" + b"\xff" * 10 + b"\x00"
    frames = lba + 150
    raw[12:15] = bytes((((frames // 4500) // 10 << 4)
                        | (frames // 4500) % 10,
                        (((frames // 75) % 60) // 10 << 4)
                        | ((frames // 75) % 60) % 10,
                        ((frames % 75) // 10 << 4) | (frames % 75) % 10))
    raw[15] = 2
    raw[16:20] = b"\x00\x00\x08\x00"
    raw[20:24] = raw[16:20]
    raw[24:24 + len(payload)] = payload
    raw[0x818:0x81c] = xa_edc(raw[0x10:0x818]).to_bytes(4, "little")
    return raw


class OwnedDiscProducerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.image = self.root / "synthetic.bin"
        self.cue = self.root / "synthetic.cue"
        self.sectors = MAP02_LBA + MAP02_SECTORS
        self.payload = bytearray(MAP02_SECTORS * 2048)
        self.payload[:4] = (MAP02_PRS_BYTES - 4).to_bytes(4, "little")
        self.payload[4:MAP02_PRS_BYTES] = b"A" * (MAP02_PRS_BYTES - 4)
        self.prs_sha = hashlib.sha256(self.payload[:MAP02_PRS_BYTES]).hexdigest()
        with self.image.open("wb") as file:
            file.truncate(self.sectors * SECTOR_RAW)
            file.seek(BOOT_LBA_US * SECTOR_RAW)
            file.write(mode2_sector(BOOT_LBA_US, b"PS-X EXE"))
            for i in range(MAP02_SECTORS):
                file.seek((MAP02_LBA + i) * SECTOR_RAW)
                begin = i * 2048
                file.write(mode2_sector(MAP02_LBA + i,
                                        self.payload[begin:begin + 2048]))
        self.image.chmod(0o600)
        self.cue.write_text(
            'FILE "synthetic.bin" BINARY\n'
            '  TRACK 01 MODE2/2352\n'
            '    INDEX 01 00:00:00\n',
            encoding="ascii")
        self.cue.chmod(0o600)
        self.out = self.root / "receipt"
        self.out.mkdir(mode=0o700)

    def inspect(self):
        return inspect(self.image, self.cue,
                       expected_bytes=self.sectors * SECTOR_RAW,
                       expected_prs_sha256=self.prs_sha)

    def test_positive_receipt_and_no_false_authentication(self):
        report = self.inspect()
        self.assertEqual(report["checked_xa_form1_sectors"], 13)
        self.assertEqual(report["raw_image_bytes"], self.sectors * SECTOR_RAW)
        self.assertFalse(report["real_gameplay_capture_proven"])
        self.assertFalse(report["game_bytes_in_receipt"])
        path = publish(report, self.out)
        self.assertEqual(path.name, RECEIPT)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(path.read_text())["raw_image_sha256"],
                         report["raw_image_sha256"])

    def test_producer_to_repo_verifier_roundtrip(self):
        report = self.inspect()
        path = publish(report, self.out)
        with patch.object(verifier, "RAW_BYTES", self.sectors * SECTOR_RAW), \
                patch.object(verifier, "MAP02_PRS_SHA256", self.prs_sha):
            checked = verifier.verify_receipt_file(path)
        self.assertTrue(checked["receipt_schema_verified"])
        self.assertFalse(checked["self_reported_disc_bytes_independently_verified"])
        self.assertEqual(checked["reported_raw_image_sha256"],
                         report["raw_image_sha256"])

    def test_corrupt_map02_sector_edc_rejected(self):
        with self.image.open("r+b") as f:
            f.seek(MAP02_LBA * SECTOR_RAW + 24)
            f.write(b"X")
        with self.assertRaisesRegex(ValueError, "EDC"):
            self.inspect()

    def test_modified_prs_with_coherent_edc_rejected(self):
        with self.image.open("r+b") as f:
            f.seek(MAP02_LBA * SECTOR_RAW)
            raw = mode2_sector(MAP02_LBA, self.payload[:2048])
            raw[30] = ord("Z")
            raw[0x818:0x81c] = xa_edc(raw[0x10:0x818]).to_bytes(4, "little")
            f.write(raw)
        with self.assertRaisesRegex(ValueError, "PRS SHA-256"):
            self.inspect()

    def test_corrupt_boot_edc_rejected(self):
        with self.image.open("r+b") as f:
            f.seek(BOOT_LBA_US * SECTOR_RAW + 36)
            f.write(b"!")
        with self.assertRaisesRegex(ValueError, "EDC"):
            self.inspect()

    def test_insecure_or_wrong_cue_rejected(self):
        self.image.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "0600"):
            self.inspect()
        self.image.chmod(0o600)
        self.cue.write_text('FILE "wrong.bin" BINARY\n'
                            '  TRACK 01 MODE2/2352\n'
                            '    INDEX 01 00:00:00\n')
        with self.assertRaisesRegex(ValueError, "CUE"):
            self.inspect()

    def test_reject_wrong_image_size_and_form2(self):
        with self.image.open("r+b") as f:
            f.truncate(self.image.stat().st_size - 1)
        with self.assertRaisesRegex(ValueError, "size/2352"):
            self.inspect()

    def test_reject_public_or_symlinked_receipt_directory(self):
        report = self.inspect()
        self.out.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "0700"):
            publish(report, self.out)
        self.out.chmod(0o700)
        alias = self.root / "output-alias"
        alias.symlink_to(self.out, target_is_directory=True)
        with self.assertRaises((OSError, ValueError)):
            publish(report, alias)
        self.assertEqual(list(self.out.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
