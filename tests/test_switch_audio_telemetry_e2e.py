#!/usr/bin/env python3
"""Integration: synthetic SEQ/SPU/HOME audio owner -> Switch C CSV ring ->
strict Python analyzer -> cross-version comparator. No real hardware.

The diagnostic CSVs below are emitted by test_vh_music_lifecycle_soak
using actual host audio recovery counters rather than handwritten rows.
Each 512-block session deliberately falls BELOW the >=1000-pages
comparison policy; detecting faults must not create a false statistically
credible comparison. Full memory and clock invariants are asserted by C.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))
import analyze_switch_audio_log as analyze  # noqa: E402
import compare_switch_audio_sessions as compare  # noqa: E402


class LifecycleJournalEndToEnd(unittest.TestCase):
    def test_audio_owner_csv_to_comparison(self):
        binary=ROOT / "build" / "test_vh_music_lifecycle_soak"
        if not binary.is_file():
            self.fail("compile build/test_vh_music_lifecycle_soak first")
        with tempfile.TemporaryDirectory(prefix="vh-audio-e2e-") as directory:
            folder=Path(directory)
            clean_paths=[]
            fault_paths=[]
            for n in range(2):
                prefix=folder / f"run-{n}"
                executed=subprocess.run(
                    [str(binary),"--csv-prefix",str(prefix)],
                    capture_output=True,text=True,check=True)
                self.assertIn("512 blocks, 63 pauses",executed.stdout)
                clean=Path(f"{prefix}-clean.csv")
                faulty=Path(f"{prefix}-fault.csv")
                self.assertTrue(clean.exists() and faulty.exists())
                clean_rows=analyze.load_csv(clean)
                fault_rows=analyze.load_csv(faulty)
                self.assertLessEqual(len(clean_rows),128)
                self.assertLessEqual(len(fault_rows),128)
                self.assertGreater(len(clean_rows),50)
                self.assertGreater(len(fault_rows),50)
                for rows in (clean_rows,fault_rows):
                    self.assertEqual(rows[-1]["event"],"EXIT")
                    self.assertEqual(rows[-1]["status"],0)
                    self.assertEqual(rows[-1]["output_pages"],512)
                    self.assertEqual(rows[-1]["first_pcm_count"],63)
                    self.assertEqual(rows[-1]["home_resumes"],31)
                    self.assertEqual(rows[-1]["last_pcm_us"],12000)
                    self.assertEqual(rows[-1]["worst_pcm_us"],12000)
                    self.assertEqual(rows[-1]["pcm_restart"]>=0,True)
                baseline=analyze.summarize(clean_rows)
                candidate=analyze.summarize(fault_rows)
                self.assertEqual(clean_rows[-1]["pcm_fail"],0)
                self.assertGreater(fault_rows[-1]["pcm_fail"],0)
                self.assertEqual(baseline["observed_counter_increments"]["pcm_fail"],0)
                self.assertGreater(candidate["observed_counter_increments"]["pcm_fail"],0)
                self.assertEqual(baseline["time_rollbacks"],0)
                self.assertEqual(candidate["time_rollbacks"],0)
                self.assertFalse(baseline["counter_rollbacks"])
                self.assertFalse(candidate["counter_rollbacks"])
                self.assertEqual(baseline["assessment"],"NO_OBSERVED_FAULTS")
                self.assertEqual(candidate["assessment"],"INVESTIGATE")
                self.assertGreater(candidate["repeated_fault_clusters_60s"],0)
                self.assertGreater(candidate["observed_counter_increments"]["pcm_recover"],0)
                self.assertGreater(candidate["observed_counter_increments"]["home_reopen"],0)
                clean_paths.append(clean)
                fault_paths.append(faulty)
            groups=compare.compare(compare.group(clean_paths),
                                   compare.group(fault_paths))
            self.assertEqual(groups["verdict"],"INCONCLUSIVE")
            self.assertTrue(groups["candidate"]["quality_problems"])
            self.assertTrue(groups["baseline"]["quality_problems"])
            self.assertFalse(groups["metrics"]["pcm_fail"]["comparable"])
            self.assertFalse(groups["metrics"]["pcm_fail"]["regression_flag"])
            self.assertGreater(groups["candidate"]["counters"]["pcm_fail"],0)
            self.assertEqual(groups["baseline"]["counters"]["pcm_fail"],0)
            self.assertGreater(groups["candidate"]["count"],1)
            # Validate the public CLI roundtrip, too: exit 0 is not
            # proof of audio quality when the JSON says INCONCLUSIVE.
            cli=ROOT/"tools"/"compare_switch_audio_sessions.py"
            command=[sys.executable,str(cli),"--baseline",
                     *[str(p) for p in clean_paths],"--candidate",
                     *[str(p) for p in fault_paths],
                     "--baseline-version","clean-synthetic",
                     "--candidate-version","fault-injected-synthetic",
                     "--format","json"]
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(result.stdout)
            self.assertEqual(report["verdict"],"INCONCLUSIVE")
            self.assertEqual(report["versions"]["baseline"],"clean-synthetic")
            self.assertEqual(report["versions"]["candidate"],"fault-injected-synthetic")
            print("512-block twice, 63 HOME/sleep pauses per run: "
                  "C recovery -> bounded CSV -> analyzer -> "
                  "INCONCLUSIVE comparison PASS")


if __name__ == "__main__":
    unittest.main()
