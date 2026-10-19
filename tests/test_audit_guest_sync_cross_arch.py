"""Synthetic negative tests for host/guest DSP fingerprint equivalence."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

PATH=Path(__file__).resolve().parents[1]/"tools/audit_guest_sync_cross_arch.py"
spec=importlib.util.spec_from_file_location("guest_sync_cross",PATH)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class Parity(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.gcc=self.root/"gcc.txt"
        self.clang=self.root/"clang.txt"
        self.guests=[self.root/"guest0.json",self.root/"guest1.json"]
        self.line="initial=ea424fc357e9ad98 wet=9950037014a7e866 reset=f5edab31b6802325 wet_nonzero=49128"
        self.gcc.write_text("PASS: synthetic DSP\n"+self.line+"\n")
        self.clang.write_text(self.line+"\n")
        for mode,p in enumerate(self.guests):
            p.write_text(json.dumps({"outer_nro_wet_tail_mode":mode,
                "result":"GUEST_SYNCHRONIZED_SYNTHETIC_STUDIO_C_TAIL_PROVEN",
                "pre_blocks":64,"post_switch_blocks":48,
                "different_blocks":48,"reset_nonzero_sample_values":0,
                "new_scene_note_ons":0,"identical_input_replays":2,
                "guest_live_audout_studio_c_causality_proven":False,
                "pre_switch_pcm_fnv1a64":"ea424fc357e9ad98",
                "retained_tail_pcm_fnv1a64":"9950037014a7e866",
                "reset_tail_pcm_fnv1a64":"f5edab31b6802325",
                "wet_nonzero_sample_values":49128}))
    def check(self):
        return mod.compare(self.gcc,self.clang,*self.guests,77,1,"a"*40)
    def update(self,i,key,value):
        p=self.guests[i];d=json.loads(p.read_text());d[key]=value;p.write_text(json.dumps(d))
    def test_valid_parity_is_not_live_audout_proof(self):
        d=self.check()
        self.assertEqual(d["result"],"GCC_CLANG_NEXIUM_SYNTHETIC_PCM_IDENTICAL")
        self.assertFalse(d["live_audout_sample_aligned"])
        self.assertFalse(d["physical_switch_audio_tested"])
    def test_gcc_clang_mismatch_is_rejected(self):
        self.clang.write_text(self.line.replace("49128","49127"))
        with self.assertRaisesRegex(ValueError,"GCC/Clang"):self.check()
    def test_guest_wet_hash_mismatch_is_rejected(self):
        self.update(1,"retained_tail_pcm_fnv1a64","0000000000000001")
        with self.assertRaisesRegex(ValueError,"differs"):self.check()
    def test_guest_wrong_mode_rejected(self):
        self.update(1,"outer_nro_wet_tail_mode",0)
        with self.assertRaisesRegex(ValueError,"mode"):self.check()
    def test_guest_failed_receipt_rejected(self):
        self.update(0,"result","GUEST_SYNCHRONIZED_TAIL_UNVERIFIED")
        with self.assertRaisesRegex(ValueError,"proof"):self.check()
    def test_guest_not_48_blocks_rejected(self):
        self.update(0,"different_blocks",47)
        with self.assertRaisesRegex(ValueError,"invariants"):self.check()
    def test_guest_false_audout_claim_required(self):
        self.update(1,"guest_live_audout_studio_c_causality_proven",True)
        with self.assertRaisesRegex(ValueError,"invariants"):self.check()
    def test_invalid_sha_rejected(self):
        with self.assertRaisesRegex(ValueError,"SHA"):
            mod.compare(self.gcc,self.clang,*self.guests,77,1,"xyz")
    def test_duplicate_host_line_rejected(self):
        self.gcc.write_text(self.line+"\n"+self.line+"\n")
        with self.assertRaisesRegex(ValueError,"exactly one"):self.check()
    def test_guest_omits_wet_nonzero_rejected(self):
        self.update(1,"wet_nonzero_sample_values",None)
        with self.assertRaisesRegex(ValueError,"differs"):self.check()

if __name__=="__main__":unittest.main()
