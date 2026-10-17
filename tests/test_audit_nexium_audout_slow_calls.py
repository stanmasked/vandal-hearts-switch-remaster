"""Stage274: exact slow-call timestamps must match every independent bin."""
from __future__ import annotations
import csv
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_slow_calls import (
    CAP,HEADER,CorrelationError,parse_slow,relate,audit
)
from audit_nexium_audout_latency import parse_latency
from audit_nexium_audout_scene_correlation import audit as audit_clock
from test_audit_nexium_audout_latency import make_csv
from test_audit_nexium_audout_scene_correlation import clock,scene


ORIGIN=1_130_000_000

def slow_rows():
    output=[HEADER,["TOTAL",-1,0,0,0,0,0,106,0]]
    for second in range(53):
        for ordinal,(offset,duration) in enumerate((
            (100_000_000,45_000_000),(900_000_000,51_000_000)
        )):
            start=ORIGIN+second*1_000_000_000+offset
            attempt=second*36+(7 if ordinal==0 else 20)
            output.append([
                "CALL",len(output)-2,attempt,start,start+duration,
                duration,1,0,0
            ])
    txt=io.StringIO(newline="")
    csv.writer(txt,lineterminator="\n").writerows(output)
    return txt.getvalue().encode("ascii")


class TestExactSlowCalls(unittest.TestCase):
    def setUp(self):
        self.raw=slow_rows()
        self.latency=parse_latency(make_csv())

    def test_exact_counts_and_call_offsets(self):
        calls=parse_slow(self.raw,ORIGIN,self.latency)
        self.assertEqual(len(calls),106)
        self.assertEqual(sum(c["duration_ns"]>=50_000_000 for c in calls),53)
        self.assertEqual(calls[0]["audio_second"],0)
        self.assertEqual(calls[-1]["audio_second"],52)
        self.assertEqual(calls[0]["attempt"],7)
        self.assertEqual(calls[-1]["attempt"],52*36+20)
        # Relative to synthetic INPUT, one call ends before and
        # one begins after the same time within a 500 ms range.
        inputs=[{"serial":1,"scene":2,
                 "timestamp_ns":ORIGIN+7*1_000_000_000+520_000_000}]
        observations=relate(calls,inputs*10)
        self.assertEqual(observations[0]["fully_ended_before_input"],1)
        self.assertEqual(observations[0]["began_after_input"],1)
        self.assertEqual(observations[0]["straddled_input"],0)
        self.assertEqual(observations[0]["slow_calls_start_within_500ms"],2)

    def test_integrity_tampering_fails(self):
        raw=self.raw
        replacements=(
            (b"TOTAL,-1,0,0,0,0,0,106,0",b"TOTAL,-1,0,0,0,0,0,105,0"),
            (b"TOTAL,-1,0,0,0,0,0,106,0",b"TOTAL,-1,0,0,0,0,0,106,1"),
            (b"CALL,0,7,",b"CALL,1,7,"),
            (b",45000000,1,0,0\n",b",44999999,1,0,0\n"),
            (b"CALL,0,7,",b"CALL,0,43,"),
            (b"CALL,0,7,",b"CALL,0,7,"),
        )
        for i,(old,new) in enumerate(replacements):
            if old==new: continue
            with self.subTest(i=i):
                with self.assertRaises(CorrelationError):
                    parse_slow(raw.replace(old,new,1),ORIGIN,self.latency)
        with self.assertRaises(CorrelationError):
            parse_slow(raw+b"x",ORIGIN,self.latency)
        with self.assertRaises(CorrelationError):
            parse_slow(raw.replace(b"\n",b"\r\n"),ORIGIN,self.latency)
        with self.assertRaises(CorrelationError):
            parse_slow(raw,ORIGIN+500_000_000,self.latency)

    def test_maximum_and_per_second_bin_mismatch_fail(self):
        mutated=self.raw.replace(b"51000000,1,0,0\n",b"50000000,1,0,0\n",1)
        with self.assertRaises(CorrelationError):
            parse_slow(mutated,ORIGIN,self.latency)
        broken=parse_latency(make_csv())
        broken["per_second_call_bands"][0]["ge50ms"]=0
        with self.assertRaises(CorrelationError):
            parse_slow(self.raw,ORIGIN,broken)
        broken=parse_latency(make_csv())
        broken["from40to50ms_calls"]=52
        with self.assertRaises(CorrelationError):
            parse_slow(self.raw,ORIGIN,broken)

    def test_original_sd_chain_and_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            sd=root/"guest"/"sdmc"/"switch"/"vandal-hearts-remake"
            sd.mkdir(parents=True)
            clock_src=sd/"audio-audout-clock-0000.csv"
            clock_src.write_bytes(clock())
            clock_copy=root/"clock.csv"
            clock_copy.write_bytes(clock())
            clock_location=root/"clock-locations.txt"
            clock_location.write_text(str(clock_src)+"\n",encoding="utf-8")
            clock_receipt=root/"clock-receipt.txt"
            clock_receipt.write_text(
                f"export_status=0\npath_present=1\nfile_size={len(clock())}\n")
            original_slow=sd/"audio-audout-slow-0000.csv"
            original_slow.write_bytes(self.raw)
            copied_slow=root/"copied-slow.csv"
            copied_slow.write_bytes(self.raw)
            locations=root/"slow-locations.txt"
            locations.write_text(str(original_slow)+"\n",encoding="utf-8")
            slow_receipt=root/"slow-receipt.txt"
            slow_receipt.write_text(
                f"export_status=0\npath_present=1\nfile_size={len(self.raw)}\n")
            latency_file=root/"latency.csv"
            latency_file.write_bytes(make_csv())
            trace=scene()
            (sd/"audio-scene-trace-0000.csv").write_bytes(trace)
            scene_file=root/"scene.csv"
            scene_file.write_bytes(trace)
            sh=hashlib.sha256(trace).hexdigest()
            lh=hashlib.sha256(make_csv()).hexdigest()
            scene_audit=root/"scene-verified.json"
            scene_audit.write_text(json.dumps({
                "result":"TEN_GUEST_SCENE_TRANSITIONS_DUAL_TRANSPORT_VERIFIED",
                "guest_csv_sha256":sh,"guest_sd_csv_sha256":sh,
                "guest_event_rows":53,"hardware_status":"HARDWARE NOT TESTED",
                "guest_nro_sha256":"a"*64,
            })+"\n")
            latency_audit=root/"latency-verified.json"
            latency_audit.write_text(json.dumps({
                "result":"GUEST_AUDOUT_PER_CALL_BANDS_VERIFIED",
                "sd_binding":"ORIGINAL_SD_AND_COPY_MATCHED",
                "copied_csv_sha256":lh,
                "attempts":1908,
                "queue_stage269_csv_sha256":"b"*64
            })+"\n")
            queue_audit=root/"queue-verified.json"
            queue_audit.write_text(json.dumps({
                "result":"GUEST_SD_AUDOUT_TELEMETRY_CONSISTENT",
                "attempts":1908,"windows":53,
                "sd_copy_sha256":"b"*64
            })+"\n")
            earlier_kwargs=dict(
                clock_csv=clock_copy,clock_locations=clock_location,
                clock_receipt=clock_receipt,latency_csv=latency_file,
                latency_verification=latency_audit,
                scene_csv=scene_file,scene_verification=scene_audit,
                queue_verification=queue_audit,sd_root=root/"guest"
            )
            prev=root/"stage273.json"
            prev.write_text(json.dumps(audit_clock(**earlier_kwargs))+"\n")
            args=dict(slow_csv=copied_slow,slow_locations=locations,
                      slow_receipt=slow_receipt,
                      previous_correlation=prev,**earlier_kwargs)
            report=audit(**args)
            self.assertEqual(report["slow_calls_captured"],106)
            self.assertEqual(report["slow_ge50ms_count"],53)
            self.assertFalse(report["scene_to_slow_call_causality_proven"])
            self.assertTrue(report["exact_call_order_relative_to_guest_input_known"])
            original_slow.write_bytes(self.raw+b"tamper")
            with self.assertRaises(CorrelationError):
                audit(**args)
            original_slow.write_bytes(self.raw)
            prev.write_text("{}\n")
            with self.assertRaises(CorrelationError):
                audit(**args)
            prev.write_text(json.dumps(audit_clock(**earlier_kwargs))+"\n")
            slow_receipt.write_text("export_status=0\npath_present=0\nfile_size=0\n")
            with self.assertRaises(ValueError):
                audit(**args)


if __name__=="__main__":
    unittest.main()
