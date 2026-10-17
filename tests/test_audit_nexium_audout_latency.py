"""Stage 272 synthetic controls; never substitute for actual NeXium SD."""
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_latency import HEADER,parse_latency,bind_guest_latency

def make_csv():
    rows=[HEADER,["TOTAL",-1,53*36,53*33,53,53,53,0,51000,0,0]]
    for second in range(53):
        rows.append(["SECOND",second,36,33,1,1,1,0,51000,0,0])
    out=io.StringIO(newline="")
    csv.writer(out,lineterminator="\n").writerows(rows)
    return out.getvalue().encode("ascii")

class TestLatencyHistogram(unittest.TestCase):
    def test_counts_are_calls_not_window_frequencies(self):
        report=parse_latency(make_csv())
        self.assertEqual(report["attempts"],1908)
        self.assertEqual(report["ge50ms_calls"],53)
        self.assertEqual(report["from40to50ms_calls"],53)
        self.assertEqual(report["windows"],53)
        self.assertTrue(report["measures_every_individual_blocking_call"])
        self.assertFalse(report["audible_underruns_measured"])

    def test_original_guest_sd_and_stage269_queue_are_cross_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            sd=root/"guest"/"sdmc"/"switch"/"vandal-hearts-remake"
            sd.mkdir(parents=True)
            original=sd/"audio-audout-latency-0000.csv"
            copied=root/"copied.csv"
            receipt=root/"receipt.txt"
            locations=root/"locations.txt"
            queue=root/"queue.json"
            raw=make_csv()
            original.write_bytes(raw)
            copied.write_bytes(raw)
            receipt.write_text(
                f"export_status=0\npath_present=1\nfile_size={len(raw)}\n",
                encoding="ascii")
            locations.write_text(str(original)+"\n",encoding="utf-8")
            queue.write_text(json.dumps({
                "result":"GUEST_SD_AUDOUT_TELEMETRY_CONSISTENT",
                "sd_binding":"GUEST_ORIGINAL_AND_COPY_BYTE_IDENTICAL",
                "attempts":1908,"releases":1908,"failed_attempts":0,
                "windows":53,"max_call_us":51000,
                "sd_original_sha256":"b"*64,
            })+"\n",encoding="ascii")
            def check():
                return bind_guest_latency(copied,locations,receipt,
                                          root/"guest",queue)
            report=check()
            self.assertEqual(report["attempts"],1908)
            self.assertEqual(report["ge50ms_calls"],53)
            self.assertEqual(report["sd_binding"],"ORIGINAL_SD_AND_COPY_MATCHED")
            self.assertEqual(report["original_csv_sha256"],
                             report["copied_csv_sha256"])
            # All three independent bindings are fail-closed.
            original.write_bytes(raw+b"alter")
            with self.assertRaises(ValueError):
                check()
            original.write_bytes(raw)
            receipt.write_text("export_status=0\npath_present=0\nfile_size=0\n")
            with self.assertRaises(ValueError):
                check()
            receipt.write_text(
                f"export_status=0\npath_present=1\nfile_size={len(raw)}\n")
            data=json.loads(queue.read_text())
            data["attempts"]=1909
            queue.write_text(json.dumps(data)+"\n")
            with self.assertRaises(ValueError):
                check()

    def test_row_band_tamper_rejected(self):
        raw=make_csv().replace(b"SECOND,0,36,33,1,1,1,",b"SECOND,0,36,34,1,1,1,",1)
        with self.assertRaises(ValueError):
            parse_latency(raw)

    def test_total_band_tamper_rejected(self):
        raw=make_csv().replace(b"TOTAL,-1,1908,1749,53,53,53,",b"TOTAL,-1,1908,1750,53,53,53,",1)
        with self.assertRaises(ValueError):
            parse_latency(raw)

    def test_boundary_consistency_rejected(self):
        raw=make_csv().replace(b"SECOND,0,36,33,1,1,1,0,51000,",b"SECOND,0,36,33,1,1,1,0,40000,",1)
        with self.assertRaises(ValueError):
            parse_latency(raw)

    def test_missing_second_rejected(self):
        raw=make_csv().replace(b"SECOND,1,36,",b"SECOND,3,36,",1)
        with self.assertRaises(ValueError):
            parse_latency(raw)

    def test_crlf_and_noncanonical_integer_rejected(self):
        for raw in (make_csv().replace(b"\n",b"\r\n"),
                    make_csv().replace(b"SECOND,0,36,",b"SECOND,00,36,",1)):
            with self.subTest(raw=raw[:80]):
                with self.assertRaises(ValueError):
                    parse_latency(raw)

    def test_missing_window_or_extra_column_rejected(self):
        raw=make_csv()
        with self.assertRaises(ValueError):
            parse_latency(b"\n".join(raw.split(b"\n")[:-3])+b"\n")
        with self.assertRaises(ValueError):
            parse_latency(raw.replace(b"SECOND,0,36,",b"SECOND,0,36,999,",1))

if __name__=="__main__":
    unittest.main()
