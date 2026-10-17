"""Stage277 paired negative controls use synthetic guest SD; not emulator facts."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from compare_nexium_idle_switch_pairs import (
    audit_pair_archives,read_bound_idle,summarize,IDLE_PREFIX,IDLE_COPIES,RECEIPTS
)
from compare_nexium_verified_slow_runs import audit_archive
from test_compare_nexium_verified_slow_runs import fixture,create_zip
from test_audit_nexium_audout_idle_control import TestIdleControl

def paired_fixture(run_id:int)->dict[str,bytes]:
    files=fixture(run_id)
    case=TestIdleControl("test_original_sd_unchanged_scene_and_full_audio")
    case.setUp()
    try:
        idle=case.check()
        idle["nro_sha256"]="a"*64
        idle["run_id"]=run_id
        idle["git_sha"]=f"{run_id:040x}"
        for kind,_filename,copied,_loc,receipt,raw in case.items:
            files[IDLE_PREFIX+IDLE_COPIES[kind]]=raw
            if receipt:
                files[IDLE_PREFIX+receipt]=(
                    f"export_status=0\npath_present=1\n"
                    f"file_size={len(raw)}\n").encode("ascii")
        pair={
            "schema":"vh-nexium-idle-versus-switch-same-nro/v1",
            "result":"SAME_NRO_GUEST_IDLE_AND_SWITCH_MEASUREMENTS_VERIFIED",
            "nro_sha256":"a"*64,
            "idle_run_id":run_id,
            "guest_idle_audout_attempts":1908,
            "guest_switch_audout_attempts":1908,
            "idle_slow_ge40ms_calls":106,
            "switch_slow_ge40ms_calls":106,
            "idle_slow_ge50ms_calls":53,
            "switch_slow_ge50ms_calls":53,
            "idle_ge40_per_1000_attempts":round(1000*106/1908,3),
            "switch_ge40_per_1000_attempts":round(1000*106/1908,3),
            "idle_ge50_per_1000_attempts":round(1000*53/1908,3),
            "switch_ge50_per_1000_attempts":round(1000*53/1908,3),
            "scene_switching_causality_proven":False,
            "physical_hardware_tested":False,
            "audible_underruns_measured":False,
        }
        encode=lambda data:(json.dumps(data,sort_keys=True)+"\n").encode("ascii")
        files[IDLE_PREFIX+"idle-audout-verification.json"]=encode(idle)
        files[IDLE_PREFIX+"idle-vs-switch.json"]=encode(pair)
        return files
    finally:
        case.doCleanups()

class PairedSameNroRegression(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.paths=[self.root/"one.zip",self.root/"two.zip"]
        self.contents=[paired_fixture(27601),paired_fixture(27602)]
        for path,files in zip(self.paths,self.contents):
            create_zip(path,files)

    def test_valid_distinct_synthetic_pairs(self):
        report=audit_pair_archives(self.paths)
        self.assertEqual(report["result"],"SAME_NRO_IDLE_SWITCH_ARCHIVED_PAIRS_REVERIFIED")
        self.assertEqual(report["totals"]["idle_attempts"],3816)
        self.assertEqual(report["totals"]["switch_attempts"],3816)
        self.assertEqual(report["totals"]["idle_ge40"],212)
        self.assertEqual(report["totals"]["switch_ge50"],106)
        self.assertEqual(report["paired_rate_directions"]["ge40"]["exact_ties"],2)
        self.assertFalse(report["randomized_or_causal_inference"])
        self.assertFalse(report["original_guest_sd_reopened_offline"])

    def test_duplicate_ids_or_different_nro_rejected(self):
        with self.assertRaises(CorrelationError):
            audit_pair_archives([self.paths[0],self.paths[0]])
        invalid=paired_fixture(27602)
        preflight=json.loads(invalid["integrated-nro-preflight.json"])
        preflight["nro_sha256"]="b"*64
        invalid["integrated-nro-preflight.json"]=(
            json.dumps(preflight)+"\n").encode("ascii")
        create_zip(self.paths[1],invalid)
        with self.assertRaises(CorrelationError):
            audit_pair_archives(self.paths)

    def test_single_idle_byte_tamper_rejected(self):
        for kind,filename in IDLE_COPIES.items():
            with self.subTest(kind=kind):
                altered=dict(self.contents[0])
                altered[IDLE_PREFIX+filename]+=b"BAD\n"
                create_zip(self.paths[0],altered)
                with self.assertRaises(CorrelationError):
                    audit_pair_archives(self.paths)

    def test_idle_receipt_tamper_rejected(self):
        altered=dict(self.contents[0])
        altered[IDLE_PREFIX+RECEIPTS["slow"]]=b"export_status=0\npath_present=0\nfile_size=0\n"
        create_zip(self.paths[0],altered)
        with self.assertRaises(CorrelationError):
            audit_pair_archives(self.paths)

    def test_forged_idle_original_sd_hash_rejected(self):
        altered=dict(self.contents[0])
        k=IDLE_PREFIX+"idle-audout-verification.json"
        report=json.loads(altered[k])
        report["idle_guest_sd_sha256"]["scene"]="0"*64
        altered[k]=(json.dumps(report)+"\n").encode("ascii")
        create_zip(self.paths[0],altered)
        with self.assertRaises(CorrelationError):
            audit_pair_archives(self.paths)

    def test_wrong_paired_count_rejected(self):
        altered=dict(self.contents[0])
        k=IDLE_PREFIX+"idle-vs-switch.json"
        report=json.loads(altered[k])
        report["switch_slow_ge50ms_calls"]+=1
        altered[k]=(json.dumps(report)+"\n").encode("ascii")
        create_zip(self.paths[0],altered)
        with self.assertRaises(CorrelationError):
            audit_pair_archives(self.paths)

    def test_forged_guest_music_input_rejected_even_with_hash_update(self):
        altered=dict(self.contents[0])
        scene_file=IDLE_PREFIX+IDLE_COPIES["scene"]
        scene=altered[scene_file]
        scene=scene.replace(b"ACCEPT",b"INPUTX",1)
        altered[scene_file]=scene
        witness_key=IDLE_PREFIX+"idle-audout-verification.json"
        witness=json.loads(altered[witness_key])
        import hashlib
        witness["idle_guest_sd_sha256"]["scene"]=hashlib.sha256(scene).hexdigest()
        altered[witness_key]=(json.dumps(witness)+"\n").encode("ascii")
        create_zip(self.paths[0],altered)
        with self.assertRaises(CorrelationError):
            audit_pair_archives(self.paths)

    def test_cross_pairs_opposite_rates_are_not_a_causal_claim(self):
        one={"run_id":1,"nro_sha256":"a"*64,
             "idle_attempts":1000,"switch_attempts":1000,
             "idle_ge40":8,"switch_ge40":20,
             "idle_ge50":1,"switch_ge50":2}
        two={"run_id":2,"nro_sha256":"a"*64,
             "idle_attempts":1000,"switch_attempts":1000,
             "idle_ge40":22,"switch_ge40":7,
             "idle_ge50":3,"switch_ge50":0}
        report=summarize([one,two])
        self.assertEqual(report["paired_rate_directions"]["ge40"]["switch_rate_higher"],1)
        self.assertEqual(report["paired_rate_directions"]["ge40"]["idle_rate_higher"],1)
        self.assertFalse(report["randomized_or_causal_inference"])

if __name__=="__main__":
    unittest.main()
