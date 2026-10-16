#!/usr/bin/env python3
"""Stage 210: independent C export processes -> SD staging recovery ->
numbered CSVs -> strict Python analyzer -> comparative NRO report.
No SD hardware, copyrighted game assets or live console involved.
"""
from __future__ import annotations

import hashlib
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


class ExportRestartRoundtrip(unittest.TestCase):
    def test_four_restarts_with_interrupted_temporary_file(self):
        program=ROOT / "build" / "switch_audio_export_session"
        self.assertTrue(program.is_file(), "compile C export harness first")
        with tempfile.TemporaryDirectory(prefix="vh-210-restart-") as directory:
            folder=Path(directory)
            def invoke(kind: str) -> str:
                p=subprocess.run(
                    [str(program),"--directory",str(folder),kind],
                    text=True,capture_output=True,check=True,
                )
                return p.stdout.strip()
            clean_paths=[]
            fault_paths=[]

            first=Path(invoke("clean"))
            clean_paths.append(first)
            self.assertEqual(first.name,"audio-diagnostics-0000.csv")
            previous_data=first.read_bytes()
            first_digest=hashlib.sha256(previous_data).hexdigest()
            rows=analyzer.load_csv(first)
            self.assertEqual(len(rows),21)
            self.assertEqual(rows[0]["event"],"START")
            self.assertEqual(rows[-1]["event"],"EXIT")
            self.assertEqual(rows[-1]["output_pages"],2400)
            self.assertEqual(rows[-1]["home_resumes"],40)

            # Mid-write "power loss" leaves non-CSV data in .tmp;
            # it must never be promoted, parsed or replace the old
            # committed CSV on the NEXT independent process run.
            aborted=invoke("interrupted")
            self.assertIn("INTERRUPTED",aborted)
            temporary=folder/"audio-diagnostics.tmp"
            self.assertTrue(temporary.exists())
            with self.assertRaises(analyzer.LogFormatError):
                analyzer.load_csv(temporary)
            self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(),
                             first_digest)
            second=Path(invoke("clean"))
            clean_paths.append(second)
            self.assertEqual(second.name,"audio-diagnostics-0001.csv")
            self.assertFalse(temporary.exists())
            self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(),
                             first_digest)
            self.assertEqual(second.read_bytes(),previous_data)

            third=Path(invoke("faulty"))
            fourth=Path(invoke("faulty"))
            fault_paths.extend([third,fourth])
            self.assertEqual(
                [p.name for p in (*clean_paths,*fault_paths)],
                [f"audio-diagnostics-{i:04d}.csv" for i in range(4)],
            )
            self.assertEqual(len(set(map(str,(*clean_paths,*fault_paths)))),4)
            self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(),
                             first_digest)
            self.assertFalse(temporary.exists())
            for p in (*clean_paths,*fault_paths):
                self.assertEqual(p.stat().st_size > 200,True)
                r=analyzer.summarize(analyzer.load_csv(p))
                self.assertEqual(r["observed_counter_increments"]["output_pages"],2400)
                self.assertEqual(r["observed_counter_increments"]["home_resumes"],40)
                self.assertEqual(r["historical_gaps"],0)
                self.assertEqual(r["time_rollbacks"],0)
                self.assertEqual(r["counter_rollbacks"],{})
                self.assertEqual(r["ack_latency_us"]["recorded_samples"],20)
                self.assertEqual(r["assessment"],
                                 "NO_OBSERVED_FAULTS" if p in clean_paths
                                 else "INVESTIGATE")
            for p in fault_paths:
                r=analyzer.summarize(analyzer.load_csv(p))
                self.assertEqual(r["observed_counter_increments"]["pcm_fail"],5)
                self.assertEqual(r["observed_counter_increments"]["home_fail"],2)
                self.assertEqual(r["ack_latency_us"]["p95"],95000)

            baseline=comparator.group(clean_paths)
            candidate=comparator.group(fault_paths)
            self.assertFalse(baseline["quality_problems"])
            self.assertFalse(candidate["quality_problems"])
            self.assertEqual(baseline["counters"]["output_pages"],4800)
            self.assertEqual(candidate["counters"]["output_pages"],4800)
            self.assertEqual(candidate["counters"]["pcm_fail"],10)
            self.assertEqual(candidate["counters"]["home_fail"],4)
            self.assertEqual(baseline["counters"]["home_resumes"],80)
            self.assertEqual(candidate["counters"]["home_resumes"],80)
            self.assertEqual(comparator.compare(baseline,baseline)["verdict"],
                             "NO_REGRESSION_FLAG")
            report=comparator.compare(baseline,candidate)
            self.assertEqual(report["verdict"],"POTENTIAL_REGRESSION")
            self.assertEqual(set(report["flags"]),
                             {"pcm_fail","home_fail","ack_latency_p95_us"})
            cli=ROOT/"tools"/"compare_switch_audio_sessions.py"
            cmd=[sys.executable,str(cli),"--baseline",
                 *map(str,clean_paths),"--candidate",
                 *map(str,fault_paths),"--baseline-version","run-1",
                 "--candidate-version","run-2","--format","json"]
            proc=subprocess.run(cmd,text=True,capture_output=True)
            self.assertEqual(proc.returncode,1,proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["verdict"],
                             "POTENTIAL_REGRESSION")
            # Only four COMPLETE CSVs qualify as prior sessions.
            self.assertEqual(len(list(folder.glob("*.csv"))),4)
            print("4 NRO-style export processes PASS; stale .tmp recovered; "
                  "four numbered CSVs validated; 4800 pages per cohort; "
                  "injected error/latency comparison detected")


if __name__ == "__main__":
    unittest.main()
