"""Stage310 source-preserving guest exit evidence synthetic provenance tests."""
from __future__ import annotations

import copy
import tempfile
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"tests"))

from audit_switch_guest_scene_trace import TraceError
from audit_nexium_guest_exit_timeline import audit_guest_root,SUBDIR
from audit_nexium_guest_optical_exit_clock import audit_guest_clocks
from preserve_nexium_guest_exit_original import preserve_original
from test_compare_nexium_guest_exit_cohort import fixture


class PreserveGuestOriginalTests(unittest.TestCase):
    def setUp(self):
        self.workspace=tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root=Path(self.workspace.name)/"guest-root"
        self.root.mkdir()
        self.dest=Path(self.workspace.name)/"saved"/"audio-exit-timeline-000.csv"
        _,self.png,_,self.raw,_=fixture(0)
        self.folder=self.root/SUBDIR
        self.folder.mkdir(parents=True)
        (self.folder/"audio-exit-timeline-000.csv").write_bytes(self.raw)
        self.guest=audit_guest_root(self.root)
        self.optical=audit_guest_clocks(self.png,self.guest)

    def run_audit(self, *, guest=None, optical=None, png=None,
                  destination=None):
        return preserve_original(
            self.root,self.guest if guest is None else guest,
            self.optical if optical is None else optical,
            self.png if png is None else png,
            self.dest if destination is None else destination)

    def test_genuine_source_bytes_are_preserved_identically(self):
        r=self.run_audit()
        self.assertEqual(r["result"],
                         "ORIGINAL_GUEST_EXIT_CSV_BYTES_PRESERVED_AND_REAUDITED")
        self.assertEqual(self.dest.read_bytes(),self.raw)
        self.assertTrue(r["original_source_csv_bytes_independently_reaudited"])
        self.assertEqual(r["guest_exit_receipt_sha256"],
                         self.guest["guest_exit_csv_sha256"])
        self.assertFalse(r["physical_Nintendo_Switch_audio_tested"])

    def test_refuse_overwrite_existing_preserved_source(self):
        self.dest.parent.mkdir()
        self.dest.write_bytes(b"earlier source")
        with self.assertRaises(TraceError):
            self.run_audit()
        self.assertEqual(self.dest.read_bytes(),b"earlier source")

    def test_unavailable_guest_transport_must_not_invent_csv(self):
        (self.folder/"audio-exit-timeline-000.csv").unlink()
        absent=audit_guest_root(self.root)
        cross=audit_guest_clocks(self.png,absent)
        r=self.run_audit(guest=absent,optical=cross)
        self.assertEqual(r["result"],"ORIGINAL_GUEST_EXIT_SD_NOT_OBSERVED")
        self.assertFalse(self.dest.exists())
        self.assertFalse(r["original_source_csv_bytes_independently_reaudited"])

    def test_mutated_original_csv_is_rejected(self):
        (self.folder/"audio-exit-timeline-000.csv").write_bytes(
            self.raw.replace(b"stop_requested",b"stop_requestED"))
        with self.assertRaises((TraceError,ValueError)):
            self.run_audit()
        self.assertFalse(self.dest.exists())

    def test_changed_stage307_receipt_is_rejected(self):
        x=copy.deepcopy(self.guest)
        x["guest_exit_csv_sha256"]="a"*64
        with self.assertRaises(TraceError):
            self.run_audit(guest=x)

    def test_changed_stage308_crc_receipt_is_rejected(self):
        x=copy.deepcopy(self.optical)
        x["optical_packet_sha256"]="a"*64
        with self.assertRaises(TraceError):
            self.run_audit(optical=x)

    def test_swapped_optical_png_is_rejected(self):
        _,png,_,_,_=fixture(1)
        with self.assertRaises(TraceError):
            self.run_audit(png=png)

    def test_symlink_original_csv_fails_closed(self):
        original=self.folder/"audio-exit-timeline-000.csv"
        raw=self.root/"some-file"
        raw.write_bytes(self.raw)
        original.unlink()
        original.symlink_to(raw)
        with self.assertRaises((TraceError,ValueError)):
            self.run_audit()

    def test_extra_original_guest_exit_csv_fails_closed(self):
        (self.folder/"audio-exit-timeline-001.csv").write_bytes(self.raw)
        with self.assertRaises((TraceError,ValueError)):
            self.run_audit()

    def test_deterministic_preservation_witness_and_source(self):
        r=self.run_audit()
        self.dest.unlink()
        self.assertEqual(r,self.run_audit())
        self.assertEqual(self.dest.read_bytes(),self.raw)


if __name__=="__main__":
    unittest.main()
