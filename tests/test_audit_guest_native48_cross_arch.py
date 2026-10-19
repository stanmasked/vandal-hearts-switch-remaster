"""Negative fixtures for host/guest exact native 48-kHz output-stage parity."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[1]/"tools/audit_guest_native48_cross_arch.py"
spec=importlib.util.spec_from_file_location("native48_crossarch",SCRIPT)
audit_tool=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_tool)
SHA="a"*40

class Native48ParityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.gcc=root/"gcc.txt"
        self.clang=root/"clang.txt"
        self.guests=[root/"guest0.json",root/"guest1.json"]
        self.line=("native48 pre=1111222233334444 wet=9950037014a7e866 "
                   "reset=f5edab31b6802325 prefix_frames=35665 tail_frames=26750 "
                   "different_pages=48 wet_nonzero=49000 reset_first=2 reset_later=0")
        for file in (self.gcc,self.clang):
            file.write_text("PASS: guest synthetic DSP\n"+self.line+"\n")
        for mode,file in enumerate(self.guests):
            file.write_text(json.dumps({
                "schema":"vh-map02-guest-native-48k-bridge/v1",
                "outer_nro_wet_tail_mode":mode,
                "result":"GUEST_NATIVE_48K_SYNCHRONIZED_TAIL_OBSERVED",
                "pre_switch_native_fnv1a64":"1111222233334444",
                "wet_native_fnv1a64":"9950037014a7e866",
                "reset_native_fnv1a64":"f5edab31b6802325",
                "pre_switch_native_frames":35665,
                "post_switch_native_frames":26750,
                "different_post_switch_native_pages":48,
                "retained_tail_nonzero_sample_values":49000,
                "reset_first_page_nonzero_sample_values":2,
                "reset_later_pages_nonzero_sample_values":0,
                "identical_complete_replays":2,
                "rate_hz":48000,
                "guest_synthetic_postprocess_causality":True,
                "live_audout_music_sample_aligned":False,
                "physical_switch_speakers_verified":False
            }))
    def run_audit(self):
        return audit_tool.audit(self.gcc,self.clang,*self.guests,42,1,SHA)
    def update_guest(self,index,key,value):
        file=self.guests[index]
        data=json.loads(file.read_text())
        data[key]=value
        file.write_text(json.dumps(data))
    def test_valid_parity_rejects_live_audio_inference(self):
        r=self.run_audit()
        self.assertEqual(r["result"],"GCC_CLANG_BOTH_NEXIUM_NATIVE_48K_EQUAL")
        self.assertFalse(r["live_audout_sample_aligned"])
        self.assertFalse(r["physical_switch_audio_tested"])
    def test_gcc_clang_mismatch_fails(self):
        self.clang.write_text(self.line.replace("49000","48999"))
        with self.assertRaisesRegex(ValueError,"GCC and Clang"):self.run_audit()
    def test_guest_wet_pcm_hash_mismatch_fails(self):
        self.update_guest(0,"wet_native_fnv1a64","0000000000000001")
        with self.assertRaisesRegex(ValueError,"differ"):self.run_audit()
    def test_guest_frame_count_mismatch_fails(self):
        self.update_guest(1,"post_switch_native_frames",26751)
        with self.assertRaisesRegex(ValueError,"differ"):self.run_audit()
    def test_host_one_prefix_frame_drift_is_rejected(self):
        for f in (self.gcc,self.clang):
            f.write_text(self.line.replace("prefix_frames=35665","prefix_frames=35664"))
        with self.assertRaisesRegex(ValueError,"bounds"):self.run_audit()
    def test_host_one_tail_frame_drift_is_rejected(self):
        for f in (self.gcc,self.clang):
            f.write_text(self.line.replace("tail_frames=26750","tail_frames=26751"))
        with self.assertRaisesRegex(ValueError,"bounds"):self.run_audit()
    def test_guest_boundary_residue_mismatch_fails(self):
        self.update_guest(0,"reset_first_page_nonzero_sample_values",1)
        with self.assertRaisesRegex(ValueError,"differ"):self.run_audit()
    def test_nonzero_later_reset_fails(self):
        self.update_guest(1,"reset_later_pages_nonzero_sample_values",1)
        with self.assertRaisesRegex(ValueError,"differ"):self.run_audit()
    def test_incorrect_guest_mode_fails(self):
        self.update_guest(1,"outer_nro_wet_tail_mode",0)
        with self.assertRaisesRegex(ValueError,"status"):self.run_audit()
    def test_false_claim_of_live_audout_fails(self):
        self.update_guest(0,"live_audout_music_sample_aligned",True)
        with self.assertRaisesRegex(ValueError,"claim"):self.run_audit()
    def test_unbounded_host_tail_fails(self):
        self.gcc.write_text(self.line.replace("reset_first=2","reset_first=3"))
        self.clang.write_text(self.line.replace("reset_first=2","reset_first=3"))
        with self.assertRaisesRegex(ValueError,"bounds"):self.run_audit()
    def test_duplicate_host_receipts_fail(self):
        self.gcc.write_text(self.line+"\n"+self.line+"\n")
        with self.assertRaisesRegex(ValueError,"exactly one"):self.run_audit()
    def test_bad_run_provenance_fails(self):
        with self.assertRaisesRegex(ValueError,"provenance"):
            audit_tool.audit(self.gcc,self.clang,*self.guests,0,1,SHA)
    def test_guest_missing_field_fails(self):
        self.update_guest(1,"wet_native_fnv1a64",None)
        with self.assertRaisesRegex(ValueError,"types"):self.run_audit()
    def test_wrong_guest_schema_fails(self):
        self.update_guest(0,"schema","vh-map02-guest-native-48k-bridge/v0")
        with self.assertRaisesRegex(ValueError,"status"):self.run_audit()
    def test_missing_guest_schema_fails(self):
        self.update_guest(1,"schema",None)
        with self.assertRaisesRegex(ValueError,"status"):self.run_audit()
    def test_boolean_guest_mode_fails(self):
        self.update_guest(0,"outer_nro_wet_tail_mode",False)
        with self.assertRaisesRegex(ValueError,"types"):self.run_audit()
    def test_boolean_zero_residue_fails(self):
        self.update_guest(1,"reset_later_pages_nonzero_sample_values",False)
        with self.assertRaisesRegex(ValueError,"types"):self.run_audit()
    def test_duplicate_guest_json_keys_fail(self):
        p=self.guests[0]
        original=p.read_text()
        p.write_text(original.replace(
            '"schema": "vh-map02-guest-native-48k-bridge/v1"',
            '"schema": "forged", "schema": "vh-map02-guest-native-48k-bridge/v1"'))
        with self.assertRaisesRegex(ValueError,"Duplicate"):self.run_audit()
    def test_guest_array_instead_of_object_fails(self):
        self.guests[0].write_text('[]')
        with self.assertRaisesRegex(ValueError,"object"):self.run_audit()
    def test_zero_prefix_hash_rejected_independently(self):
        for file in (self.gcc,self.clang):
            file.write_text(self.line.replace("1111222233334444","0000000000000000"))
        with self.assertRaisesRegex(ValueError,"bounds"):self.run_audit()

if __name__=="__main__":unittest.main()
