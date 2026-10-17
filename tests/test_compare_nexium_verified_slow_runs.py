"""Synthetic cross-workflow acceptance tests; not genuine emulator observations."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_latency import parse_latency
from audit_nexium_audout_scene_correlation import (
    CorrelationError,parse_clock,parse_scene_inputs
)
from audit_nexium_audout_slow_calls import parse_slow,relate
from compare_nexium_verified_slow_runs import (
    audit_archive, compare_archives, PREFIX
)
from test_audit_nexium_audout_latency import make_csv
from test_audit_nexium_audout_scene_correlation import clock,scene
from test_audit_nexium_audout_slow_calls import slow_rows


def digest(b:bytes)->str:
    return hashlib.sha256(b).hexdigest()

def fixture(run_id:int,nro:str="a"*64)->dict[str,bytes]:
    clock_raw=clock()
    lat_raw=make_csv()
    slow_raw=slow_rows()
    scene_raw=scene()
    orig=parse_clock(clock_raw)
    lat=parse_latency(lat_raw)
    calls=parse_slow(slow_raw,orig["origin_ns"],lat)
    observations=relate(calls,parse_scene_inputs(scene_raw))
    receipt=(f"export_status=0\npath_present=1\n"
             f"file_size={len(slow_raw)}\n").encode("ascii")
    report={
        "result":"GUEST_SD_EXACT_AUDOUT_SLOW_CALLS_VERIFIED",
        "stage273_result":"GUEST_CLOCK_BOUND_SCENE_AND_AUDOUT_WINDOWS",
        "nro_sha256":nro,
        "slow_copy_sha256":digest(slow_raw),
        "guest_sd_slow_sha256":digest(slow_raw),
        "slow_receipt_sha256":digest(receipt),
        "slow_calls":calls,
        "slow_calls_captured":len(calls),
        "slow_calls_dropped":0,
        "slow_ge50ms_count":sum(c["duration_ns"]>=50_000_000 for c in calls),
        "audio_origin_ns":orig["origin_ns"],
        "audout_attempts":lat["attempts"],
        "audout_seconds":lat["windows"],
        "scene_input_timings":observations,
        "physical_switch_tested":False,
        "audible_underruns_measured":False,
    }
    latency_witness={
        "result":"GUEST_AUDOUT_PER_CALL_BANDS_VERIFIED",
        "sd_binding":"ORIGINAL_SD_AND_COPY_MATCHED",
        "original_csv_sha256":digest(lat_raw),
        "copied_csv_sha256":digest(lat_raw),
    }
    correlation={
        "source_nro_sha256":nro,
        "scene_csv_sha256":digest(scene_raw),
        "guest_clock_copy_sha256":digest(clock_raw),
        "latency_csv_sha256":digest(lat_raw),
        "guest_monotonic_origin_ns":orig["origin_ns"],
    }
    scene_witness={
        "guest_nro_sha256":nro,
        "result":"TEN_GUEST_SCENE_TRANSITIONS_DUAL_TRANSPORT_VERIFIED",
        "guest_csv_sha256":digest(scene_raw),
    }
    preflight={"run_id":run_id,"run_attempt":1,
               "result":"SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED",
               "hardware_status":"HARDWARE NOT TESTED",
               "nro_sha256":nro,"git_sha":f"{run_id:040x}"}
    def data(obj):return (json.dumps(obj,sort_keys=True)+"\n").encode("ascii")
    return {
        "integrated-nro-preflight.json":data(preflight),
        PREFIX+"soak-audout-slow-unverified.csv":slow_raw,
        PREFIX+"soak-audout-slow-export-result.txt":receipt,
        PREFIX+"soak-audout-exact-slow-verification.json":data(report),
        PREFIX+"soak-audout-clock-unverified.csv":clock_raw,
        PREFIX+"soak-audout-latency-unverified.csv":lat_raw,
        PREFIX+"soak-audout-latency-verification.json":data(latency_witness),
        PREFIX+"soak-guest-optical.csv":scene_raw,
        PREFIX+"soak-audout-scene-correlation.json":data(correlation),
        PREFIX+"soak-verification.json":data(scene_witness),
    }


def create_zip(path:Path,parts:dict[str,bytes])->None:
    with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_STORED) as out:
        for name,contents in parts.items():
            out.writestr(name,contents)


class VerifiedCrossRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.one=self.root/"run-101.zip"
        self.two=self.root/"run-102.zip"
        create_zip(self.one,fixture(101))
        create_zip(self.two,fixture(102))

    def test_two_distinct_identical_nro_synthetic_artifacts(self):
        report=compare_archives([self.one,self.two])
        self.assertEqual(report["result"],
            "MULTIRUN_EXACT_SLOW_CALLS_ARCHIVES_REVERIFIED")
        self.assertEqual(report["distinct_archive_run_ids"],2)
        self.assertEqual(report["nro_sha256"],"a"*64)
        self.assertEqual([r["run_id"] for r in report["runs"]],[101,102])
        self.assertFalse(report["original_transient_guest_sd_reopened_now"])
        self.assertFalse(report["slow_call_scene_causality_proven"])

    def test_duplicate_run_rejected(self):
        with self.assertRaises(CorrelationError):
            compare_archives([self.one,self.one])

    def test_different_nro_rejected(self):
        create_zip(self.two,fixture(102,"b"*64))
        with self.assertRaises(CorrelationError):
            compare_archives([self.one,self.two])

    def test_copy_tampering_rejected(self):
        for mutation in ("soak-audout-slow-unverified.csv",
                         "soak-audout-slow-export-result.txt",
                         "soak-guest-optical.csv",
                         "soak-audout-latency-unverified.csv"):
            with self.subTest(mutation=mutation):
                parts=fixture(101)
                key=next(k for k in parts if k.endswith(mutation))
                parts[key]+=b"TAMPER\n"
                create_zip(self.one,parts)
                with self.assertRaises(CorrelationError):
                    audit_archive(self.one)

    def test_missing_original_sd_verdict_rejected(self):
        parts=fixture(101)
        parts.pop(PREFIX+"soak-audout-exact-slow-verification.json")
        create_zip(self.one,parts)
        with self.assertRaises(CorrelationError):
            audit_archive(self.one)

    def test_forged_original_sd_hash_rejected(self):
        parts=fixture(101)
        key=PREFIX+"soak-audout-exact-slow-verification.json"
        data=json.loads(parts[key])
        data["guest_sd_slow_sha256"]="0"*64
        parts[key]=(json.dumps(data)+"\n").encode("ascii")
        create_zip(self.one,parts)
        with self.assertRaises(CorrelationError):
            audit_archive(self.one)

    def test_duplicate_zip_member_rejected(self):
        with zipfile.ZipFile(self.one,"a") as out:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore",UserWarning)
                out.writestr("integrated-nro-preflight.json",b"{}")
        with self.assertRaises(CorrelationError):
            audit_archive(self.one)


if __name__=="__main__":
    unittest.main()
