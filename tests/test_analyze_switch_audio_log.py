#!/usr/bin/env python3
"""Host-only regressions for the exact Switch 18-column exported CSV."""
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


def snapshot(ms=0, event="START", status=1, **overrides):
    item = {column: 0 for column in analyzer.COLUMNS}
    item.update({"elapsed_ms": ms, "event": event, "status": status})
    item.update(overrides)
    return item


def write_csv(path, rows, header=None):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(header if header is not None else analyzer.COLUMNS)
        for row in rows:
            writer.writerow([row.get(c, 0) for c in analyzer.COLUMNS])


class AudioJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "audio-diagnostics.csv"

    def report(self, rows):
        write_csv(self.path, rows)
        return analyzer.summarize(analyzer.load_csv(self.path))

    def test_retained_baseline_never_counted_as_incident(self):
        r = self.report([
            snapshot(100000, "PERIODIC", home_resumes=90, output_pages=5000,
                     pcm_fail=12, first_pcm_count=6, last_pcm_us=12000,
                     worst_pcm_us=17000),
            snapshot(105000, "PERIODIC", home_resumes=90, output_pages=5030,
                     pcm_fail=12, first_pcm_count=6, last_pcm_us=12000,
                     worst_pcm_us=17000),
            snapshot(107000, "RESUME", home_resumes=91, output_pages=5033,
                     pcm_fail=12, first_pcm_count=7, last_pcm_us=14500,
                     worst_pcm_us=17000),
            snapshot(110000, "EXIT", status=0, home_resumes=91,
                     output_pages=5040, pcm_fail=12, first_pcm_count=7,
                     last_pcm_us=14500, worst_pcm_us=17000),
        ])
        self.assertEqual(r["observed_counter_increments"]["home_resumes"], 1)
        self.assertEqual(r["observed_counter_increments"]["output_pages"], 40)
        self.assertEqual(r["observed_counter_increments"]["pcm_fail"], 0)
        self.assertEqual(r["ack_latency_us"]["recorded_samples"], 1)
        self.assertEqual(r["ack_latency_us"]["median"], 14500)
        self.assertEqual(r["assessment"], "NO_OBSERVED_FAULTS")
        self.assertEqual(r["observed_elapsed_ms"], 10000)
        self.assertIn("Beginning of the session", " ".join(r["warnings"]))

    def test_multiple_fault_bursts_with_stall(self):
        r = self.report([
            snapshot(0),
            snapshot(1000, "ERROR", pcm_fail=1, output_pages=20),
            snapshot(3000, "ERROR", pcm_fail=2, home_fail=1,
                     output_pages=25),
            snapshot(4000, "RESUME", pcm_fail=2, home_fail=1,
                     pcm_recover=2, home_recover=1, output_pages=26),
            snapshot(80000, "ERROR", pcm_fail=3, home_fail=1,
                     output_pages=30),
            snapshot(100000, "PERIODIC", pcm_fail=3, home_fail=1,
                     output_pages=30),
            snapshot(101000, "EXIT", status=0, pcm_fail=3, home_fail=1,
                     output_pages=30),
        ])
        self.assertEqual(r["assessment"], "INVESTIGATE")
        self.assertEqual(len(r["fault_clusters_60s"]), 2)
        self.assertEqual(r["repeated_fault_clusters_60s"], 1)
        self.assertEqual(r["fault_clusters_60s"][0]["total_increments"], 3)
        self.assertEqual(r["observed_counter_increments"]["pcm_fail"], 3)
        self.assertEqual(r["observed_counter_increments"]["home_fail"], 1)
        self.assertEqual(r["observed_counter_increments"]["pcm_recover"], 2)
        self.assertEqual(len(r["possible_output_stalls"]), 1)
        self.assertEqual(r["possible_output_stalls"][0]["start_ms"], 80000)
        self.assertEqual(r["possible_output_stalls"][0]["end_ms"], 100000)

    def test_confirmed_buffer_latency_is_not_speaker_timing(self):
        r = self.report([
            snapshot(0, first_pcm_count=12, last_pcm_us=400000,
                     worst_pcm_us=400000),
            snapshot(1000, "RESUME", first_pcm_count=13,
                     last_pcm_us=51000, worst_pcm_us=400000),
            snapshot(2000, "RESUME", first_pcm_count=15,
                     last_pcm_us=120000, worst_pcm_us=400000),
            snapshot(3000, "RESUME", first_pcm_count=16,
                     last_pcm_us=25000, worst_pcm_us=400000),
            snapshot(4000, "EXIT", status=0, first_pcm_count=16,
                     last_pcm_us=25000, worst_pcm_us=400000),
        ])
        m = r["ack_latency_us"]
        self.assertEqual(m["recorded_samples"], 3)
        self.assertEqual(m["missing_individual_samples"], 1)
        self.assertEqual(m["median"], 51000)
        self.assertEqual(m["p95"], 120000)
        self.assertEqual(m["over_50ms"], 2)
        self.assertEqual(m["over_100ms"], 1)
        self.assertEqual(m["max_reported_cumulative"], 400000)
        self.assertEqual(r["assessment"], "REVIEW")
        self.assertIn("Not every confirmed", " ".join(r["warnings"]))

    def test_early_evicted_faults_keep_counts_but_not_fake_timing(self):
        # Stage 208 exporter reserves START + oldest GAP + 126 latest
        # rows, preserving lifetime deltas without inventing the dates
        # of the incidents evicted by the ring.
        records = [snapshot(0, "START")]
        records.append(snapshot(900000, "GAP", pcm_fail=17,
                                home_fail=5, lease_fail=3,
                                output_pages=60000, first_pcm_count=22,
                                last_pcm_us=15000, worst_pcm_us=140000))
        for i in range(2, 128):
            records.append(snapshot(900000 + i * 5000,
                                    "EXIT" if i == 127 else "PERIODIC",
                                    status=0 if i == 127 else 1,
                                    pcm_fail=17, home_fail=5, lease_fail=3,
                                    output_pages=60000 + i * 100,
                                    first_pcm_count=22, last_pcm_us=15000,
                                    worst_pcm_us=140000))
        r = self.report(records)
        self.assertEqual(r["rows"], 128)
        self.assertEqual(r["historical_gaps"], 1)
        self.assertEqual(r["assessment"], "INVESTIGATE")
        self.assertEqual(r["unlocalized_faults"],
                         {"pcm_fail": 17, "home_fail": 5, "lease_fail": 3})
        self.assertEqual(r["observed_counter_increments"]["pcm_fail"], 17)
        self.assertEqual(r["observed_counter_increments"]["home_fail"], 5)
        self.assertEqual(r["observed_counter_increments"]["lease_fail"], 3)
        self.assertEqual(r["fault_clusters_60s"], [])
        self.assertEqual(r["repeated_fault_clusters_60s"], 0)
        self.assertEqual(r["ack_latency_us"]["recorded_samples"], 0)
        self.assertEqual(r["ack_latency_us"]["missing_individual_samples"], 22)
        self.assertEqual(r["time_rollbacks"], 0)
        self.assertTrue(any("GAP" in w for w in r["warnings"]))

    def test_gap_does_not_create_false_long_stall(self):
        r = self.report([
            snapshot(0, "START", status=1, output_pages=250),
            snapshot(1000000, "GAP", status=1, output_pages=250,
                     pcm_fail=5),
            snapshot(1000100, "EXIT", status=0, output_pages=251,
                     pcm_fail=5),
        ])
        self.assertEqual(r["possible_output_stalls"], [])
        self.assertEqual(r["unlocalized_faults"]["pcm_fail"], 5)
        self.assertEqual(r["assessment"], "INVESTIGATE")

    def test_clock_rollback_is_separate_from_counter_rollback(self):
        r = self.report([
            snapshot(50000, "PERIODIC", pcm_fail=10, output_pages=100),
            snapshot(51000, "ERROR", pcm_fail=11, output_pages=120),
            snapshot(100, "CLOCK", pcm_fail=0, output_pages=0),
            snapshot(200, "ERROR", pcm_fail=1, output_pages=20),
            snapshot(300, "EXIT", status=0, pcm_fail=1, output_pages=25),
        ])
        self.assertIsNone(r["observed_elapsed_ms"])
        self.assertEqual(r["time_rollbacks"], 1)
        self.assertEqual(r["counter_rollbacks"]["pcm_fail"], 1)
        self.assertEqual(r["counter_rollbacks"]["output_pages"], 1)
        self.assertEqual(r["observed_counter_increments"]["pcm_fail"], 2)
        self.assertEqual(len(r["fault_clusters_60s"]), 2)

    def test_negative_terminal_state_without_explicit_error_row(self):
        r = self.report([
            snapshot(0),
            snapshot(1000, "STATE", status=-8),
        ])
        self.assertEqual(r["error_status_entries"], 1)
        self.assertEqual(r["assessment"], "INVESTIGATE")
        self.assertIn("No EXIT", " ".join(r["warnings"]))

    def test_limit_128_rows_and_column_order(self):
        rows = [snapshot(i * 5000, "PERIODIC") for i in range(128)]
        rows[0]["event"] = "START"
        rows[-1]["event"] = "EXIT"
        r = self.report(rows)
        self.assertEqual(r["rows"], 128)
        write_csv(self.path, rows + [snapshot(999999, "EXIT")])
        with self.assertRaisesRegex(analyzer.LogFormatError, "128"):
            analyzer.load_csv(self.path)
        write_csv(self.path, rows[:1], header=list(reversed(analyzer.COLUMNS)))
        with self.assertRaisesRegex(analyzer.LogFormatError, "header"):
            analyzer.load_csv(self.path)

    def test_reject_bad_values_and_non_clock_timestamp_rewinds(self):
        base = snapshot(20)
        cases = [
            [snapshot(20), snapshot(19, "RESUME")],
            [dict(base, event="UNKNOWN")],
            [dict(base, pcm_fail="-1")],
            [dict(base, output_pages=str(1 << 64))],
            [dict(base, home_resumes=str(1 << 32))],
            [dict(base, status="-2147483649")],
            [dict(base, status="1.5")],
            [dict(base, elapsed_ms="")],
            [dict(base, event="START,FORMULA")],
            [dict(base, home_fail="=1+1")],
        ]
        for rows in cases:
            with self.subTest(rows=rows):
                write_csv(self.path, rows)
                with self.assertRaises(analyzer.LogFormatError):
                    analyzer.load_csv(self.path)
        self.path.write_bytes(b"x" * (analyzer.BYTES_LIMIT + 1))
        with self.assertRaisesRegex(analyzer.LogFormatError, "large"):
            analyzer.load_csv(self.path)

    def test_single_and_multi_file_cli_json_and_text(self):
        write_csv(self.path, [
            snapshot(0, output_pages=1000),
            snapshot(5000, "EXIT", status=0, output_pages=1120),
        ])
        tool = ROOT / "tools" / "analyze_switch_audio_log.py"
        cmd = [sys.executable, str(tool), "--format", "json", str(self.path)]
        output = subprocess.run(cmd, text=True, capture_output=True, check=True)
        result = json.loads(output.stdout)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["observed_counter_increments"]["output_pages"], 120)
        report = subprocess.run([sys.executable, str(tool), str(self.path)],
                                text=True, capture_output=True, check=True)
        self.assertIn("NO_OBSERVED_FAULTS", report.stdout)
        double = subprocess.run(cmd + [str(self.path)], text=True,
                                capture_output=True, check=True)
        self.assertEqual(len(json.loads(double.stdout)), 2)
        self.path.write_text("not,a,switch,log\n", encoding="utf-8")
        failure = subprocess.run(cmd, text=True, capture_output=True)
        self.assertEqual(failure.returncode, 2)
        self.assertIn("unexpected CSV header", failure.stderr)


if __name__ == "__main__":
    unittest.main()
