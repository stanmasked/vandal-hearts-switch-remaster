#!/usr/bin/env python3
"""Stage 207: long HOME/sleep C audio -> bounded CSV -> cohort regression.

Unlike stage 206 (512 PCM pages / deliberately inconclusive), this runs
2048 confirmed output pages per session with sparse recoverable errors
to preserve the ENTIRE observed period in the 128-row ring.
Four sessions (two clean and two fault-injected) are independently run.
Synthetic PCM and counter timings are NOT Switch hardware measurements.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import analyze_switch_audio_log as analyzer  # noqa: E402
import compare_switch_audio_sessions as comparator  # noqa: E402

BLOCKS = 2048
HOME_PAUSES = 10
HOME_SERIALS = HOME_PAUSES // 2
START_FAILURES = 2
SUBMIT_FAILURES = 7
HOME_DURATION_MS = BLOCKS * 12 + 1


class LongSwitchCohort(unittest.TestCase):
    def test_clean_reference_and_faulty_cohort_with_sufficient_exposure(self):
        fixture = ROOT / "build" / "test_vh_music_lifecycle_soak"
        self.assertTrue(fixture.is_file(), "compile C lifecycle soak first")
        cli = ROOT / "tools" / "compare_switch_audio_sessions.py"
        with tempfile.TemporaryDirectory(prefix="vh-long-cohort-") as folder:
            clean, faulty = [], []
            for iteration in range(2):
                prefix = Path(folder) / f"independent-session-{iteration}"
                result = subprocess.run(
                    [str(fixture), "--long-csv-prefix", str(prefix)],
                    check=True, capture_output=True, text=True,
                )
                self.assertIn("2048 blocks, 10 pauses", result.stdout)
                self.assertIn("2 resume start faults", result.stdout)
                self.assertIn("7 PCM retries PASS", result.stdout)
                for name, dest in (("clean", clean), ("fault", faulty)):
                    file = Path(f"{prefix}-{name}.csv")
                    rows = analyzer.load_csv(file)
                    self.assertGreater(len(rows), 2)
                    self.assertLessEqual(len(rows), 128)
                    self.assertEqual(rows[0]["event"], "START")
                    self.assertEqual(rows[-1]["event"], "EXIT")
                    self.assertEqual(rows[-1]["output_pages"], BLOCKS)
                    self.assertEqual(rows[-1]["first_pcm_count"], HOME_PAUSES)
                    self.assertEqual(rows[-1]["home_resumes"], HOME_SERIALS)
                    self.assertEqual(rows[-1]["elapsed_ms"], HOME_DURATION_MS)
                    self.assertEqual(rows[-1]["pcm_fail"], 0 if name == "clean" else SUBMIT_FAILURES)
                    self.assertEqual(rows[-1]["home_fail"], 0 if name == "clean" else START_FAILURES)
                    self.assertEqual(rows[-1]["last_pcm_us"], 12000)
                    report = analyzer.summarize(rows)
                    self.assertEqual(report["observed_counter_increments"]["output_pages"], BLOCKS)
                    self.assertEqual(report["observed_counter_increments"]["home_resumes"], HOME_SERIALS)
                    self.assertFalse(report["counter_rollbacks"])
                    self.assertEqual(report["time_rollbacks"], 0)
                    self.assertEqual(report["observed_elapsed_ms"], HOME_DURATION_MS)
                    self.assertEqual(report["assessment"],
                                     "NO_OBSERVED_FAULTS" if name == "clean" else "INVESTIGATE")
                    dest.append(file)

            clean_group = comparator.group(clean)
            faulty_group = comparator.group(faulty)
            self.assertEqual(clean_group["count"], 2)
            self.assertEqual(faulty_group["count"], 2)
            self.assertEqual(clean_group["quality_problems"], [])
            self.assertEqual(faulty_group["quality_problems"], [])
            self.assertEqual(clean_group["counters"]["output_pages"], 4096)
            self.assertEqual(faulty_group["counters"]["output_pages"], 4096)
            self.assertEqual(clean_group["counters"]["home_resumes"], 10)
            self.assertEqual(faulty_group["counters"]["home_resumes"], 10)
            self.assertEqual(faulty_group["counters"]["pcm_fail"], 14)
            self.assertEqual(faulty_group["counters"]["home_fail"], 4)
            self.assertEqual(faulty_group["counters"]["pcm_recover"], 10)
            self.assertEqual(faulty_group["counters"]["home_recover"], 4)
            self.assertEqual(clean_group["latency"]["sample_count"], 20)
            self.assertEqual(faulty_group["latency"]["sample_count"], 20)
            self.assertEqual(clean_group["truncated_windows"], 0)
            self.assertEqual(faulty_group["truncated_windows"], 0)

            # Clean-vs-clean runs have no flag; the "different sessions"
            # requirement is maintained because both CSVs were created
            # by separate process executions.
            stable = comparator.compare(clean_group, clean_group)
            self.assertEqual(stable["verdict"], "NO_REGRESSION_FLAG")
            self.assertTrue(stable["metrics"]["pcm_fail"]["comparable"])
            self.assertTrue(stable["metrics"]["home_fail"]["comparable"])
            self.assertTrue(stable["metrics"]["ack_latency_p95_us"]["comparable"])
            self.assertEqual(stable["flags"], [])

            degraded = comparator.compare(clean_group, faulty_group)
            self.assertEqual(degraded["verdict"], "POTENTIAL_REGRESSION")
            self.assertIn("pcm_fail", degraded["flags"])
            self.assertIn("home_fail", degraded["flags"])
            self.assertNotIn("ack_latency_p95_us", degraded["flags"])
            self.assertTrue(degraded["metrics"]["pcm_fail"]["comparable"])
            self.assertTrue(degraded["metrics"]["home_fail"]["comparable"])
            self.assertTrue(degraded["metrics"]["ack_latency_p95_us"]["comparable"])

            # Exercise the actual command-line contract / exit status.
            args = [
                "--baseline", *map(str, clean),
                "--candidate", *map(str, faulty),
                "--baseline-version", "host-clean",
                "--candidate-version", "host-injected",
                "--format", "json",
            ]
            run = subprocess.run([sys.executable, str(cli), *args],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 1, run.stderr)
            output = json.loads(run.stdout)
            self.assertEqual(output["verdict"], "POTENTIAL_REGRESSION")
            self.assertEqual(output["versions"]["candidate"], "host-injected")
            self.assertEqual(output["candidate"]["counters"]["pcm_fail"], 14)
            print("LONG HOME/PCM COHORT PASS: four 2048-page sessions; "
                  "10 HOME resumes per pair; 14 injected PCM and 4 HOME "
                  "failures; clean NO_REGRESSION_FLAG and injected "
                  "POTENTIAL_REGRESSION correctly classified")


if __name__ == "__main__":
    unittest.main()
