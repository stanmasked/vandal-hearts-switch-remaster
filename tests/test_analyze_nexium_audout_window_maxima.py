"""Regressions: window maxima do not masquerade as per-call distributions."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from analyze_nexium_audout_window_maxima import (
    analyze, individual_run, rank_nearest,
)
from audit_nexium_audout_repeatability import RepeatabilityError, MEMBERS
from test_audit_nexium_audout_repeatability import fixture

class WindowMaximaTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.a = Path(temp.name) / "run-1.zip"
        self.b = Path(temp.name) / "run-2.zip"
        fixture(self.a, 701, samples=36)
        fixture(self.b, 702, samples=37)

    def test_exact_derived_windows_and_explicit_bounds(self):
        report = analyze([self.a, self.b])
        self.assertEqual(report["result"], "SAME_NRO_GUEST_WINDOW_MAXIMA_VERIFIED")
        self.assertEqual(report["run_count"], 2)
        self.assertFalse(report["per_call_latency_distribution_known"])
        self.assertFalse(report["audible_underruns_measured"])
        for run in report["runs"]:
            self.assertEqual(run["windows"], 53)
            self.assertEqual(run["windows_ge_50ms"], 53)
            self.assertEqual(run["seconds_with_max_ge_50ms"], list(range(53)))
            self.assertEqual(sum(b["window_count"] for b in run["window_maximum_bins"]), 53)
            self.assertEqual(run["max_window_us_global"], 52000)
            self.assertEqual(run["max_window_us_p90_nearest_rank"], 52000)
            self.assertEqual(len(run["per_second_windows"]), 53)

    def test_rank_is_nearest_rank_not_linear_interpolation(self):
        self.assertEqual(rank_nearest([2,1,3,9], .5), 2)
        self.assertEqual(rank_nearest([2,1,3,9], .9), 9)
        self.assertEqual(rank_nearest([2,1,3,9], .99), 9)

    def test_wrong_binary_and_repeat_run_are_rejected(self):
        fixture(self.b, 701, samples=37)
        with self.assertRaises(RepeatabilityError):
            analyze([self.a, self.b])
        fixture(self.b, 702, samples=37, nro="b5"*32)
        with self.assertRaises(RepeatabilityError):
            analyze([self.a, self.b])

    def test_original_csv_copy_corruption_rejected(self):
        fixture(self.b, 702, samples=37, corrupt="csv")
        with self.assertRaises(RepeatabilityError):
            analyze([self.a, self.b])

    def test_empty_evidence_rejected(self):
        self.b.unlink()
        with self.assertRaises(RepeatabilityError):
            analyze([self.a, self.b])

    def test_wrong_second_window_rejected(self):
        raw = self.b.read_bytes()
        with zipfile.ZipFile(self.b) as z:
            contents = {n:z.read(n) for n in z.namelist()}
        csv_name=MEMBERS["csv"]
        contents[csv_name]=contents[csv_name].replace(b"SECOND,0,",b"SECOND,2,",1)
        with zipfile.ZipFile(self.b,"w") as z:
            for name,payload in contents.items():
                z.writestr(name,payload)
        with self.assertRaises((RepeatabilityError,ValueError)):
            analyze([self.a,self.b])

if __name__ == "__main__":
    unittest.main()
