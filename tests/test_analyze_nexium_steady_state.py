"""Synthetic Stage279 equal guest-time window controls; not an audible test."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from analyze_nexium_steady_state import analyze_archives,subwindow,WINDOW_COUNT
from test_compare_nexium_idle_switch_pairs import paired_fixture
from test_compare_nexium_verified_slow_runs import create_zip
from test_audit_nexium_audout_latency import make_csv
from test_audit_nexium_audout_scene_correlation import clock
from test_audit_nexium_audout_slow_calls import slow_rows


class SteadyStateComparisons(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.archives=[root/"one.zip",root/"two.zip"]
        self.raws=[paired_fixture(27901),paired_fixture(27902)]
        for path,contents in zip(self.archives,self.raws):
            create_zip(path,contents)

    def test_two_valid_same_binary_pairs_compare_exactly_51_seconds(self):
        report=analyze_archives(self.archives,draws=32)
        self.assertEqual(report["result"],"ORIGINAL_SD_BOUND_COMMON_51S_AUDOUT_REVERIFIED")
        self.assertEqual(report["matched_second_count_per_mode"],51)
        self.assertEqual(report["complete_verified_source_pair_count"],2)
        steady=report["steady_pair_verdict"]
        self.assertEqual(steady["totals"]["idle_attempts"],51*36*2)
        self.assertEqual(steady["totals"]["switch_attempts"],51*36*2)
        self.assertEqual(steady["totals"]["idle_ge40"],51*2*2)
        self.assertEqual(steady["totals"]["switch_ge50"],51*2)
        self.assertFalse(report["physical_switch_tested"])
        self.assertFalse(report["speaker_audio_output_measured"])
        self.assertFalse(report["music_switch_causality_established"])
        self.assertFalse(report["guest_original_sd_reopened_in_offline_report"])
        for pair in report["per_run_windows"]:
            for mode in ("idle","switch"):
                self.assertEqual(pair[mode]["seconds_compared"],51)
                self.assertTrue(pair[mode]["window_counts_match_exact_slow_timestamps"])

    def test_rejected_same_run_reuse(self):
        with self.assertRaises(CorrelationError):
            analyze_archives([self.archives[0],self.archives[0]],draws=4)

    def test_rejected_divergent_nro(self):
        files=paired_fixture(27902)
        preflight=json.loads(files["integrated-nro-preflight.json"])
        preflight["nro_sha256"]="b"*64
        files["integrated-nro-preflight.json"]=(json.dumps(preflight)+"\n").encode()
        create_zip(self.archives[1],files)
        with self.assertRaises(CorrelationError):
            analyze_archives(self.archives,draws=4)

    def test_rejected_original_idle_or_switch_latency_copy_tamper(self):
        for prefix in ("runtime-evidence/idle-control/","runtime-evidence/scene-soak/"):
            with self.subTest(prefix=prefix):
                original=dict(self.raws[0])
                name=prefix+"soak-audout-latency-unverified.csv"
                original[name]+=b"FORGED\n"
                create_zip(self.archives[0],original)
                with self.assertRaises(CorrelationError):
                    analyze_archives(self.archives,draws=4)

    def test_rejected_incomplete_common_interval(self):
        raw=make_csv()
        # Truncation also breaks summary conservation; Stage279 must fail closed.
        shorter=b"\n".join(raw.splitlines()[:53])+b"\n"
        with self.assertRaises((CorrelationError,ValueError)):
            subwindow(shorter,clock(),slow_rows())

    def test_rejected_forged_slow_timestamp_without_new_histogram(self):
        raw=slow_rows().replace(b"CALL,0,",b"CALL,2,",1)
        with self.assertRaises(CorrelationError):
            subwindow(make_csv(),clock(),raw)

    def test_newer_longer_idle_run_never_counts_extra_seconds(self):
        hist=make_csv()
        extra=hist.replace(b"SECOND,52,36,33,1,1,1,0,51000,0,0\n",
                           b"SECOND,52,36,33,1,1,1,0,51000,0,0\n"
                           b"SECOND,53,36,33,1,1,1,0,51000,0,0\n")
        # The independent histogram rejects inconsistent totals; never
        # silently append or include an unverified extra window.
        with self.assertRaises((CorrelationError,ValueError)):
            subwindow(extra,clock(),slow_rows())

    def test_excluding_second_zero_is_not_merely_removing_first_attempt(self):
        report=subwindow(make_csv(),clock(),slow_rows())
        self.assertEqual(report["excluded_first_second_attempts"],36)
        self.assertEqual(report["attempts"],1836)
        self.assertEqual(report["excluded_first_second_ge50"],1)
        self.assertEqual(report["ge50"],51)
        self.assertEqual(report["first_guest_second"],1)
        self.assertEqual(report["last_guest_second"],51)


if __name__=="__main__":
    unittest.main()
