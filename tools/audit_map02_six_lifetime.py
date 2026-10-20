#!/usr/bin/env python3
"""Independent six-run Stage273 lifetime counters vs original PNG / raw PCM."""
import argparse
import hashlib
import json
from pathlib import Path

from audit_map02_cpal_alsa_boundary import audit, require
from audit_map02_alsa_lifetime import parse
from verify_map02_nexium_one_binary import verify_host_links, verify_evidence_attempts

SCHEMA="vh-map02-six-alsa-lifetime-guest-correlation/v1"

def read(p):
    val=json.loads(p.read_text(encoding="utf-8"))
    require(isinstance(val,dict),f"{p}: expected object")
    return val

def check(root,source,run_id):
    host=verify_host_links(root,source,run_id)
    attempt=verify_evidence_attempts(root,source,run_id)
    guest=audit(root,source,run_id)
    binarydir=root/"map02-host-alsa-probe"
    manifest=read(binarydir/"manifest.json")
    binary=(binarydir/"libmap02_alsa_lifetime.so").read_bytes()
    require(binary[:4]==b"\x7fELF" and
            hashlib.sha256(binary).hexdigest()==manifest.get("sha256") and
            manifest.get("schema")=="vh-map02-host-alsa-lifetime-probe/v1" and
            manifest.get("run_id")==run_id and
            manifest.get("attempt")==attempt and
            manifest.get("source_sha")==source and
            manifest.get("sample_interval_nominal_ms")==200,
            "Invalid shared low-frequency host probe")
    rows=[]
    for trial in guest["trials"]:
        ms,rep=trial["hint_ms"],trial["repeat"]
        directory=root/f"map02-presubmit-nexium-guest-proof-{ms}-r{rep}"
        copied=read(directory/"host-alsa-probe-manifest.json")
        require(copied==manifest,f"{directory}: mixed host probe")
        first=int((directory/"guest-first-input-monotonic-ns.txt").read_text().strip())
        last=int((directory/"guest-final-observation-monotonic-ns.txt").read_text().strip())
        parsed=parse(directory/"host-alsa-lifetime.csv",first,last)
        require(parsed==read(directory/"host-alsa-lifetime-report.json"),
                f"{directory}: saved snapshot report does not match actual CSV")
        streams=parsed["per_stream"]
        target=[{"id":sid,**s} for sid,s in streams.items()
                if s["format_class"]=="48k_stereo"]
        require(target, f"{directory}: no identified 48k/stereo ALSA instance")
        rows.append({
            "hint_ms":ms,"repeat":rep,
            "guest_stage":trial["stage_name"],
            "guest_audout_entered":trial["audout_call_entries"],
            "guest_audout_returned":trial["audout_call_returns"],
            "virtual_pcm_nonzero_samples":
                trial["virtual_monitor_pcm_nonzero_samples"],
            "guest_classification":trial["classification"],
            "host_heartbeat_count":parsed["heartbeat_count"],
            "host_observed_span_ms":parsed["observed_span_ms"],
            "host_sample_gap_max_ms":parsed["sample_gap_max_ms"],
            "48k_stereo_host_streams":target,
            "other_host_streams":[{"id":sid,**s} for sid,s in streams.items()
                   if s["format_class"]!="48k_stereo"],
            "source_raw_lifetime_snapshots_verified":True,
        })
    require(len(rows)==6,"Six distinct actual guest traces required")
    return {
        "schema":SCHEMA,"result":"SIX_GUEST_HOST_ALSA_LIFETIME_SNAPSHOTS_VERIFIED",
        "source_sha":source,"run_id":run_id,"run_attempt":attempt,
        "one_nexium_host_executable_sha256":host["host_executable_sha256"],
        "one_lifetime_probe_sha256":manifest["sha256"],
        "same_nro_guest_png_pcm_verified_all_six":True,
        "instrumentation_changes_host_scheduling":True,
        "sampled_snapshots_not_exact_hardware_or_callback_lifetime":True,
        "rust_cpal_callback_period_directly_measured":False,
        "audout_service_permanent_deadlock_proven":False,
        "physical_switch_dac_audio_proven":False,
        "trials":rows
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--source-sha",required=True)
    p.add_argument("--run-id",required=True,type=int)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try:
        data=check(a.root,a.source_sha,a.run_id)
        status=0
    except (OSError,ValueError,KeyError,TypeError,UnicodeError) as exc:
        data={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(exc),
              "same_nro_guest_png_pcm_verified_all_six":False,
              "audout_service_permanent_deadlock_proven":False,
              "physical_switch_dac_audio_proven":False}
        status=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(data,sort_keys=True,indent=2))
    return status

if __name__=="__main__":
    raise SystemExit(main())
