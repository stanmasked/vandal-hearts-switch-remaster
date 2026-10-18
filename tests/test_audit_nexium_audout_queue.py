import csv
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_nexium_audout_queue import (
    HEADER, read_telemetry, bind_original_sd, bind_export_receipt
)

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

    def test_phase8_last_partial_block_has_no_ninth_attempt(self):
        # 5505 = 344 complete 16-attempt groups + a final single
        # attempt. Actual phase8 service queries = 344, not phase0's
        # 345. An off-by-one must fail the default legacy phase0 audit.
        rows = make_rows()
        rows[-1][2] += 5
        rows[-1][3] += 5
        rows[1][2] += 5
        rows[1][3] += 5
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"phase8-5505.csv"
            with path.open("w",newline="",encoding="ascii") as out:
                csv.writer(out,lineterminator="\n").writerows(rows)
            from audit_nexium_audout_queue import parse_telemetry
            raw=path.read_bytes()
            self.assertEqual(parse_telemetry(raw,phase=8)["attempts"],5505)
            with self.assertRaisesRegex(ValueError,"expected 1/16"):
                parse_telemetry(raw,phase=0)
            for invalid in (-1,16,True,8.0):
                with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                    parse_telemetry(raw,phase=invalid)

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

    def test_bind_captured_original_and_copy(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            sd = root / "guest" / "sdmc" / "switch" / "vandal-hearts-remake"
            sd.mkdir(parents=True)
            original = sd / "audio-audout-queue-0000.csv"
            with original.open("w", newline="", encoding="ascii") as f:
                csv.writer(f, lineterminator="\n").writerows(make_rows())
            copy = root / "soak-audout-sd-unverified.csv"
            shutil.copyfile(original, copy)
            locations = root / "soak-audout-sd-locations.txt"
            locations.write_text(str(original) + "\n", encoding="utf-8")
            raw, binding = bind_original_sd(copy, locations, root / "guest")
            self.assertEqual(raw, original.read_bytes())
            self.assertEqual(binding["sd_copy_sha256"],
                             hashlib.sha256(raw).hexdigest())
            self.assertEqual(binding["sd_original_name"], original.name)
            self.assertEqual(binding["sd_copy_bytes"], len(raw))
            self.assertEqual(read_telemetry(original)["attempts"], 5500)
            # Copied bytes cannot silently replace the guest original.
            copy.write_bytes(raw[:-1] + b"X")
            with self.assertRaises(ValueError):
                bind_original_sd(copy, locations, root / "guest")
            copy.write_bytes(raw)
            locations.write_text(str(copy) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                bind_original_sd(copy, locations, root / "guest")
            locations.write_text(str(original) + "\n", encoding="utf-8")
            extra = sd / "audio-audout-queue-0001.csv"
            shutil.copyfile(original, extra)
            with self.assertRaises(ValueError):
                bind_original_sd(copy, locations, root / "guest")
            extra.unlink()
            copy.unlink()
            copy.symlink_to(original)
            with self.assertRaises(ValueError):
                bind_original_sd(copy, locations, root / "guest")

    def test_reject_hardlink_or_noncanonical_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            capture = root / "capture.csv"
            with capture.open("w", newline="", encoding="ascii") as f:
                csv.writer(f, lineterminator="\n").writerows(make_rows())
            alternate = root / "alias.csv"
            alternate.hardlink_to(capture)
            with self.assertRaises(ValueError):
                read_telemetry(capture)
            alternate.unlink()
            capture.write_bytes(capture.read_bytes().replace(b"\n", b"\r\n"))
            with self.assertRaises(ValueError):
                read_telemetry(capture)

    def test_guest_export_receipt_binds_file_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "export-result.txt"
            path.write_bytes(b"export_status=0\npath_present=1\nfile_size=101\n")
            result = bind_export_receipt(path, 101)
            self.assertEqual(result["guest_export_receipt"],
                             "GUEST_WRITER_SUCCEEDED_AND_STAT_VISIBLE")
            for forged in [
                b"export_status=-6\npath_present=0\nfile_size=0\n",
                b"export_status=0\npath_present=1\nfile_size=100\n",
                b"export_status=0\npath_present=1\nfile_size=101\nextra=1\n",
                b"export_status=0\r\npath_present=1\r\nfile_size=101\r\n",
            ]:
                path.write_bytes(forged)
                with self.assertRaises(ValueError):
                    bind_export_receipt(path, 101)

if __name__ == "__main__":
    unittest.main()
