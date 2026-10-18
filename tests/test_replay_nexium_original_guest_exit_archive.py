"""Stage311 separate-run original guest exit raw-source replay and attacks."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from audit_switch_guest_scene_trace import TraceError
from audit_nexium_guest_exit_timeline import SUBDIR, audit_guest_root
from audit_nexium_guest_optical_exit_clock import audit_guest_clocks
from preserve_nexium_guest_exit_original import preserve_original
from replay_nexium_original_guest_exit_archive import (
    ORIGINAL, PNG, REPORTS, read_archive, independent_archive_replay,
)
from test_compare_nexium_guest_exit_cohort import fixture


class ArchiveReplayerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.archive = root / "original-NeXium-artifact"
        self.archive.mkdir()
        self.guestroot = root / "isolated-original-SD"
        folder = self.guestroot / SUBDIR
        folder.mkdir(parents=True)
        _, self.png, _, self.original, _ = fixture(0)
        (folder / ORIGINAL).write_bytes(self.original)
        self.stage307 = audit_guest_root(self.guestroot)
        self.stage308 = audit_guest_clocks(self.png, self.stage307)
        self.stage310 = preserve_original(
            self.guestroot, self.stage307, self.stage308,
            self.png, self.archive / ORIGINAL)
        (self.archive / PNG).write_bytes(self.png)
        for name, doc in zip(REPORTS,
                             (self.stage307, self.stage308, self.stage310)):
            (self.archive / name).write_text(
                json.dumps(doc, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    def audit(self):
        return independent_archive_replay(
            *read_archive(self.archive), 39141325435)

    def test_original_source_bytes_replayed_separate_from_guest_runner(self):
        r = self.audit()
        self.assertEqual(r["result"],
                         "INDEPENDENT_ORIGINAL_GUEST_EXIT_BYTES_FULLY_REPLAYED")
        self.assertEqual(r["original_capture_workflow_run_id"], 39141325435)
        self.assertTrue(r["original_guest_csv_bytes_independently_reaudited"])
        self.assertTrue(r["source_stage307_receipt_reproduced"])
        self.assertTrue(r["source_stage308_receipt_reproduced"])
        self.assertTrue(r["source_stage310_receipt_reproduced"])
        self.assertFalse(r["physical_Nintendo_Switch_audio_tested"])

    def test_repeated_replay_is_identical(self):
        self.assertEqual(self.audit(), self.audit())

    def test_missing_original_csv_fails_not_fallback_to_json(self):
        (self.archive / ORIGINAL).unlink()
        with self.assertRaises(TraceError):
            self.audit()

    def test_changed_original_csv_bytes_rejected(self):
        source = self.archive / ORIGINAL
        source.write_bytes(self.original.replace(
            b"stop_requested", b"stop_requestED"))
        with self.assertRaises((TraceError, ValueError)):
            self.audit()

    def test_forged_stage307_report_rejected(self):
        self.stage307["guest_exit_csv_sha256"] = "f" * 64
        (self.archive / REPORTS[0]).write_text(json.dumps(self.stage307))
        with self.assertRaises(TraceError):
            self.audit()

    def test_forged_stage308_report_rejected(self):
        self.stage308["guest_exit_order_verified"] = False
        (self.archive / REPORTS[1]).write_text(json.dumps(self.stage308))
        with self.assertRaises(TraceError):
            self.audit()

    def test_forged_stage310_receipt_rejected(self):
        self.stage310["original_source_csv_bytes_independently_reaudited"] = False
        (self.archive / REPORTS[2]).write_text(json.dumps(self.stage310))
        with self.assertRaises(TraceError):
            self.audit()

    def test_different_optical_scene_capture_rejected(self):
        _,png,_,_,_ = fixture(1)
        (self.archive / PNG).write_bytes(png)
        with self.assertRaises(TraceError):
            self.audit()

    def test_symlink_original_source_rejected(self):
        p = self.archive / ORIGINAL
        other = self.archive / "elsewhere"
        other.write_bytes(self.original)
        p.unlink()
        p.symlink_to(other)
        with self.assertRaises(TraceError):
            self.audit()

    def test_duplicate_named_originals_fail_closed(self):
        (self.archive / "ambiguous").mkdir()
        (self.archive / "ambiguous" / ORIGINAL).write_bytes(self.original)
        with self.assertRaises(TraceError):
            self.audit()

    def test_separated_receipt_directory_rejected(self):
        different = self.archive / "detached"
        different.mkdir()
        (self.archive / REPORTS[2]).rename(different / REPORTS[2])
        with self.assertRaises(TraceError):
            self.audit()

    def test_duplicate_source_run_identity_or_missing_run_rejected(self):
        raw, image, a, b, c = read_archive(self.archive)
        with self.assertRaises(TraceError):
            independent_archive_replay(raw,image,a,b,c,0)
        with self.assertRaises(TraceError):
            independent_archive_replay(raw,image,a,b,c,True)

    def test_source_receipt_does_not_claim_hardware_or_pcm_clock_mapping(self):
        r=self.audit()
        self.assertTrue(r["guest_software_clock_not_calibrated_to_host_pcm"])
        self.assertFalse(r["audible_music_or_dropout_verified"])
        self.assertFalse(r["retail_audio_assets_present_in_receipt"])
        self.assertFalse(r["physical_Nintendo_Switch_audio_tested"])


if __name__ == "__main__":
    unittest.main()
