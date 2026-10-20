#!/usr/bin/env python3
"""Independently re-decode six real Stage283 matrix guest/CPAL/PCM archives.

Each matrix job is a distinct hosted runner with the identical immutable host
ELF and opt-in generated NRO. A requested 21/22ms Pulse hint is NOT measured
CPAL hardware latency. Neither a pending guest call nor a silent virtual sink
proves permanent deadlock or physical Nintendo Switch DAC operation.
"""
import argparse
from array import array
import hashlib
import json
from pathlib import Path
import sys

from audit_map02_cpal_audioout_timeline import parse as parse_host
from decode_map02_prejoin_stage import decode_image as decode_prejoin
from decode_map02_guest_scene_trace import decode_packet_image
from decode_map02_audout_presubmit import decode as decode_guest

SCHEMA="vh-map02-stage283-six-run-source-pinned-cpal-optical-audit/v1"
HOST="dd4ed55b6ce8477f19b77465f4ce6a0606b7a7315b3a0e2b8137b7d7ab5effd0"
NRO="371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b"
NRO_SOURCE="04b20024a50327091cff430eb5c28e4722d4ec76"
NRO_BUILD_RUN=39460035568


def require(value,reason):
    if not value:
        raise ValueError(reason)


def data(path):
    value=json.loads(path.read_text(encoding="utf-8"))
    require(type(value) is dict,f"{path}: expected JSON object")
    return value


def observed_guest_final(path):
    try:
        return decode_guest(decode_packet_image(path))
    except (OSError,TypeError,ValueError) as exc:
        return {"schema":"vh-map02-presubmit-optical/v1",
                "result":"GUEST_PRESUBMIT_UNVERIFIED",
                "reason":str(exc),"live_dac_samples_proven":False,
                "physical_switch_speaker_audio_verified":False}


def describe_behavior(record):
    completed=(
        record["prejoin_stage"]=="CLEANUP_COMPLETED"
        and record["prejoin_guest_audout_entries"]==
            record["prejoin_guest_audout_returns"]>0
        and record["strict_guest_result"]=="GUEST_PRESUBMIT_PCM_PAGES_MATCHED"
        and record["strict_guest_pages"]==8
        and record["cpal_callback_entries"]==
            record["cpal_callback_returns"]>0
        and record["audioout_appends"]>0
        and record["audioout_releases"]>0
        and record["nonzero_virtual_pcm16"]>0
    )
    pending=(
        record["prejoin_stage"]=="ENTERED_PLAYBUFFER"
        and record["prejoin_guest_audout_entries"]>
            record["prejoin_guest_audout_returns"]
        and record["strict_guest_result"]=="GUEST_PRESUBMIT_UNVERIFIED"
        and record["cpal_callback_entries"]==
            record["cpal_callback_returns"]==0
        and record["audioout_appends"]==
            record["audioout_releases"]==0
        and record["nonzero_virtual_pcm16"]==0
    )
    if completed:
        return "GUEST_COMPLETED_8_CRC_PAGES_WITH_REAL_VIRTUAL_PCM"
    if pending:
        return "GUEST_AUDOUT_PENDING_WITH_NO_POSTINPUT_CPAL_OR_VIRTUAL_PCM"
    return "OTHER_FULLY_CAPTURED_GUEST_AUDIO_BEHAVIOR"


