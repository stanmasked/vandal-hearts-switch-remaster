"""Stage276 synthetic negative controls, never real hardware/emulator observations."""
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
from audit_nexium_audout_idle_control import CorrelationError,audit
from audit_nexium_audout_queue import HEADER as QUEUE_HEADER
from test_audit_nexium_audout_latency import make_csv
from test_audit_nexium_audout_scene_correlation import clock,scene
from test_audit_nexium_audout_slow_calls import slow_rows


def queue_csv():
    rows=[QUEUE_HEADER,["TOTAL",-1,1908,1908,0,51000,120,0,0,0,0,0]]
    for second in range(53):
        probes=((second+1)*36+15)//16-(second*36+15)//16
        rows.append(["SECOND",second,36,36,0,51000,probes,0,0,0,0,0])
    out=io.StringIO(newline="")
    csv.writer(out,lineterminator="\n").writerows(rows)
    return out.getvalue().encode("ascii")

def idle_scene():
    return b"\n".join(scene().split(b"\n")[:4])+b"\n"

class TestIdleControl(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.sd_root=self.root/"isolated"
        self.sd=self.sd_root/"sdmc"/"switch"/"vandal-hearts-remake"
        self.sd.mkdir(parents=True)
        self.evidence=self.root/"evidence"
        self.evidence.mkdir()
        self.items=[
            ("scene","audio-scene-trace-0000.csv","soak-sd-unverified.csv",
             "soak-sd-locations.txt",None,idle_scene()),
            ("queue","audio-audout-queue-0000.csv","soak-audout-sd-unverified.csv",
             "soak-audout-sd-locations.txt","soak-audout-export-result.txt",queue_csv()),
            ("latency","audio-audout-latency-0000.csv","soak-audout-latency-unverified.csv",
             "soak-audout-latency-locations.txt","soak-audout-latency-export-result.txt",make_csv()),
            ("clock","audio-audout-clock-0000.csv","soak-audout-clock-unverified.csv",
             "soak-audout-clock-locations.txt","soak-audout-clock-export-result.txt",clock()),
            ("slow","audio-audout-slow-0000.csv","soak-audout-slow-unverified.csv",
             "soak-audout-slow-locations.txt","soak-audout-slow-export-result.txt",slow_rows()),
        ]
        for kind,filename,copied,location,receipt,raw in self.items:
            original=self.sd/filename
            original.write_bytes(raw)
            (self.evidence/copied).write_bytes(raw)
            (self.evidence/location).write_text(str(original)+"\n")
            if receipt:
                (self.evidence/receipt).write_text(
                    f"export_status=0\npath_present=1\nfile_size={len(raw)}\n")
        out=io.StringIO(newline="")
        writer=csv.writer(out,lineterminator="\n")
        writer.writerow(["scene","serial","pcm_bytes","epoch_ms"])
        writer.writerow(["field_initial",0,1_000_000,1700000000])
        for i in range(1,11):
            writer.writerow([f"idle_{i}",i,1_000_000+i*960_000,1700000000+i*5_000])
        (self.evidence/"soak-events.csv").write_text(out.getvalue())
        for i in range(11):
            (self.evidence/f"soak-scene-{i:02d}.png").write_bytes(b"PNG"+b"X"*120)
        self.preflight=self.root/"preflight.json"
        self.gitsha="a"*40
        self.preflight.write_text(json.dumps({
            "result":"SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED",
            "nro_sha256":"b"*64,
            "git_sha":self.gitsha,"run_id":276,"run_attempt":1,
        })+"\n")

    def check(self):
        return audit(sd_root=self.sd_root,evidence=self.evidence,
                     preflight=self.preflight,git_sha=self.gitsha,
                     run_id=276,run_attempt=1)

    def test_original_sd_unchanged_scene_and_full_audio(self):
        result=self.check()
        self.assertEqual(result["result"],"ORIGINAL_SD_IDLE_50S_AUDOUT_VERIFIED")
        self.assertEqual(result["guest_scene_change_inputs"],0)
        self.assertEqual(result["guest_audio_second_windows"],53)
        self.assertEqual(result["slow_ge40ms_calls"],106)
        self.assertEqual(result["slow_ge50ms_calls"],53)
        self.assertEqual(result["slow_records_dropped"],0)
        self.assertFalse(result["audible_underruns_measured"])

    def test_reject_scene_switch_input(self):
        p=self.sd/"audio-scene-trace-0000.csv"
        p.write_bytes(scene())
        with self.assertRaises(CorrelationError):
            self.check()

    def test_reject_consistent_but_non_idle_guest_scene(self):
        # Even if the live original and its captured copy are
        # identically replaced, an INPUT / POST must be rejected.
        forged=scene()
        (self.sd/"audio-scene-trace-0000.csv").write_bytes(forged)
        (self.evidence/"soak-sd-unverified.csv").write_bytes(forged)
        with self.assertRaises(CorrelationError):
            self.check()

    def test_reject_consistently_rebound_startup_origin(self):
        # A matching copy is not sufficient: the independent clock
        # must still fall between startup SUBMIT_CALL/RELEASE_RETURN.
        raw=idle_scene().replace(b"1120000000",b"1400000000")
        (self.sd/"audio-scene-trace-0000.csv").write_bytes(raw)
        (self.evidence/"soak-sd-unverified.csv").write_bytes(raw)
        with self.assertRaises(CorrelationError):
            self.check()

    def test_reject_original_guest_csv_mutation_and_alias(self):
        for kind,filename,copied,location,receipt,raw in self.items:
            with self.subTest(kind=kind):
                path=self.sd/filename
                path.write_bytes(raw+b"CHANGED\n")
                with self.assertRaises(CorrelationError):
                    self.check()
                path.write_bytes(raw)
                (self.evidence/location).write_text("/tmp/not-original.csv\n")
                with self.assertRaises(CorrelationError):
                    self.check()
                (self.evidence/location).write_text(str(path)+"\n")

    def test_reject_missing_receipt_and_slow_overflow(self):
        receipt=self.evidence/"soak-audout-slow-export-result.txt"
        good=receipt.read_bytes()
        receipt.write_text("export_status=0\npath_present=0\nfile_size=0\n")
        with self.assertRaises(ValueError):
            self.check()
        receipt.write_bytes(good)
        data=slow_rows().replace(b"TOTAL,-1,0,0,0,0,0,106,0",
                                 b"TOTAL,-1,0,0,0,0,0,106,1",1)
        for path in [self.sd/"audio-audout-slow-0000.csv",
                     self.evidence/"soak-audout-slow-unverified.csv"]:
            path.write_bytes(data)
        receipt.write_text(f"export_status=0\npath_present=1\nfile_size={len(data)}\n")
        with self.assertRaises(CorrelationError):
            self.check()

    def test_reject_missing_fiftieth_second_or_nro_change(self):
        p=self.evidence/"soak-audout-latency-unverified.csv"
        raw=p.read_bytes()
        p.write_bytes(b"\n".join(raw.splitlines()[:-4])+b"\n")
        with self.assertRaises(CorrelationError):
            self.check()
        p.write_bytes(raw)
        result=json.loads(self.preflight.read_text())
        result["nro_sha256"]="c"*64
        result["run_id"]=1000
        self.preflight.write_text(json.dumps(result)+"\n")
        with self.assertRaises(CorrelationError):
            self.check()

    def test_reject_host_music_key_schedule(self):
        p=self.evidence/"soak-events.csv"
        p.write_text(p.read_text().replace("idle_5,5,","focus_5,5,"))
        with self.assertRaises(CorrelationError):
            self.check()


if __name__=="__main__":
    unittest.main()
