"""Stage337 four authentic NeXium originals and source/NRO same-run binding tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"tests"))

from audit_nexium_guest_exit_timeline import ExitTimelineError
from audit_nexium_stage334_capture_manifest import audit_original_capture
from audit_nexium_stage336_capture_build_binding import bind_sources
from compare_nexium_stage335_three_original_capture_sources import ALL_PINS
from compare_nexium_stage337_four_original_captures import compare_four,find_unique,RESULT
from test_compare_nexium_stage335_three_original_capture_sources import sample_capture

THIRD_SHA="a"*40
FOURTH_SHA="c"*40
THIRD_RUN=39175592570
FOURTH_RUN=39177437951
THIRD_NRO="b"*64
FOURTH_NRO="d"*64


def build_receipts(nro_digest:str,sha:str,run:int)->tuple[dict,dict]:
    preflight={
        "result":"SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED",
        "git_sha":sha,"run_id":run,"run_attempt":1,
        "nro_filename":"vandal-hearts-prototype.nro",
        "nro_sha256":nro_digest,"nro_bytes":124000,
        "hardware_status":"HARDWARE NOT TESTED",
    }
    monitor={
        "source_nro_sha256":nro_digest,
        "hardware_status":"HARDWARE NOT TESTED",
        "recording":"virtual PulseAudio null-sink monitor; not audible playback",
        "sample_format":"s16le stereo 48000Hz",
        "raw_bytes":100_000,
    }
    return preflight,monitor


class FourRealCaptureSourceReplayTests(unittest.TestCase):
    def setUp(self):
        self.a=sample_capture(0,last_duration=11225937,prior_duration=32154011)
        self.b=sample_capture(1,last_duration=22352500,prior_duration=31247083)
        self.c=sample_capture(2,last_duration=18486979,prior_duration=32374948)
        self.d=sample_capture(3,last_duration=42000000,prior_duration=31000000)
        self.third_preflight,self.third_monitor=build_receipts(THIRD_NRO,THIRD_SHA,THIRD_RUN)
        self.fourth_preflight,self.fourth_monitor=build_receipts(FOURTH_NRO,FOURTH_SHA,FOURTH_RUN)

    def compare(self,a=None,b=None,c=None,d=None,old_pins=None,
                third_saved=None,third_preflight=None,third_monitor=None,
                fourth_saved=None,fourth_binding=None,fourth_preflight=None,
                fourth_monitor=None,third_sha=THIRD_SHA,fourth_sha=FOURTH_SHA):
        sources=[self.a if a is None else a,
                 self.b if b is None else b,
                 self.c if c is None else c,
                 self.d if d is None else d]
        if old_pins is None:
            old_pins=[{k:audit_original_capture(x)[k] for k in ALL_PINS}
                      for x in sources[:2]]
        third_saved=audit_original_capture(sources[2]) if third_saved is None else third_saved
        fourth_saved=audit_original_capture(sources[3]) if fourth_saved is None else fourth_saved
        third_preflight=self.third_preflight if third_preflight is None else third_preflight
        third_monitor=self.third_monitor if third_monitor is None else third_monitor
        fourth_preflight=self.fourth_preflight if fourth_preflight is None else fourth_preflight
        fourth_monitor=self.fourth_monitor if fourth_monitor is None else fourth_monitor
        fourth_binding=bind_sources(
            sources[3],fourth_saved,fourth_preflight,fourth_monitor,
            git_sha=FOURTH_SHA,run_id=FOURTH_RUN,run_attempt=1) if fourth_binding is None else fourth_binding
        return compare_four(
            sources,old_pins,third_saved,third_preflight,third_monitor,
            fourth_saved,fourth_binding,fourth_preflight,fourth_monitor,
            third_sha=third_sha,third_run_id=THIRD_RUN,third_attempt=1,
            fourth_sha=fourth_sha,fourth_run_id=FOURTH_RUN,fourth_attempt=1)

    def test_four_distinct_authentic_sources_and_NROs(self):
        report=self.compare()
        self.assertEqual(report["result"],RESULT)
        self.assertEqual(len(report["cohorts"]),4)
        self.assertEqual([r["guest_last_software_duration_ns"] for r in report["cohorts"]],
                         [11225937,22352500,18486979,42000000])
        self.assertEqual([r["guest_prior_lower_median_software_ns"] for r in report["cohorts"]],
                         [32154011,31247083,32374948,31000000])
        self.assertEqual(report["cohorts"][-1]["guest_last_first_possible_rank"],16)
        self.assertEqual(report["third_same_run_nro_sha256"],THIRD_NRO)
        self.assertEqual(report["fourth_same_run_nro_sha256"],FOURTH_NRO)
        self.assertFalse(report["third_and_fourth_nro_sha256_match"])
        self.assertFalse(report["physical_Nintendo_Switch_audio_tested"])

    def test_valid_fourth_fast_last_call_is_not_rejected(self):
        fourth=sample_capture(3,last_duration=10000000,prior_duration=31000000)
        report=self.compare(d=fourth)
        self.assertEqual(report["cohorts"][-1]["guest_last_first_possible_rank"],1)
        self.assertEqual(report["cohorts"][-1]["guest_prior_median_minus_last_software_ns"],21000000)

    def test_valid_reproducible_NRO_binaries_can_have_same_digest(self):
        pre,monitor=build_receipts(THIRD_NRO,FOURTH_SHA,FOURTH_RUN)
        r=self.compare(fourth_preflight=pre,fourth_monitor=monitor)
        self.assertTrue(r["third_and_fourth_nro_sha256_match"])
        self.assertTrue(r["all_four_original_guest_host_CSV_source_hashes_distinct"])

    def test_fourth_forged_saved_stage334_receipt_rejected(self):
        saved=audit_original_capture(self.d)
        saved["original_guest_last_call_duration_software_ns"]+=1
        with self.assertRaises(ExitTimelineError):
            self.compare(fourth_saved=saved,fourth_binding={})

    def test_fourth_forged_saved_stage336_receipt_rejected(self):
        saved=audit_original_capture(self.d)
        bound=bind_sources(self.d,saved,self.fourth_preflight,self.fourth_monitor,
                           git_sha=FOURTH_SHA,run_id=FOURTH_RUN,run_attempt=1)
        bound["source_nro_sha256"]="0"*64
        with self.assertRaises(ExitTimelineError):
            self.compare(fourth_binding=bound)

    def test_third_wrong_same_run_commit_rejected(self):
        with self.assertRaises(ExitTimelineError):
            self.compare(third_sha="0"*40)

    def test_fourth_wrong_NRO_monitor_source_SHA_rejected(self):
        changed=copy.deepcopy(self.fourth_monitor)
        changed["source_nro_sha256"]="0"*64
        with self.assertRaises(ExitTimelineError):
            self.compare(fourth_monitor=changed,fourth_binding={})

    def test_previous_archived_source_pin_change_rejected(self):
        pins=[{k:audit_original_capture(x)[k] for k in ALL_PINS}
              for x in (self.a,self.b)]
        pins[1]["original_host_monotonic_csv_sha256"]="0"*64
        with self.assertRaises(ExitTimelineError):
            self.compare(old_pins=pins)

    def test_duplicate_fourth_guest_csv_source_rejected(self):
        changed=copy.deepcopy(self.d)
        for key in ("history_csv","last_csv","stage320","stage322"):
            changed[key]=copy.deepcopy(self.c[key])
        with self.assertRaises(ExitTimelineError):
            self.compare(d=changed)

    def test_duplicate_fourth_host_source_rejected(self):
        changed=copy.deepcopy(self.d)
        for key in ("legacy_csv","monotonic_csv","stage325","stage304"):
            changed[key]=copy.deepcopy(self.c[key])
        with self.assertRaises(ExitTimelineError):
            self.compare(d=changed)

    def test_original_source_roots_missing_or_ambiguous_rejected(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(ExitTimelineError):
                find_unique(root,"source-guest-host-stage334.json")
            (root/"source-guest-host-stage334.json").write_text("{}")
            p=root/"nested"
            p.mkdir()
            (p/"source-guest-host-stage334.json").write_text("{}")
            with self.assertRaises(ExitTimelineError):
                find_unique(root,"source-guest-host-stage334.json")

    def test_source_archived_preflight_symlink_rejected(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            (root/"original").write_text("{}")
            (root/"integrated-nro-preflight.json").symlink_to(root/"original")
            with self.assertRaises(ExitTimelineError):
                find_unique(root,"integrated-nro-preflight.json")

    def test_only_own_clock_differences_and_no_absolute_timestamps(self):
        report=self.compare()
        self.assertEqual(len(report["fourth_minus_previous_three_own_clock_differences"]),3)
        serialized=json.dumps(report,sort_keys=True)
        for forbidden in ("host_epoch_ms","begin_guest_ns","end_guest_ns","123450000000","pcm_samples"):
            self.assertNotIn(forbidden,serialized)
        self.assertTrue(report["no_software_guest_clock_converted_into_host_PCM_clock"])
        self.assertFalse(report["original_PS1_soundtrack_or_audible_dropout_verified"])


if __name__=="__main__":
    unittest.main()
