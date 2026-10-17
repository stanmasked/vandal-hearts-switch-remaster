import csv
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_nexium_audout_queue import HEADER, read_telemetry

def make_rows():
    windows = []
    for second in range(55):
        attempts = 100
        ok = 7 if second % 4 == 0 else 6
        windows.append(["SECOND", second, attempts, attempts, 0, 25000,
                        ok, 0, 0, 0, 0, 0])
    probes = sum(w[6] for w in windows)
    # 5500 attempts imply 344 probes.
    assert probes == 344, probes
    total = ["TOTAL", -1, 5500, 5500, 0, 25000,
             probes, 0, 0, 0, 0, 0]
    return [HEADER, total, *windows]

class TestAudoutSdAudit(unittest.TestCase):
    def assert_parses(self, rows, valid=True):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.csv"
            with path.open("w", newline="", encoding="ascii") as f:
                csv.writer(f, lineterminator="\n").writerows(rows)
            if valid:
                self.assertEqual(read_telemetry(path)["attempts"], 5500)
            else:
                with self.assertRaises(ValueError):
                    read_telemetry(path)

    def test_valid_long_run(self):
        self.assert_parses(make_rows())

    def test_mismatched_release_count(self):
        rows = make_rows()
        rows[2][4] = 1
        self.assert_parses(rows, False)

    def test_missing_window(self):
        rows = make_rows()
        del rows[3]
        self.assert_parses(rows, False)

    def test_probe_mismatch(self):
        rows = make_rows()
        rows[1][6] = 343
        self.assert_parses(rows, False)

    def test_queue_unavailable_is_not_an_underrun(self):
        rows = make_rows()
        rows[1][7] = rows[1][6]
        rows[1][6] = 0
        for w in rows[2:]:
            w[7] = w[6]
            w[6] = 0
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.csv"
            with path.open("w", newline="", encoding="ascii") as f:
                csv.writer(f, lineterminator="\n").writerows(rows)
            report = read_telemetry(path)
            self.assertIsNone(report["queue_min_pre_submit"])
            self.assertFalse(report["underruns_measured"])

    def test_reject_eviction(self):
        rows = make_rows()
        rows[1][10] = 1
        self.assert_parses(rows, False)

if __name__ == "__main__":
    unittest.main()
