"""Asset-free test of the one-command Mac audit orchestration.

The mocked inspection result deliberately does NOT attest a real disc.
Full 664,849,248-byte I/O, sector EDC/PRS verification, and receipt schema
each have independent tests elsewhere in the repo.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import stage_map02_private_disc as staging
from tools import run_map02_private_disc_audit as runner
from tools.check_map02_local_disc_receipt import (
    SCHEMA, RAW_BYTES, MAP02_LBA, MAP02_SECTORS,
    MAP02_PRS_BYTES, MAP02_PRS_SHA256,
    verify_receipt_file,
)

FAKE_BYTES = b"SYNTHETIC-PRIVATE-ORCHESTRATION-TEST".ljust(2352, b"\x00") * 4


class PrivateAuditHandoffTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.mount = self.root / "mounted"
        self.mount.mkdir()
        self.out = self.root / "private"
        self.out.mkdir(mode=0o700)
        self.bin = self.mount / staging.BIN_NAME
        self.cue = self.mount / staging.CUE_NAME
        self.bin.write_bytes(FAKE_BYTES)
        self.bin.chmod(0o644)
        self.cue.write_bytes(
            (f'FILE "{staging.BIN_NAME}" BINARY\r\n'
             '  TRACK 01 MODE2/2352\r\n'
             '    INDEX 01 00:00:00\r\n').encode("ascii")
        )
        self.cue.chmod(0o644)
        self.sha = hashlib.sha256(FAKE_BYTES).hexdigest()
        self.cue_raw = self.cue.read_bytes()

    def fake_structure_only_report(self, **overrides):
        """This is a mock report; never interpreted as authentic CD evidence."""
        record = {
            "schema": SCHEMA,
            "raw_image_bytes": RAW_BYTES,
            "raw_image_sectors": RAW_BYTES // 2352,
            "raw_image_sha256": self.sha,
            "cue_single_mode2_2352": True,
            "checked_xa_form1_sectors": 1 + MAP02_SECTORS,
            "map02_prs_lba": MAP02_LBA,
            "map02_prs_sectors": MAP02_SECTORS,
            "map02_prs_bytes": MAP02_PRS_BYTES,
            "map02_prs_sha256": MAP02_PRS_SHA256,
            "map02_matches_prior_ru_audit": True,
            "byte_exact_original_us_executable_proven": False,
            "real_gameplay_capture_proven": False,
            "physical_ps1_pixel_parity_proven": False,
            "game_bytes_in_receipt": False,
        }
        record.update(overrides)
        return record

    def _run_with_fake_inspection(self, report=None):
        # Exercise real stage, real atomic receipt publication, real consumer
        # validation; substitute ONLY the actual retail CD-XA inspection, which
        # necessarily requires the owner's inaccessible original image.
        real_stage = staging.stage_disc
        def small_stage(source, cue, private):
            return real_stage(source, cue, private,
                              expected_bytes=len(FAKE_BYTES))
        with patch.object(runner, "stage_disc", side_effect=small_stage), \
                patch.object(runner, "inspect",
                             return_value=report if report is not None
                             else self.fake_structure_only_report()):
            return runner.run_private_audit(self.bin, self.cue, self.out)

    def test_private_orchestration_publishes_only_schema_json(self):
        result = self._run_with_fake_inspection()
        self.assertEqual(result.name, runner.publish.__globals__["RECEIPT"])
        self.assertEqual(result.stat().st_mode & 0o777, 0o600)
        self.assertEqual(result.parent.stat().st_mode & 0o777, 0o700)
        self.assertTrue(result.is_file())
        self.assertEqual(verify_receipt_file(result)["reported_raw_image_sha256"],
                         self.sha)
        record = json.loads(result.read_text("ascii"))
        self.assertEqual(record["raw_image_sha256"], self.sha)
        self.assertFalse(record["real_gameplay_capture_proven"])
        self.assertFalse(record["byte_exact_original_us_executable_proven"])
        self.assertEqual((self.bin.stat().st_mode & 0o777,
                          self.cue.stat().st_mode & 0o777), (0o644, 0o644))
        self.assertEqual(self.bin.read_bytes(), FAKE_BYTES)
        self.assertEqual(self.cue.read_bytes(), self.cue_raw)
        private = self.out / staging.STAGE_NAME
        self.assertEqual((private / staging.BIN_NAME).read_bytes(), FAKE_BYTES)
        self.assertEqual(sorted(p.name for p in result.parent.iterdir()),
                         [result.name])

    def test_second_invocation_refuses_existing_local_copy_and_receipt(self):
        receipt = self._run_with_fake_inspection()
        original = receipt.read_bytes()
        with self.assertRaises(FileExistsError):
            self._run_with_fake_inspection()
        self.assertEqual(receipt.read_bytes(), original)
        self.assertEqual(list(self.out.iterdir()),
                         [self.out / staging.STAGE_NAME])

    def test_hash_mismatch_refuses_receipt_but_keeps_private_copy(self):
        wrong = self.fake_structure_only_report(raw_image_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "audited-copy SHA-256 differ"):
            self._run_with_fake_inspection(wrong)
        self.assertEqual(list((self.out / staging.STAGE_NAME / "receipt").iterdir()), [])
        self.assertEqual(self.bin.read_bytes(), FAKE_BYTES)

    def test_broken_sector_inspection_never_publishes_receipt(self):
        real_stage = staging.stage_disc
        with patch.object(
                runner, "stage_disc",
                side_effect=lambda src, cue, parent:
                real_stage(src, cue, parent, expected_bytes=len(FAKE_BYTES))), \
             patch.object(runner, "inspect",
                          side_effect=ValueError("original MAP02 sector EDC mismatch")):
            with self.assertRaisesRegex(ValueError, "EDC mismatch"):
                runner.run_private_audit(self.bin, self.cue, self.out)
        self.assertEqual(list((self.out / staging.STAGE_NAME / "receipt").iterdir()), [])
        self.assertEqual(self.bin.read_bytes(), FAKE_BYTES)

    def test_bad_receipt_claim_rejected_before_publication(self):
        bad = self.fake_structure_only_report(real_gameplay_capture_proven=True)
        with self.assertRaisesRegex(ValueError, "overstated"):
            self._run_with_fake_inspection(bad)
        self.assertEqual(list((self.out / staging.STAGE_NAME / "receipt").iterdir()), [])
        self.assertEqual(self.bin.read_bytes(), FAKE_BYTES)


if __name__ == "__main__":
    unittest.main()
