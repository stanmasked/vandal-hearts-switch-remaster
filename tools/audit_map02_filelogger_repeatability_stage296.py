#!/usr/bin/env python3
"""Stage296 cohort audit: independent REAL NeXium CPAL/FileLogger trial receipts.

Consumes sanitized Stage294 receipts from isolated GitHub runner artifacts.
Never assumes callback counters equal log-line counts or assigns causality.
The original raw guest/PCM/PNG proofs are checked by Stage294 on each runner.
"""
import argparse
import json
from pathlib import Path

SCHEMA="vh-map02-stage296-real-filelogger-repeatability/v1"
TRIALS=((21,1),(21,2),(22,1),(22,2),(22,3))
HOST_SHA="c3803abd7a06fd4081d7d49367cfbd2cedc4bb1650996f1e09fca5788c881b65"
NRO_SHA="371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b"
SOURCE_SCHEMA="vh-map02-stage294-source-pinned-gui-filelogger-guest-evidence/v1"

def require(flag,message):
    if not flag:
        raise ValueError(message)

def load(path):
    obj=json.loads(Path(path).read_text())
    require(type(obj) is dict,"Expected a JSON object: "+str(path))
    return obj

def audit(root,run_id,head_sha):
    root=Path(root)
    require(root.is_dir(),"Missing independent trial artifact directory")
    require(type(run_id) is int and run_id>0,"Run ID must be positive")
    require(isinstance(head_sha,str) and len(head_sha)==40 and
            all(x in "0123456789abcdef" for x in head_sha),
            "Full commit SHA expected")
    expected={"map02-stage296-hint%d-r%d-evidence"%(h,r)
              for h,r in TRIALS}
    observed={p.name for p in root.iterdir() if p.is_dir()}
    require(observed==expected,
            "Trial artifacts missing, duplicated or unexpected: "+
            repr(sorted(observed.symmetric_difference(expected))))
    trials=[]
    for hint,replica in TRIALS:
        path=root/("map02-stage296-hint%d-r%d-evidence"%(hint,replica))
        context=load(path/"stage296-trial-context.json")
        proof=load(path/"stage294-filelogger-derived-receipt.json")
        source=load(path/"pinned-host-and-nro.json")
        pre=load(path/"guest-prejoin-stage.json")
        final=load(path/"guest-final-receipt.json")
        cp=load(path/"host-cpal-lifecycle-audit.json")
        pcm=load(path/"virtual-pcm-health.json")
        require(context=={
            "schema":"vh-map02-stage296-trial-context/v1",
            "run_id":run_id,
            "attempt":1,
            "hint_ms":hint,
            "replica":replica,
            "head_sha":head_sha,
            "stage294_audit_result":
                "REAL_LIFECYCLE_NEXIUM_FILELOGGER_AND_GUEST_EVIDENCE_VERIFIED",
        }, "Runner identity mismatch for %s"%path.name)
        require(source["schema"]=="vh-map02-stage294-guest-host-pair/v1"
                and source["actual_new_trial_run_id"]==run_id
                and source["trial_attempt"]==1
                and source["pulse_hint_ms"]==hint
                and source["new_host_executable_sha256"]==HOST_SHA
                and source["guest_nro_sha256"]==NRO_SHA
                and source["rom_or_licensed_audio_used"] is False,
                "Stage294 immutable ELF/NRO source provenance mismatch")
        require(proof["schema"]==SOURCE_SCHEMA
                and proof["result"]==
                "REAL_LIFECYCLE_NEXIUM_FILELOGGER_AND_GUEST_EVIDENCE_VERIFIED"
                and proof["actual_source_run_id"]==run_id
                and proof["requested_pulse_hint_ms"]==hint
                and proof["exact_stage287_nexium_elf_sha256"]==HOST_SHA
                and proof["exact_generated_guest_nro_sha256"]==NRO_SHA
                and proof["one_source_pinned_gui_filelogger_found"] is True
                and proof["original_gui_filelogger_raw_bytes_uploaded"] is False
                and proof["physical_switch_audio_proven"] is False
                and proof["no_permanent_audout_deadlock_or_cpal_root_cause_proven"] is True,
                "Stage294 guest/FileLogger verification missing")
        require(isinstance(proof["full_process_filelogger_sha256"],str)
                and len(proof["full_process_filelogger_sha256"])==64
                and proof["full_process_filelogger_bytes"]>0,
                "Actual FileLogger SHA or bytes absent")
        require(proof["guest_window_cpal_entries"]==
                cp["guest_window_atomic_counter_deltas"]["cpal_entries"]
                and proof["guest_window_cpal_returns"]==
                cp["guest_window_atomic_counter_deltas"]["cpal_returns"]
                and proof["guest_window_cpal_error_callback_delta"]==
                cp["guest_window_atomic_counter_deltas"]["error_callbacks"]
                and proof["guest_window_audioout_appends"]==
                cp["guest_window_atomic_counter_deltas"]["audioout_appends"]
                and cp["guest_monotonic_window_verified"] is True,
                "CPAL evidence receipt counters mismatch")
        require(proof["guest_prejoin_audout_entries"]==
                pre["audout_playbuffer_call_entries"]
                and proof["guest_prejoin_audout_returns"]==
                pre["audout_playbuffer_call_returns"]
                and proof["guest_final_optical_result"]==final["result"]
                and proof["raw_virtual_pcm_sha256"]==pcm["raw_sha256"]
                and proof["virtual_pcm_nonzero_samples"]==
                pcm["nonzero_pcm16_samples"] and pcm["valid_pcm16le_stereo"] is True,
                "Raw PCM/optical per-run verifier mismatch")
        require(proof["full_process_cpal_error_log_lines"]>=0
                and proof["guest_window_cpal_error_callback_delta"]>=0
                and isinstance(proof["sanitized_cpal_message_groups"],list),
                "Invalid FileLogger error counts")
        # Never equate whole-process wall-clock log lines with guest-window
        # monotonic callback counters. Both may legitimately be different.
        trials.append({
            "hint_ms":hint,"replica":replica,
            "gui_log_bytes":proof["full_process_filelogger_bytes"],
            "gui_log_sha256":proof["full_process_filelogger_sha256"],
            "full_process_cpal_error_log_lines":
                proof["full_process_cpal_error_log_lines"],
            "guest_window_cpal_error_callbacks":
                proof["guest_window_cpal_error_callback_delta"],
            "guest_window_cpal_entries":proof["guest_window_cpal_entries"],
            "guest_window_cpal_returns":proof["guest_window_cpal_returns"],
            "guest_prejoin_stage":pre["stage_name"],
            "guest_final_optical_result":final["result"],
            "pcm_nonzero_samples":pcm["nonzero_pcm16_samples"],
            "behavior":proof["guest_observed_behavior"],
            "sanitized_cpal_message_groups":proof["sanitized_cpal_message_groups"],
        })
    byhint={}
    for hint in (21,22):
        group=[t for t in trials if t["hint_ms"]==hint]
        byhint[str(hint)]={
            "runs":len(group),
            "callbacks_with_errors":sum(t["guest_window_cpal_error_callbacks"]>0
                                        for t in group),
            "runs_with_full_process_cpal_error_text":
                sum(t["full_process_cpal_error_log_lines"]>0 for t in group),
            "runs_with_completed_eight_page_guest_crc":
                sum(t["guest_final_optical_result"]==
                    "GUEST_PRESUBMIT_PCM_PAGES_MATCHED" for t in group),
            "runs_with_zero_new_cpal_callback_entries":
                sum(t["guest_window_cpal_entries"]==0 for t in group),
            "error_callback_deltas":[t["guest_window_cpal_error_callbacks"]
                                     for t in group],
        }
    return {
        "schema":SCHEMA,
        "result":"FIVE_INDEPENDENT_GUEST_FILELOGGER_RECEIPTS_VERIFIED",
        "run_id":run_id,"head_sha":head_sha,
        "same_pinned_elf_sha256":HOST_SHA,
        "same_rom_free_guest_nro_sha256":NRO_SHA,
        "cohort":byhint,"trials":trials,
        "full_process_error_lines_not_guest_window_event_counts":True,
        "five_runs_not_a_statistical_reliability_estimate":True,
        "pulse_hint_not_measured_hardware_period":True,
        "no_permanent_deadlock_or_audio_root_cause_proven":True,
        "physical_nintendo_switch_audio_proven":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True,type=Path)
    p.add_argument("--run-id",required=True,type=int)
    p.add_argument("--head-sha",required=True)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    try:
        result=audit(a.root,a.run_id,a.head_sha)
        rc=0
    except (ValueError,OSError,KeyError,TypeError,OverflowError,
            json.JSONDecodeError) as exc:
        result={"schema":SCHEMA,"result":"UNVERIFIED",
                "reason":str(exc),
                "no_permanent_deadlock_or_audio_root_cause_proven":True,
                "physical_nintendo_switch_audio_proven":False}
        rc=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps(result,sort_keys=True,indent=2))
    return rc

if __name__=="__main__":
    raise SystemExit(main())
