"""Generated-only falsification checks for Stage296 independent cohort receipts."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_filelogger_repeatability_stage296 import (
    audit,TRIALS,HOST_SHA,NRO_SHA,SOURCE_SCHEMA
)

RUN=39504242167
SHA="335da2c666d57caa429a1a4408935dcd046cdf1a"

def emit(path,obj):
    path.write_text(json.dumps(obj,sort_keys=True)+"\n")

def sample(root):
    for hint,replica in TRIALS:
        p=root/("map02-stage296-hint%d-r%d-evidence"%(hint,replica))
        p.mkdir()
        entries=0 if hint==21 else 3
        nonzero=0 if hint==21 else 20
        optical=("GUEST_PRESUBMIT_UNVERIFIED" if hint==21
                 else "GUEST_PRESUBMIT_PCM_PAGES_MATCHED")
        emit(p/"stage296-trial-context.json",{
            "schema":"vh-map02-stage296-trial-context/v1",
            "run_id":RUN,"attempt":1,"hint_ms":hint,
            "replica":replica,"head_sha":SHA,
            "stage294_audit_result":
                "REAL_LIFECYCLE_NEXIUM_FILELOGGER_AND_GUEST_EVIDENCE_VERIFIED"})
        emit(p/"pinned-host-and-nro.json",{
            "schema":"vh-map02-stage294-guest-host-pair/v1",
            "actual_new_trial_run_id":RUN,"trial_attempt":1,
            "pulse_hint_ms":hint,"new_host_executable_sha256":HOST_SHA,
            "guest_nro_sha256":NRO_SHA,"rom_or_licensed_audio_used":False})
        emit(p/"host-cpal-lifecycle-audit.json",{
            "guest_monotonic_window_verified":True,
            "guest_window_atomic_counter_deltas":{
                "cpal_entries":entries,"cpal_returns":entries,
                "error_callbacks":0,"audioout_appends":entries}})
        emit(p/"guest-prejoin-stage.json",{
            "stage_name":"ENTERED_PLAYBUFFER" if hint==21
                         else "CLEANUP_COMPLETED",
            "audout_playbuffer_call_entries":1,
            "audout_playbuffer_call_returns":0 if hint==21 else 1})
        emit(p/"guest-final-receipt.json",{"result":optical})
        emit(p/"virtual-pcm-health.json",{
            "raw_sha256":"f"*64,"nonzero_pcm16_samples":nonzero,
            "valid_pcm16le_stereo":True})
        emit(p/"stage294-filelogger-derived-receipt.json",{
            "schema":SOURCE_SCHEMA,
            "result":"REAL_LIFECYCLE_NEXIUM_FILELOGGER_AND_GUEST_EVIDENCE_VERIFIED",
            "actual_source_run_id":RUN,"requested_pulse_hint_ms":hint,
            "exact_stage287_nexium_elf_sha256":HOST_SHA,
            "exact_generated_guest_nro_sha256":NRO_SHA,
            "one_source_pinned_gui_filelogger_found":True,
            "original_gui_filelogger_raw_bytes_uploaded":False,
            "physical_switch_audio_proven":False,
            "no_permanent_audout_deadlock_or_cpal_root_cause_proven":True,
            "full_process_filelogger_sha256":"a"*64,
            "full_process_filelogger_bytes":512,
            "guest_window_cpal_entries":entries,
            "guest_window_cpal_returns":entries,
            "guest_window_cpal_error_callback_delta":0,
            "guest_window_audioout_appends":entries,
            "guest_prejoin_audout_entries":1,
            "guest_prejoin_audout_returns":0 if hint==21 else 1,
            "guest_final_optical_result":optical,
            "raw_virtual_pcm_sha256":"f"*64,
            "virtual_pcm_nonzero_samples":nonzero,
            "full_process_cpal_error_log_lines":0,
            "sanitized_cpal_message_groups":[],
            "guest_observed_behavior":"simulated value not independently inferred",
        })

class RepeatabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        sample(self.root)

    def path(self,hint=22,replica=3):
        return self.root/("map02-stage296-hint%d-r%d-evidence"%(hint,replica))

    def change(self,filename,key,value):
        p=self.path()/filename
        d=json.loads(p.read_text());d[key]=value;emit(p,d)

    def test_five_complete_source_bound_receipts(self):
        x=audit(self.root,RUN,SHA)
        self.assertEqual(x["result"],"FIVE_INDEPENDENT_GUEST_FILELOGGER_RECEIPTS_VERIFIED")
        self.assertEqual(x["cohort"]["22"]["runs"],3)
        self.assertEqual(x["cohort"]["21"]["runs_with_zero_new_cpal_callback_entries"],2)

    def test_missing_replica_rejected(self):
        import shutil
        shutil.rmtree(self.path())
        with self.assertRaisesRegex(ValueError,"Trial artifacts missing"):
            audit(self.root,RUN,SHA)

    def test_swapped_hint_rejected(self):
        self.change("stage296-trial-context.json","hint_ms",21)
        with self.assertRaisesRegex(ValueError,"Runner identity mismatch"):
            audit(self.root,RUN,SHA)

    def test_reused_run_id_rejected(self):
        self.change("pinned-host-and-nro.json","actual_new_trial_run_id",RUN-1)
        with self.assertRaisesRegex(ValueError,"source provenance mismatch"):
            audit(self.root,RUN,SHA)

    def test_missing_original_audit_rejected(self):
        self.change("stage294-filelogger-derived-receipt.json","result","UNVERIFIED")
        with self.assertRaisesRegex(ValueError,"verification missing"):
            audit(self.root,RUN,SHA)

    def test_counter_mismatch_rejected(self):
        self.change("stage294-filelogger-derived-receipt.json",
                    "guest_window_cpal_returns",4)
        with self.assertRaisesRegex(ValueError,"counters mismatch"):
            audit(self.root,RUN,SHA)

    def test_pcm_digest_mismatch_rejected(self):
        self.change("virtual-pcm-health.json","raw_sha256","0"*64)
        with self.assertRaisesRegex(ValueError,"PCM/optical"):
            audit(self.root,RUN,SHA)

    def test_log_lines_not_equated_to_callbacks(self):
        self.change("stage294-filelogger-derived-receipt.json",
                    "guest_window_cpal_error_callback_delta",169)
        cp=self.path()/"host-cpal-lifecycle-audit.json"
        d=json.loads(cp.read_text())
        d["guest_window_atomic_counter_deltas"]["error_callbacks"]=169
        emit(cp,d)
        x=audit(self.root,RUN,SHA)
        self.assertEqual(x["cohort"]["22"]["error_callback_deltas"],[0,0,169])
        self.assertEqual(x["cohort"]["22"]["runs_with_full_process_cpal_error_text"],0)

if __name__=="__main__":
    unittest.main()
