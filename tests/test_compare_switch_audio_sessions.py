#!/usr/bin/env python3
"""NRO baseline/candidate CSV comparison tests: no assets, libnx or SD I/O."""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))
import analyze_switch_audio_log as analyzer  # noqa: E402
import compare_switch_audio_sessions as compare  # noqa: E402


def make_rows(*, count=21, pages_per_step=200, pcm_faults=(),
              home_faults=(), lease_faults=(), latency_us=12000,
              home_per_step=1, baseline_pcm_fail=0, baseline_pages=50000,
              finish=True, first_event="START", start_ms=0):
    """Preloaded large cumulative counters must never become incidents."""
    rows = []
    for i in range(count):
        row = {name: 0 for name in analyzer.COLUMNS}
        row.update({
            "elapsed_ms": start_ms + i*5000,
            "event": first_event if i == 0 else (
                "EXIT" if i == count-1 and finish else "RESUME"),
            "status": 0 if i == count-1 and finish else 1,
            "home_resumes": 40 + i*home_per_step,
            "first_pcm_count": 100 + i,
            "last_pcm_us": latency_us,
            "worst_pcm_us": max(latency_us, 14000),
            "output_pages": baseline_pages + i*pages_per_step,
            "output_frames": 20000000 + i*pages_per_step*557,
            "pcm_fail": baseline_pcm_fail + sum(k<=i for k in pcm_faults),
            "home_fail": 3 + sum(k<=i for k in home_faults),
            "lease_fail": 1 + sum(k<=i for k in lease_faults),
        })
        rows.append(row)
    return rows


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir=Path(temp.name)
        self.paths=[]

    def add(self, rows, label="record"):
        path=self.dir / f"{label}_{len(self.paths)}.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer=csv.writer(stream)
            writer.writerow(analyzer.COLUMNS)
            writer.writerows([[r[name] for name in analyzer.COLUMNS] for r in rows])
        self.paths.append(path)
        return path

    def cohorts(self, baseline=None, candidate=None):
        baseline=baseline or [make_rows(),make_rows()]
        candidate=candidate or [make_rows(),make_rows()]
        old=[self.add(rows,"old") for rows in baseline]
        new=[self.add(rows,"new") for rows in candidate]
        return old,new

    def compare_paths(self, old, new):
        return compare.compare(compare.group(old),compare.group(new))

    def run_cli(self, old, new, as_json=True):
        tool=ROOT / "tools" / "compare_switch_audio_sessions.py"
        args=[sys.executable,str(tool),"--baseline",
              *[str(p) for p in old],"--candidate",
              *[str(p) for p in new]]
        if as_json:
            args.extend(["--format","json"])
        return subprocess.run(args, text=True, capture_output=True)

    def test_identical_cohorts_no_false_regression(self):
        old,new=self.cohorts()
        r=self.compare_paths(old,new)
        self.assertEqual(r["verdict"],"NO_REGRESSION_FLAG")
        self.assertEqual(r["flags"],[])
        self.assertEqual(r["baseline"]["counters"]["output_pages"],8000)
        self.assertEqual(r["candidate"]["counters"]["output_pages"],8000)
        self.assertEqual(r["baseline"]["counters"]["pcm_fail"],0)
        self.assertEqual(r["candidate"]["latency"]["p95_us"],12000)
        self.assertTrue(r["metrics"]["pcm_fail"]["comparable"])
        self.assertTrue(r["metrics"]["home_fail"]["comparable"])
        self.assertTrue(r["metrics"]["ack_latency_p95_us"]["comparable"])
        cmd=self.run_cli(old,new)
        self.assertEqual(cmd.returncode,0,cmd.stderr)
        self.assertEqual(json.loads(cmd.stdout)["verdict"],"NO_REGRESSION_FLAG")
        tool=ROOT / "tools" / "compare_switch_audio_sessions.py"
        versioned=subprocess.run([
            sys.executable,str(tool),"--baseline",*[str(p) for p in old],
            "--candidate",*[str(p) for p in new],
            "--baseline-version","old-sha","--candidate-version","new-sha",
            "--format","json"],text=True,capture_output=True,check=True)
        self.assertEqual(json.loads(versioned.stdout)["versions"],
                         {"baseline":"old-sha","candidate":"new-sha"})

    def test_candidate_pcm_fault_growth_flags_nonzero_exit(self):
        old,new=self.cohorts(candidate=[
            make_rows(pcm_faults=(2,3,4,5)),
            make_rows(pcm_faults=(9,10,11))])
        r=self.compare_paths(old,new)
        self.assertEqual(r["verdict"],"POTENTIAL_REGRESSION")
        self.assertIn("pcm_fail",r["flags"])
        self.assertEqual(r["candidate"]["counters"]["pcm_fail"],7)
        self.assertEqual(r["baseline"]["counters"]["pcm_fail"],0)
        self.assertEqual(r["metrics"]["pcm_fail"]["candidate_rate"],8.75)
        cmd=self.run_cli(old,new)
        self.assertEqual(cmd.returncode,1,cmd.stderr)
        self.assertEqual(json.loads(cmd.stdout)["verdict"],"POTENTIAL_REGRESSION")

    def test_more_raw_faults_but_lower_page_rate_not_flagged(self):
        old,new=self.cohorts(
            baseline=[make_rows(pages_per_step=100,pcm_faults=(2,3,4)),
                      make_rows(pages_per_step=100,pcm_faults=(5,6,7))],
            candidate=[make_rows(pages_per_step=250,pcm_faults=(2,3,4,5)),
                       make_rows(pages_per_step=250,pcm_faults=(6,7,8))])
        r=self.compare_paths(old,new)
        self.assertEqual(r["candidate"]["counters"]["pcm_fail"],7)
        self.assertEqual(r["baseline"]["counters"]["pcm_fail"],6)
        self.assertEqual(r["verdict"],"NO_REGRESSION_FLAG")
        self.assertLess(r["metrics"]["pcm_fail"]["candidate_rate"],
                        r["metrics"]["pcm_fail"]["baseline_rate"])

    def test_home_fault_rate_uses_resume_exposure(self):
        old,new=self.cohorts(candidate=[
            make_rows(home_faults=(3,6)),make_rows(home_faults=(4,8))])
        r=self.compare_paths(old,new)
        self.assertIn("home_fail",r["flags"])
        self.assertEqual(r["metrics"]["home_fail"]["exposure"],"home_resumes")
        self.assertEqual(r["metrics"]["home_fail"]["scale"],100)
        self.assertEqual(r["metrics"]["home_fail"]["candidate_rate"],10)
        self.assertEqual(r["metrics"]["home_fail"]["baseline_rate"],0)

    def test_lagging_pcm_completion_p95_threshold(self):
        old,new=self.cohorts(candidate=[
            make_rows(latency_us=75000),make_rows(latency_us=75000)])
        r=self.compare_paths(old,new)
        self.assertIn("ack_latency_p95_us",r["flags"])
        self.assertEqual(r["metrics"]["ack_latency_p95_us"]["baseline"],12000)
        self.assertEqual(r["metrics"]["ack_latency_p95_us"]["candidate"],75000)
        self.assertEqual(r["baseline"]["latency"]["sample_count"],40)
        self.assertEqual(r["candidate"]["latency"]["sample_count"],40)

    def test_not_enough_p95_samples_or_home_events(self):
        old,new=self.cohorts(
            baseline=[make_rows(count=4,pages_per_step=400,home_per_step=0),
                      make_rows(count=4,pages_per_step=400,home_per_step=0)],
            candidate=[make_rows(count=4,pages_per_step=400,home_per_step=0,
                                  latency_us=99000,home_faults=(1,2)),
                       make_rows(count=4,pages_per_step=400,home_per_step=0,
                                  latency_us=99000,home_faults=(1,2))])
        r=self.compare_paths(old,new)
        self.assertEqual(r["verdict"],"NO_REGRESSION_FLAG")
        self.assertFalse(r["metrics"]["home_fail"]["comparable"])
        self.assertFalse(r["metrics"]["ack_latency_p95_us"]["comparable"])
        self.assertFalse(r["metrics"]["home_fail"]["regression_flag"])
        self.assertFalse(r["metrics"]["ack_latency_p95_us"]["regression_flag"])
        self.assertTrue(any("latency" in w for w in r["warnings"]))

    def test_inconclusive_single_or_short_sessions(self):
        old,new=self.cohorts(
            baseline=[make_rows(count=3,pages_per_step=100)],
            candidate=[make_rows(),make_rows(pcm_faults=(1,2,3,4))])
        r=self.compare_paths(old,new)
        self.assertEqual(r["verdict"],"INCONCLUSIVE")
        self.assertFalse(r["metrics"]["pcm_fail"]["comparable"])
        self.assertFalse(r["metrics"]["pcm_fail"]["regression_flag"])
        self.assertTrue(r["baseline"]["quality_problems"])
        result=self.run_cli(old,new)
        self.assertEqual(result.returncode,0)
        self.assertEqual(json.loads(result.stdout)["verdict"],"INCONCLUSIVE")

    def test_inconclusive_missing_exit_counter_resets_or_clock(self):
        old,new=self.cohorts(
            candidate=[make_rows(finish=False),
                       make_rows(first_event="PERIODIC")])
        r=self.compare_paths(old,new)
        self.assertEqual(r["verdict"],"INCONCLUSIVE")
        self.assertTrue(r["candidate"]["quality_problems"])
        self.assertEqual(r["candidate"]["truncated_windows"],1)

    def test_ring_rollover_keeps_lifetime_faults_but_comparison_inconclusive(self):
        older = [make_rows(), make_rows()]
        newer = []
        for _ in range(2):
            rows = make_rows(count=21, pages_per_step=200)
            rows[1]["event"] = "GAP"
            for row in rows[1:]:
                # Early bursts were evicted and are only represented
                # by cumulative counts at the GAP boundary.
                row["pcm_fail"] = 16
                row["home_fail"] = 4
            newer.append(rows)
        old, new = self.cohorts(baseline=older, candidate=newer)
        r = self.compare_paths(old,new)
        self.assertEqual(r["candidate"]["historical_gaps"], 2)
        self.assertEqual(r["candidate"]["counters"]["pcm_fail"], 32)
        self.assertEqual(r["candidate"]["counters"]["home_fail"], 8)
        self.assertEqual(r["verdict"], "INCONCLUSIVE")
        self.assertFalse(r["metrics"]["pcm_fail"]["comparable"])
        self.assertFalse(r["metrics"]["pcm_fail"]["regression_flag"])
        self.assertTrue(any("GAP" in w for w in r["warnings"]))
        self.assertTrue(all(any("historical GAP" in x for x in item["reasons"])
                            for item in r["candidate"]["quality_problems"]))
        result = self.run_cli(old,new)
        self.assertEqual(result.returncode,0)
        self.assertEqual(json.loads(result.stdout)["verdict"],"INCONCLUSIVE")

    def test_old_baseline_does_not_count_faults(self):
        old,new=self.cohorts(
            baseline=[make_rows(baseline_pcm_fail=U32_SMALL),
                      make_rows(baseline_pcm_fail=U32_SMALL)],
            candidate=[make_rows(baseline_pcm_fail=0),
                       make_rows(baseline_pcm_fail=0)])
        r=self.compare_paths(old,new)
        self.assertEqual(r["verdict"],"NO_REGRESSION_FLAG")
        self.assertEqual(r["baseline"]["counters"]["pcm_fail"],0)

    def test_mixed_home_exposure_warns(self):
        old,new=self.cohorts(
            baseline=[make_rows(home_per_step=1),make_rows(home_per_step=1)],
            candidate=[make_rows(home_per_step=5),make_rows(home_per_step=5)])
        r=self.compare_paths(old,new)
        self.assertEqual(r["verdict"],"NO_REGRESSION_FLAG")
        self.assertTrue(any("HOME frequency" in w for w in r["warnings"]))

    def test_cli_reject_corrupt_input_or_overlapping_groups(self):
        old,new=self.cohorts()
        overlap=self.run_cli(old,old)
        self.assertEqual(overlap.returncode,2)
        self.assertIn("same CSV",overlap.stderr)
        new[0].write_text("wrong,format\n",encoding="utf-8")
        bad=self.run_cli(old,new)
        self.assertEqual(bad.returncode,2)
        self.assertIn("CSV validation failed",bad.stderr)
        duplicate=self.run_cli(old,[new[1],new[1]])
        self.assertEqual(duplicate.returncode,2)
        self.assertIn("duplicate CSV within",duplicate.stderr)
        fresh=self.add(make_rows(),"new")
        ok=self.run_cli(old,[new[1],fresh],as_json=False)
        self.assertEqual(ok.returncode,0)
        self.assertIn("NRO COHORT COMPARISON",ok.stdout)


U32_SMALL = 400_000


if __name__ == "__main__":
    unittest.main()
