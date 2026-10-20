#!/usr/bin/env python3
"""Cross-check instrumented six-run ALSA transfer traces and immutable host.

Unlike Stage269 this is a NEW WORKLOAD (LD_PRELOAD instrumentation adds time).
Do not attribute changed outcomes to the unchanged Pulse latency hints.
"""
import argparse
import hashlib
import json
from pathlib import Path

from audit_map02_alsa_host_trace import parse
from audit_map02_cpal_alsa_boundary import audit, require
from verify_map02_nexium_one_binary import (
    verify_host_links, verify_evidence_attempts
)

SCHEMA="vh-map02-six-run-instrumented-alsa-observation/v1"


def read(path):
    data=json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(data,dict),f"{path}: expected JSON object")
    return data


def check(root, source, run_id):
    host=verify_host_links(root,source,run_id)
    attempt=verify_evidence_attempts(root,source,run_id)
    guest=audit(root,source,run_id)
    probe_dir=root/"map02-host-alsa-probe"
    probe=read(probe_dir/"manifest.json")
    so=(probe_dir/"libmap02_alsa_trace.so").read_bytes()
    require(probe.get("schema")=="vh-map02-alsa-host-probe-artifact/v1" and
            probe.get("source_sha")==source and
            probe.get("run_id")==run_id and
            probe.get("attempt")==attempt and
            probe.get("sha256")==hashlib.sha256(so).hexdigest() and so[:4]==b"\x7fELF",
            "Invalid shared host ALSA instrumentation library identity")
    rows=[]
    for trial in guest["trials"]:
        ms,rep=trial["hint_ms"],trial["repeat"]
        d=root/f"map02-presubmit-nexium-guest-proof-{ms}-r{rep}"
        copied=read(d/"host-alsa-probe-manifest.json")
        require(copied==probe,f"{d}: mismatched injected ALSA module")
        raw=d/"host-alsa-events.csv"
        parsed=parse(raw)
        original=read(d/"host-alsa-trace-report.json")
        require(parsed==original,f"{d}: forged host ALSA transfer summary")
        require(parsed["instrumentation_affects_host_timing"] is True and
                parsed["rust_cpal_callback_period_proven"] is False and
                parsed["guest_audout_service_deadlock_proven"] is False and
                parsed["physical_switch_audio_proven"] is False and
                parsed["anonymous_pcm_stream_ordinals_available"] is True and
                parsed["raw_audio_data_collected"] is False,
                f"{d}: unsupported host liveness or hardware claim")
        rows.append({
            "hint_ms":ms,"repeat":rep,
            "guest_optical_pcm_classification":trial["classification"],
            "guest_stage_at_prejoin":trial["stage_name"],
            "guest_audout_calls_entered":trial["audout_call_entries"],
            "guest_audout_calls_returned":trial["audout_call_returns"],
            "virtual_pcm_nonzero_samples":
                trial["virtual_monitor_pcm_nonzero_samples"],
            "observed_alsa_period_frames":parsed["period_frames_values"],
            "observed_alsa_buffer_frames":parsed["buffer_frames_values"],
            "alsa_transfer_kinds":parsed["transfer_kinds"],
            "alsa_transfer_calls_sampled":parsed["transfer_call_count"],
            "48k_stereo_alsa_stream_ids":parsed["48k_stereo_stream_ids"],
            "other_alsa_stream_ids":parsed["other_hw_stream_ids"],
            "48k_attributed_transfer_calls":
                parsed["48k_stereo_attributed_transfer_count"],
            "other_attributed_transfer_calls":
                parsed["other_config_attributed_transfer_count"],
            "unattributed_transfer_calls":
                parsed["unattributed_transfer_count"],
            "mixed_config_stream_ids":
                parsed["mixed_configuration_stream_ids"],
            "raw_alsa_stream_pointers_exposed":False,
            "trace_event_limit_reached":
                parsed["capture_prefix_only_if_event_limit_reached"],
            "alsa_transfer_duration_ns_min":
                parsed["transfer_duration_ns_min"],
            "alsa_transfer_duration_ns_max":
                parsed["transfer_duration_ns_max"],
            "probe_and_raw_alsa_trace_verified":True
        })
    require(len(rows)==6,"Six actual guest ALSA traces required")
    return {
        "schema":SCHEMA,
        "result":"SIX_HOST_ALSA_INTERPOSITION_TRACES_VERIFIED",
        "source_sha":source,"run_id":run_id,"run_attempt":attempt,
        "nexium_host_binary_sha256":host["host_executable_sha256"],
        "alsa_probe_sha256":probe["sha256"],
        "same_nexium_host_binary_all_six_verified":True,
        "same_alsa_preload_binary_all_six_verified":True,
        "anonymous_pcm_stream_ordinals_all_six_present":True,
        "rust_cpal_callback_identity_directly_proven":False,
        "guest_nro_png_pcm_six_trials_verified":True,
        "instrumentation_is_a_changed_guest_host_workload":True,
        "no_inference_from_prior_uninstrumented_guest_outcomes":True,
        "rust_cpal_callback_period_proven":False,
        "guest_audout_service_deadlock_proven":False,
        "physical_switch_dac_proven":False,
        "trials":rows,
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root",required=True,type=Path)
    ap.add_argument("--run-id",required=True,type=int)
    ap.add_argument("--source-sha",required=True)
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    try:
        report=check(args.root,args.source_sha,args.run_id)
        status=0
    except (ValueError,TypeError,KeyError,OSError,UnicodeError) as exc:
        report={
            "schema":SCHEMA,"result":"UNVERIFIED","reason":str(exc),
            "same_nexium_host_binary_all_six_verified":False,
            "same_alsa_preload_binary_all_six_verified":False,
            "guest_nro_png_pcm_six_trials_verified":False,
            "rust_cpal_callback_period_proven":False,
            "guest_audout_service_deadlock_proven":False,
            "physical_switch_dac_proven":False
        }
        status=1
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",
                           encoding="utf-8")
    print(json.dumps(report,indent=2,sort_keys=True))
    return status


if __name__=="__main__":
    raise SystemExit(main())
