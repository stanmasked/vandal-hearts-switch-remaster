"""Stage288 synthetic archival same-guest-clock scene/slow-call revalidation."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from analyze_nexium_steady_state import analyze_archives
from analyze_nexium_steady_segments import analyze_temporal_thirds
from analyze_nexium_steady_segment_sensitivity import analyze_sensitivity
from analyze_nexium_steady_temporal_contrasts import analyze_contrasts
from analyze_nexium_steady_boundary_shifts import analyze_boundary_shifts
from analyze_nexium_steady_boundary_pair_grid import analyze_grid
from analyze_nexium_steady_disjoint_bands import analyze_components
from analyze_nexium_steady_rate_exposure import analyze_exposure
from analyze_nexium_steady_second_profile import analyze_second_profile
from analyze_nexium_steady_scene_alignment import analyze_scene_alignment
from compare_nexium_verified_slow_runs import PREFIX
from test_compare_nexium_idle_switch_pairs import paired_fixture
from test_compare_nexium_verified_slow_runs import create_zip


class Stage288IndependentGuestAlignment(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.paths=[root/"1.zip",root/"2.zip"]
        self.sources=[paired_fixture(28801),paired_fixture(28802)]
        for p,files in zip(self.paths,self.sources):
            create_zip(p,files)
        self.steady=analyze_archives(self.paths,draws=4)
        self.temporal=analyze_temporal_thirds(self.steady)
        self.sensitivity=analyze_sensitivity(self.steady,self.temporal,draws=8)
        self.contrasts=analyze_contrasts(
            self.steady,self.temporal,self.sensitivity,draws=8)
        self.boundary=analyze_boundary_shifts(
            self.steady,self.temporal,self.sensitivity,self.contrasts,draws=8)
        self.grid=analyze_grid(
            self.steady,self.temporal,self.sensitivity,self.contrasts,
            self.boundary,draws=8)
        self.disjoint=analyze_components(
            self.steady,self.temporal,self.sensitivity,self.contrasts,
            self.boundary,self.grid,draws=8)
        self.exposure=analyze_exposure(
            self.steady,self.temporal,self.sensitivity,self.contrasts,
            self.boundary,self.grid,self.disjoint,draws=8)
        self.profile=analyze_second_profile(
            self.steady,self.temporal,self.sensitivity,self.contrasts,
            self.boundary,self.grid,self.disjoint,self.exposure,draws=8)

    def audit(self,archives=None,profile=None):
        return analyze_scene_alignment(
            self.paths if archives is None else archives,
            self.steady,self.temporal,self.sensitivity,self.contrasts,
            self.boundary,self.grid,self.disjoint,self.exposure,
            self.profile if profile is None else profile,draws=8)

    def test_ten_actual_guest_inputs_per_archive_and_51_seconds(self):
        r=self.audit()
        self.assertEqual(r["source_run_ids"],[28801,28802])
        self.assertEqual(r["pair_count"],2)
        self.assertEqual(len(r["events"]),20)
        self.assertEqual(r["scene_input_seconds"]["matched_pair_seconds"],20)
        self.assertEqual(r["other_guest_seconds"]["matched_pair_seconds"],82)
        self.assertEqual(r["all_matched_seconds"]["matched_pair_seconds"],102)
        self.assertEqual([row["input_relative_seconds"] for row in r["runs"]],
                         [[7,11,15,19,23,27,31,35,39,43]]*2)
        self.assertTrue(r["same_guest_monotonic_clock_for_scene_and_audout"])
        self.assertFalse(r["independent_audio_scheduler_event_trace_present"])
        self.assertFalse(r["scene_switch_causality_proven"])
        self.assertFalse(r["physical_switch_tested"])

    def test_full_scene_and_no_scene_accounting_conserves_per_mode_calls(self):
        r=self.audit()
        total=self.steady["steady_pair_verdict"]["totals"]
        for mode in ("idle","switch"):
            for band in ("attempts","ge40","ge50"):
                self.assertEqual(
                    r["scene_input_seconds"]["totals"][mode][band]+
                    r["other_guest_seconds"]["totals"][mode][band],
                    total[mode+"_"+band])

    def test_exact_timing_retains_original_input_order(self):
        r=self.audit()
        for e in r["events"]:
            self.assertTrue(1<=e["audout_guest_second"]<=51)
            self.assertEqual(
                e["slow_40to50_beginnings_within_500ms"]+
                e["slow_ge50_beginnings_within_500ms"],
                e["slow_call_beginnings_within_500ms"])
            self.assertEqual(
                e["slow_calls_completed_before_input"]+
                e["slow_calls_began_after_input"]+
                e["slow_calls_straddled_input"],
                e["slow_call_beginnings_within_500ms"])

    def test_scene_csv_tamper_fails_even_if_per_second_rates_unchanged(self):
        files=dict(self.sources[0])
        files[PREFIX+"soak-guest-optical.csv"]+=b"BAD\n"
        create_zip(self.paths[0],files)
        with self.assertRaises(CorrelationError):
            self.audit()

    def test_switch_slow_timestamp_tamper_fails(self):
        files=dict(self.sources[0])
        files[PREFIX+"soak-audout-slow-unverified.csv"]+=b"BAD\n"
        create_zip(self.paths[0],files)
        with self.assertRaises(CorrelationError):
            self.audit()

    def test_swapped_or_reused_archive_rejected(self):
        with self.assertRaises(CorrelationError):
            self.audit(archives=[self.paths[0],self.paths[0]])
        with self.assertRaises(CorrelationError):
            self.audit(archives=[self.paths[1],self.paths[0]])

    def test_stale_stage287_profile_rejected(self):
        forged=copy.deepcopy(self.profile)
        forged["band_summary"]["ge40"]["positive_seconds"]+=1
        with self.assertRaises(CorrelationError):
            self.audit(profile=forged)

    def test_no_scene_input_on_idle_control_and_no_scheduler_claims(self):
        r=self.audit()
        self.assertEqual(len(r["events"]),20)
        self.assertTrue(r["event_second_intervals_not_randomized"])
        self.assertTrue(r["fixed_switch_before_idle_capture_order"])
        self.assertFalse(r["host_pcm_clock_alignment_proven"])
        self.assertFalse(r["audible_underruns_measured"])


if __name__=="__main__":
    unittest.main()
