"""Synthetic stage-273 guest monotonic-clock alignment & tamper controls."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import (
    CLOCK_HEADER,CLOCK_SCHEMA,CorrelationError,parse_clock,parse_scene_inputs,
    join,audit
)
from test_audit_nexium_audout_latency import make_csv


def clock(origin=1_000_000_000, attempts=1908):
    return (CLOCK_HEADER+
            f"{CLOCK_SCHEMA},{origin},{attempts},52,0\n").encode("ascii")

def scene():
    rows=[["index","event","serial","scene","monotonic_ns","dropped_total"]]
    for kind,n,sc,t in [
        ("ACCEPT",0,1,1_100_000_000),
        ("SUBMIT_CALL",0,1,1_120_000_000),
        ("RELEASE_RETURN",0,1,1_155_000_000)
    ]:
        rows.append([len(rows)-1,kind,n,sc,t,0])
    for n in range(1,11):
        start=1_000_000_000+(3+4*n)*1_000_000_000+600_000_000
        sc=2 if n%2 else 1
        for kind,delta in [
            ("INPUT",0),("POST",1000),("ACCEPT",4_000_000),
            ("SUBMIT_CALL",5_000_000),("RELEASE_RETURN",38_000_000)
        ]:
            rows.append([len(rows)-1,kind,n,sc,start+delta,0])
    out=io.StringIO(newline="")
    csv.writer(out,lineterminator="\n").writerows(rows)
    return out.getvalue().encode("ascii")


class GuestTimeCorrelationTests(unittest.TestCase):
    def test_same_monotonic_clock_produces_ten_bounded_second_indices(self):
        anchor=parse_clock(clock())
        report=join(anchor,scene(),make_csv())
        self.assertEqual(report["result"],
                         "GUEST_CLOCK_BOUND_SCENE_AND_AUDOUT_WINDOWS")
        self.assertEqual(report["guest_scene_input_count"],10)
        self.assertEqual([e["relative_audio_second"] for e in report["scene_inputs"]],
                         [7,11,15,19,23,27,31,35,39,43])
        self.assertEqual(report["input_seconds_with_ge50ms_calls"],10)
        self.assertEqual(report["all_guest_ge50ms_calls"],53)
        self.assertTrue(report["guest_clock_alignment_proven"])
        self.assertFalse(report["individual_slow_call_start_time_known"])
        self.assertFalse(report["host_pcm_clock_alignment_proven"])
        self.assertFalse(report["audible_underruns_measured"])

    def test_one_event_precedes_audio_clock(self):
        with self.assertRaises(CorrelationError):
            join(parse_clock(clock(origin=9_000_000_000)),scene(),make_csv())

    def test_bad_anchor_rejected(self):
        for tampered in [
            clock().replace(b"origin_ns",b"event_ns"),
            clock()+b"\n",clock().replace(b",52,0\n",b",52,1\n"),
            clock(attempts=0),clock().replace(b",52,0\n",b",999,0\n"),
            clock().replace(b",52,0\n",b",052,0\n")
        ]:
            with self.subTest(tampered=tampered[:90]):
                with self.assertRaises(CorrelationError):
                    parse_clock(tampered)

    def test_tampered_scene_order_rejected(self):
        for raw in [
            scene().replace(b"INPUT,1,",b"INPUT,2,",1),
            scene().replace(b"POST,2,",b"UNTRUSTED,2,",1),
            scene().replace(b",0\n",b",1\n",1),
            scene().replace(b",dropped_total",b",altered")
        ]:
            with self.assertRaises(CorrelationError):
                parse_scene_inputs(raw)

    def test_counter_mismatch_rejected(self):
        with self.assertRaises(CorrelationError):
            join(parse_clock(clock(attempts=1909)),scene(),make_csv())

    def test_real_original_guest_clock_copy_and_prior_verdicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            sd=root/"guest"/"sdmc"/"switch"/"vandal-hearts-remake"
            sd.mkdir(parents=True)
            src=sd/"audio-audout-clock-0000.csv"
            src.write_bytes(clock())
            copied=root/"copied-clock.csv"
            copied.write_bytes(clock())
            locations=root/"clock-locations.txt"
            locations.write_text(str(src)+"\n",encoding="utf-8")
            receipt=root/"receipt.txt"
            receipt.write_text(
                f"export_status=0\npath_present=1\nfile_size={len(clock())}\n",
                encoding="ascii")
            latency_file=root/"latency.csv"
            latency_file.write_bytes(make_csv())
            scenes=scene()
            (sd/"audio-scene-trace-0000.csv").write_bytes(scenes)
            scene_file=root/"scene.csv"
            scene_file.write_bytes(scenes)
            scene_verify=root/"scene-verification.json"
            scene_verify.write_text(json.dumps({
                "result":"TEN_GUEST_SCENE_TRANSITIONS_DUAL_TRANSPORT_VERIFIED",
                "guest_csv_sha256":hashlib.sha256(scenes).hexdigest(),
                "guest_sd_csv_sha256":hashlib.sha256(scenes).hexdigest(),
                "guest_event_rows":53,
                "hardware_status":"HARDWARE NOT TESTED",
                "guest_nro_sha256":"a"*64,
            })+"\n",encoding="ascii")
            lat_verify=root/"latency-verification.json"
            queue_hash="b"*64
            lat_verify.write_text(json.dumps({
                "result":"GUEST_AUDOUT_PER_CALL_BANDS_VERIFIED",
                "sd_binding":"ORIGINAL_SD_AND_COPY_MATCHED",
                "copied_csv_sha256":hashlib.sha256(make_csv()).hexdigest(),
                "attempts":1908,
                "queue_stage269_csv_sha256":queue_hash,
            })+"\n",encoding="ascii")
            queue_verify=root/"queue-verification.json"
            queue_verify.write_text(json.dumps({
                "result":"GUEST_SD_AUDOUT_TELEMETRY_CONSISTENT",
                "attempts":1908, "windows":53, "sd_copy_sha256":queue_hash,
            })+"\n",encoding="ascii")
            args=dict(
                clock_csv=copied,clock_locations=locations,clock_receipt=receipt,
                latency_csv=latency_file,latency_verification=lat_verify,
                scene_csv=scene_file,scene_verification=scene_verify,
                queue_verification=queue_verify,sd_root=root/"guest")
            report=audit(**args)
            self.assertEqual(report["guest_clock_original_csv_sha256"],
                             hashlib.sha256(clock()).hexdigest())
            self.assertTrue(report["original_guest_sd_reopened"])
            src.write_bytes(clock(origin=2_000_000_000))
            with self.assertRaises(CorrelationError):
                audit(**args)
            src.write_bytes(clock())
            scene_file.write_bytes(scenes.replace(b"INPUT",b"INPUTX"))
            with self.assertRaises(CorrelationError):
                audit(**args)
            scene_file.write_bytes(scenes)
            receipt.write_text("export_status=0\npath_present=0\nfile_size=0\n")
            with self.assertRaises(ValueError):
                audit(**args)


if __name__=="__main__":
    unittest.main()
