"""Stage280 synthetic temporal-third controls; never hardware/audio proof."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from analyze_nexium_steady_state import analyze_archives
from analyze_nexium_steady_segments import analyze_temporal_thirds
from test_compare_nexium_idle_switch_pairs import paired_fixture
from test_compare_nexium_verified_slow_runs import create_zip


class TemporalThirdsRegression(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder=Path(tmp.name)
        archives=[folder/"one.zip",folder/"two.zip"]
        for run,path in zip((28001,28002),archives):
            create_zip(path,paired_fixture(run))
        self.source=analyze_archives(archives,draws=4)

    def test_three_complete_17_second_segments(self):
        result=analyze_temporal_thirds(self.source)
        self.assertEqual(result["segment_count"],3)
        self.assertEqual([(x["first_guest_second"],x["last_guest_second"])
                          for x in result["segments"]],
                         [(1,17),(18,34),(35,51)])
        for part in result["segments"]:
            self.assertEqual(part["seconds_per_mode"],17)
            self.assertEqual(part["totals"]["idle_attempts"],17*36*2)
            self.assertEqual(part["totals"]["switch_attempts"],17*36*2)
            self.assertEqual(part["totals"]["idle_ge40"],17*2*2)
            self.assertEqual(part["totals"]["switch_ge50"],17*2)
        for key,value in result["complete_51s_totals"].items():
            self.assertEqual(sum(p["totals"][key] for p in result["segments"]),value)
        self.assertFalse(result["randomized_experiment"])
        self.assertFalse(result["music_switch_causal_effect_proven"])
        self.assertFalse(result["audible_output_or_underruns_measured"])
        self.assertFalse(result["physical_switch_tested"])

    def test_missing_or_repeated_guest_second_is_rejected(self):
        for mutation in ("missing","duplicate","misnumbered"):
            with self.subTest(mutation=mutation):
                data=copy.deepcopy(self.source)
                rows=data["per_run_windows"][0]["idle"]["per_second"]
                if mutation=="missing":
                    rows.pop()
                elif mutation=="duplicate":
                    rows[1]=rows[0].copy()
                else:
                    rows[0]["second"]=0
                with self.assertRaises(CorrelationError):
                    analyze_temporal_thirds(data)

    def test_wrong_per_second_call_or_slow_bands_rejected(self):
        for field in ("attempts","ge40","ge50"):
            with self.subTest(field=field):
                data=copy.deepcopy(self.source)
                data["per_run_windows"][0]["switch"]["per_second"][0][field]+=1
                with self.assertRaises(CorrelationError):
                    analyze_temporal_thirds(data)

    def test_noncanonical_counter_and_missing_slow_binding_rejected(self):
        for malformed in (True,-1,1.5):
            with self.subTest(value=malformed):
                data=copy.deepcopy(self.source)
                data["per_run_windows"][0]["idle"]["per_second"][0]["attempts"]=malformed
                with self.assertRaises(CorrelationError):
                    analyze_temporal_thirds(data)
        data=copy.deepcopy(self.source)
        data["per_run_windows"][0]["idle"][
            "window_counts_match_exact_slow_timestamps"]=False
        with self.assertRaises(CorrelationError):
            analyze_temporal_thirds(data)

    def test_duplicate_or_removed_pair_is_rejected(self):
        data=copy.deepcopy(self.source)
        data["per_run_windows"][1]["run_id"]=data["per_run_windows"][0]["run_id"]
        with self.assertRaises(CorrelationError):
            analyze_temporal_thirds(data)
        data=copy.deepcopy(self.source)
        data["per_run_windows"].pop()
        with self.assertRaises(CorrelationError):
            analyze_temporal_thirds(data)

    def test_overstated_hardware_or_causal_result_is_rejected(self):
        for key in ("physical_switch_tested",
                    "speaker_audio_output_measured",
                    "music_switch_causality_established"):
            with self.subTest(key=key):
                data=copy.deepcopy(self.source)
                data[key]=True
                with self.assertRaises(CorrelationError):
                    analyze_temporal_thirds(data)


if __name__=="__main__":
    unittest.main()