def verify_run(folder,hint,repeat,run_id,attempt):
    folder=Path(folder)
    require(folder.is_dir() and not folder.is_symlink(),
            f"{hint}/{repeat}: missing actual artifact directory")
    manifest=data(folder/"matrix-identity.json")
    require(manifest.get("schema")=="vh-map02-stage283-guest-matrix-identity/v1"
            and manifest.get("hint_ms")==hint and manifest.get("repeat")==repeat
            and manifest.get("run_id")==run_id and manifest.get("attempt")==attempt,
            "Matrix evidence metadata does not match verified job identity")
    require(manifest.get("expected_host_elf_sha256")==HOST,
            f"{hint}/{repeat}: compiled host SHA declared by matrix differs")
    require(manifest.get("expected_nro_sha256")==NRO,
            f"{hint}/{repeat}: generated guest NRO SHA declared by matrix differs")
    require(manifest.get("runner_os")=="Linux",
            f"{hint}/{repeat}: matrix runner OS is not Linux")
    require(type(manifest.get("job_label")) is str,
            f"{hint}/{repeat}: nonstring matrix job label")
    require(manifest["job_label"]==f"hint{hint}-repeat{repeat}",
            f"{hint}/{repeat}: wrong job label within archived matrix receipt")
    provenance=data(folder/"pinned-host-and-nro.json")
    require(provenance["schema"]==f"vh-map02-stage{281 if hint==21 else 280}-guest-host-pair/v1",
            "Inherited guest provenance schema mismatch")
    require(provenance["new_host_executable_sha256"]==HOST
            and provenance["guest_nro_sha256"]==NRO
            and provenance["guest_original_research_source_sha"]==NRO_SOURCE
            and provenance["old_guest_artifact_run_id"]==NRO_BUILD_RUN,
            "Host or NRO source/content changed across matrix jobs")
    require(provenance["actual_new_trial_run_id"]==run_id
            and provenance["trial_attempt"]==attempt
            and provenance["pulse_hint_ms"]==hint,
            "Actual recorded hint/run ID conflicts with matrix")
    host=data(folder/"host-identity.json")
    require(host["result"]=="EXACT_SOURCE_INSTRUMENTED_HOST_ELF_ARTIFACT_VERIFIED"
            and host["observed_elf_sha256"]==HOST
            and host["pinned_nexium_source_sha"]==
                "089562567a0a8760dfdd8420e1f57c35159a9219",
            "Compiled NeXium ELF identity receipt invalid")
    saved_pre=data(folder/"guest-prejoin-stage.json")
    decoded_pre=decode_prejoin(folder/"guest-prejoin.png")
    require(saved_pre==decoded_pre
            and decoded_pre["result"]=="PREJOIN_STAGE_SNAPSHOT_CAPTURED",
            "Guest prejoin PNG does not independently agree with decoded atomic counters")
    saved_final=data(folder/"guest-final-receipt.json")
    actual_final=observed_guest_final(folder/"guest-final.png")
    require(saved_final==actual_final,
            "Original final guest PNG CRC receipt differs from independent re-decode")
    f=int((folder/"guest-first-input-monotonic-ns.txt").read_text().strip())
    end=int((folder/"guest-final-observation-monotonic-ns.txt").read_text().strip())
    host_timeline=parse_host(folder/"host-cpal-audioout-timeline.csv",f,end)
    require(host_timeline==data(folder/"host-cpal-audioout-audit.json")
            and host_timeline["guest_input_and_final_markers_verified"] is True,
            "Raw CPAL/AudioOut CSV or monotonic guest markers do not match receipt")
    pcm=(folder/"virtual-pulse-48k-stereo-s16le.pcm").read_bytes()
    require(100000<len(pcm)<100000000 and len(pcm)%4==0,
            "Missing or invalid raw virtual 48k stereo S16LE capture")
    pcm_report=data(folder/"virtual-pcm-health.json")
    require(pcm_report.get("raw_sha256")==hashlib.sha256(pcm).hexdigest()
            and pcm_report.get("bytes")==len(pcm)
            and pcm_report.get("valid_pcm16le_stereo") is True
            and pcm_report.get("physical_switch_dac_proven") is False,
            "Virtual PCM report differs from raw bytes or overstates physical audio")
    samples=array("h")
    samples.frombytes(pcm)
    if sys.byteorder!="little":
        samples.byteswap()
    nonzero=sum(v!=0 for v in samples)
    require(pcm_report["nonzero_pcm16_samples"]==nonzero,
            "Captured PCM16 nonzero-sample count disagrees with raw file")
    cp=host_timeline["guest_window_counter_deltas"]
    entry={
        "hint_ms":hint,
        "repeat":repeat,
        "run_id":run_id,
        "run_attempt":attempt,
        "matrix_job_label":manifest["job_label"],
        "identical_compiled_host_sha256":HOST,
        "identical_generated_nro_sha256":NRO,
        "host_timeline_observed_ms":host_timeline["observed_span_ms"],
        "host_cpal_reporter_samples":host_timeline["sample_count"],
        "prejoin_stage":decoded_pre["stage_name"],
        "prejoin_guest_audout_entries":decoded_pre["audout_playbuffer_call_entries"],
        "prejoin_guest_audout_returns":decoded_pre["audout_playbuffer_call_returns"],
        "strict_guest_result":actual_final["result"],
        "strict_guest_pages":actual_final.get("observed_pages",0),
        "cpal_callback_entries":cp["cpal_entries"],
        "cpal_callback_returns":cp["cpal_returns"],
        "cpal_output_frames":cp["cpal_output_frames"],
        "audioout_appends":cp["audioout_appends"],
        "audioout_releases":cp["audioout_releases"],
        "audioout_accepted_frames":cp["audioout_accepted_frames"],
        "virtual_pcm_sha256":hashlib.sha256(pcm).hexdigest(),
        "virtual_pcm_bytes":len(pcm),
        "nonzero_virtual_pcm16":nonzero,
        "raw_guest_images_and_host_csv_and_pcm_redecoded":True,
    }
    entry["observed_behavior"]=describe_behavior(entry)
    return entry


