"""Stage315 independent raw audout original and guest exit archive replay."""
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
from audit_nexium_guest_exit_three_run_cohort import SCHEMA as UNUSED
from audit_nexium_guest_last_buffer_return import audit_guest
from audit_nexium_guest_optical_exit_clock import audit_guest_clocks
from preserve_nexium_guest_exit_original import preserve_original as preserve_exit
from preserve_nexium_guest_last_buffer_original import preserve_original as preserve_page
from replay_nexium_original_audout_exit_archive import (
    independent_original_audout_replay, read_original_archive,
    ORIGINAL_PAGE, SOURCE313, SOURCE314,
)
from test_replay_nexium_original_guest_exit_archive import ArchiveReplayerTests
from test_preserve_nexium_guest_last_buffer_original import original_page
from test_compare_nexium_guest_exit_cohort import fixture


class Stage315OriginalAudoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.folder=root/"original-archive"
        self.folder.mkdir()
        self.guest=root/"original-guest"
        sd=self.guest/SUBDIR
        sd.mkdir(parents=True)
        self.run_id=39145082758
        _,self.optical,_,self.guest_exit,_=fixture(0)
        (sd/"audio-exit-timeline-000.csv").write_bytes(self.guest_exit)
        self.guest_page=original_page()
        # Stage313 source in this fixture must use SAME guest clock
        # as the original Stage307 guest exit receipt.
        from audit_nexium_guest_exit_timeline import parse_exit_csv
        plus=parse_exit_csv(self.guest_exit)["guest_monotonic_timestamps_ns"]["plus_observed"]
        self.guest_page=("event,value\n"
                         "page_return_count,380\n"
                         f"last_page_return_guest_ns,{plus+200}\n"
                         "last_page_frames,128\n"
                         "tail_attempt_guest_ns,0\n"
                         "tail_success_return_guest_ns,0\n").encode()
        (sd/ORIGINAL_PAGE).write_bytes(self.guest_page)
        s307=audit_guest_root(self.guest)
        s308=audit_guest_clocks(self.optical,s307)
        s310=preserve_exit(self.guest,s307,s308,self.optical,
                           self.folder/"audio-exit-timeline-000.csv")
        s313=audit_guest(self.guest)
        s314=preserve_page(self.guest,s307,s310,s313,self.guest_exit,
                           self.folder/ORIGINAL_PAGE)
        (self.folder/"scene-optical-trace.png").write_bytes(self.optical)
        self.REPORTS={
            "guest-audio-exit-timeline-stage307.json":s307,
            "guest-optical-exit-clock-stage308.json":s308,
            "guest-original-exit-source-stage310.json":s310,
            SOURCE313:s313,
            SOURCE314:s314,
        }
        for name,data in self.REPORTS.items():
            (self.folder/name).write_text(json.dumps(data,sort_keys=True)+"\n")
        self.fixtures=read_original_archive(self.folder)

    def replay(self, inputs=None):
        return independent_original_audout_replay(
            *(self.fixtures if inputs is None else inputs),self.run_id)

    def test_independent_original_both_guest_sources_with_sha(self):
        report=self.replay()
        self.assertEqual(report["result"],
                         "ORIGINAL_GUEST_AUDOUT_RELEASE_AND_EXIT_SOURCES_INDEPENDENTLY_REPLAYED")
        self.assertTrue(report["both_original_guest_created_CSVs_reaudited_byte_exact"])
        self.assertTrue(report["stages_313_314_independently_replayed"])
        self.assertEqual(report["last_page_relative_to_guest_Plus_observed_ns"],200)
        self.assertFalse(report["physical_Nintendo_Switch_audio_tested"])

    def test_corrupted_original_page_source_rejected(self):
        bad=list(self.fixtures)
        bad[1]=bad[1].replace(b"page_return_count,380",b"page_return_count,381")
        with self.assertRaises(TraceError):
            self.replay(tuple(bad))

    def test_bad_original_exit_source_rejected(self):
        bad=list(self.fixtures)
        bad[0]=bad[0].replace(b"plus_observed",b"plus_observeD")
        with self.assertRaises((TraceError,ValueError)):
            self.replay(tuple(bad))

    def test_forged_original_stage313_receipt_rejected(self):
        bad=list(self.fixtures)
        bad[6]=copy.deepcopy(bad[6])
        bad[6]["last_page_relative_to_Plus_ns"]+=1
        with self.assertRaises(TraceError):
            self.replay(tuple(bad))

    def test_forged_original_stage314_sha_rejected(self):
        bad=list(self.fixtures)
        bad[7]=copy.deepcopy(bad[7])
        bad[7]["original_guest_output_csv_sha256"]="0"*64
        with self.assertRaises(TraceError):
            self.replay(tuple(bad))

    def test_swapped_optical_scene_pixel_source_rejected(self):
        bad=list(self.fixtures)
        bad[2]=fixture(1)[1]
        with self.assertRaises(TraceError):
            self.replay(tuple(bad))

    def test_noncolocated_original_csv_must_fail(self):
        relocated=self.folder/"other"
        relocated.mkdir()
        (self.folder/ORIGINAL_PAGE).rename(relocated/ORIGINAL_PAGE)
        with self.assertRaises(TraceError):
            read_original_archive(self.folder)

    def test_duplicate_original_page_csv_fails(self):
        other=self.folder/"duplicate"
        other.mkdir()
        (other/ORIGINAL_PAGE).write_bytes(self.guest_page)
        with self.assertRaises(TraceError):
            read_original_archive(self.folder)

    def test_missing_original_guest_page_source_no_json_fallback(self):
        (self.folder/ORIGINAL_PAGE).unlink()
        with self.assertRaises(TraceError):
            read_original_archive(self.folder)

    def test_symlink_original_guest_page_rejected(self):
        source=self.folder/ORIGINAL_PAGE
        copy_path=self.folder/"real_guest_page"
        copy_path.write_bytes(self.guest_page)
        source.unlink()
        source.symlink_to(copy_path)
        with self.assertRaises(TraceError):
            read_original_archive(self.folder)

    def test_stage313_receipt_absent_no_fallback(self):
        (self.folder/SOURCE313).unlink()
        with self.assertRaises(TraceError):
            read_original_archive(self.folder)

    def test_stage314_receipt_absent_no_fallback(self):
        (self.folder/SOURCE314).unlink()
        with self.assertRaises(TraceError):
            read_original_archive(self.folder)

    def test_invalid_original_capture_identity(self):
        with self.assertRaises(TraceError):
            independent_original_audout_replay(*self.fixtures,0)

    def test_determinism_no_physical_audio_claim(self):
        report=self.replay()
        self.assertEqual(report,self.replay())
        self.assertTrue(report["guest_monotonic_clock_not_host_PCM_sample_clock"])
        self.assertTrue(report["last_page_release_is_NOT_audible_sample_or_DAC_time"])
        self.assertFalse(report["original_soundtrack_or_audible_dropout_verified"])

if __name__=="__main__":
    unittest.main()