def aggregate(records,run_id,attempt):
    require(len(records)==6,"Six distinct complete optical/CPAL/PCM guest jobs required")
    observed={(x["hint_ms"],x["repeat"]) for x in records}
    require(observed=={(h,i) for h in (21,22) for i in (1,2,3)},
            "Wrong 21/22ms repeat distribution, or duplicate jobs")
    require(all(x["run_id"]==run_id and x["run_attempt"]==attempt
                and x["identical_compiled_host_sha256"]==HOST
                and x["identical_generated_nro_sha256"]==NRO
                and x["raw_guest_images_and_host_csv_and_pcm_redecoded"] is True
                for x in records),
            "Run ID, source SHA, or independent raw-evidence verification mismatch")
    ordered=sorted(records,key=lambda x:(x["hint_ms"],x["repeat"]))
    positive="GUEST_COMPLETED_8_CRC_PAGES_WITH_REAL_VIRTUAL_PCM"
    pending="GUEST_AUDOUT_PENDING_WITH_NO_POSTINPUT_CPAL_OR_VIRTUAL_PCM"
    reproducible=all((x["observed_behavior"]==pending if x["hint_ms"]==21
                      else x["observed_behavior"]==positive) for x in ordered)
    return {
        "schema":SCHEMA,
        "result":("SIX_INDEPENDENT_GUEST_RUNNERS_REPRODUCED_21_22_CONTRAST"
                  if reproducible else
                  "SIX_COMPLETE_GUEST_RUNNERS_SHOW_MIXED_OR_DIFFERENT_BEHAVIOR"),
        "requested_latency_hint_ms":[21,22],
        "attempts_per_hint":3,
        "distinct_ci_jobs":6,
        "actual_ci_run_id":run_id,
        "actual_ci_attempt":attempt,
        "exact_compiled_nexium_elf_sha256":HOST,
        "exact_research_guest_nro_sha256":NRO,
        "all_actual_optical_png_cpal_csv_and_raw_pcm_redecoded":True,
        "single_run_not_replication_claim":False,
        "identical_binary_host_and_nro_across_six":True,
        "repeated_contrast_observed":reproducible,
        "latency_hint_not_a_measured_hardware_period":True,
        "permanent_audout_deadlock_or_cpal_root_cause_proven":False,
        "physical_nintendo_switch_audio_proven":False,
        "original_game_rom_or_soundtrack_included":False,
        "trials":ordered,
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root",required=True,type=Path)
    ap.add_argument("--run-id",required=True,type=int)
    ap.add_argument("--attempt",required=True,type=int)
    ap.add_argument("--output",required=True,type=Path)
    a=ap.parse_args()
    try:
        rows=[verify_run(a.root/f"hint{h}-repeat{i}",h,i,a.run_id,a.attempt)
              for h in (21,22) for i in (1,2,3)]
        result=aggregate(rows,a.run_id,a.attempt)
        rc=0
    except (OSError,UnicodeError,ValueError,TypeError,KeyError,IndexError,
            OverflowError,json.JSONDecodeError) as exc:
        result={"schema":SCHEMA,"result":"UNVERIFIED",
                "reason":str(exc),
                "repeated_contrast_observed":False,
                "permanent_audout_deadlock_or_cpal_root_cause_proven":False,
                "physical_nintendo_switch_audio_proven":False}
        rc=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps(result,sort_keys=True,indent=2))
    return rc


if __name__=="__main__":
    raise SystemExit(main())
