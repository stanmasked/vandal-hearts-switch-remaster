#!/usr/bin/env python3
"""Stage300: source-bound real PulseAudio sink-input lineage from Stage299 guests.

Only two UNSYNCHRONIZED snapshots from the SAME runner at pre-input and late
guest observation. Never infer exact stream replacement time, CPAL stream
ownership, ALSA/device activity or a cause from an uncorked Pulse sink-input.
Suppress original PIDs, usernames, hostnames, addresses and raw properties.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from audit_map02_cpal_lifetime_stage299 import analyze as reparse_p_l

SCHEMA="vh-map02-stage300-real-pulse-sink-input-lineage/v1"
STAGE299_RUN=39511807796
STAGE299_HEAD="fb7f3d9d0b7a25cb4a4cf067abcaf0f2fe92bfc4"
HOST_SHA="fb154cbd581826a4f217485eff338badf0ea14c28a82bff258e7baf32c84153a"
NRO_SHA="371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b"
ROUTES=(("float32le",2,48000),("float32le",32,384000))

def require(condition,message):
    if not condition:
        raise ValueError(message)

def read_json(path):
    obj=json.loads(Path(path).read_text(encoding="utf8"))
    require(isinstance(obj,dict),"Expected a source JSON object")
    return obj

def extract_one(text,regex,label):
    found=re.findall(regex,text,re.MULTILINE)
    require(len(found)==1,"Missing or ambiguous sink-input "+label)
    return found[0]

def parse_pulse_snapshot(path):
    path=Path(path)
    require(path.is_file() and not path.is_symlink(),
            "Original PulseAudio snapshot unavailable")
    raw=path.read_bytes()
    require(250<=len(raw)<=64*1024,"PulseAudio snapshot length invalid")
    try:
        text=raw.decode("utf8")
    except UnicodeDecodeError as e:
        raise ValueError("Snapshot is not UTF-8") from e
    parts=re.split(r"(?m)^Sink Input #(\d+)\s*$",text)
    require(len(parts)>=3 and len(parts)%2==1 and not parts[0].strip(),
            "Malformed PulseAudio sink-input sections")
    entries=[]
    for idx in range(1,len(parts),2):
        number=int(parts[idx])
        item=parts[idx+1]
        spec=extract_one(item,
            r"^\s*Sample Specification:\s*(\w+)\s+(\d+)ch\s+(\d+)Hz\s*$",
            "Sample Specification")
        codec,channels,rate=spec
        corked=extract_one(item,r"^\s*Corked:\s*(yes|no)\s*$","Corked")
        muted=extract_one(item,r"^\s*Mute:\s*(yes|no)\s*$","Mute")
        client=int(extract_one(item,r"^\s*Client:\s*(\d+)\s*$","Client"))
        sink=int(extract_one(item,r"^\s*Sink:\s*(\d+)\s*$","Sink"))
        binary=extract_one(item,
            r'^\s*application\.process\.binary\s*=\s*"([^"]+)"\s*$',
            "application.process.binary")
        app=extract_one(item,
            r'^\s*application\.name\s*=\s*"([^"]+)"\s*$',
            "application.name")
        pid=extract_one(item,
            r'^\s*application\.process\.id\s*=\s*"(\d+)"\s*$',
            "application.process.id")
        media=extract_one(item,
            r'^\s*media\.name\s*=\s*"([^"]+)"\s*$',
            "media.name")
        entry={
            "sink_input_id":number,
            "sample_format":codec,"channels":int(channels),"rate_hz":int(rate),
            "corked":corked=="yes","muted":muted=="yes",
            "client":client,"sink":sink,"binary":binary,
            "application":app,"media":media,
            "_private_run_pid":pid,
        }
        require(entry["binary"]=="nexium" and
                entry["application"]=="ALSA plug-in [nexium]" and
                entry["media"]=="ALSA Playback",
                "Unrecognized PulseAudio application attribution")
        entries.append(entry)
    require(len(entries)==2,"Expected exactly the two original NeXium sink inputs")
    require(len({e["sink_input_id"] for e in entries})==len(entries),
            "Duplicate sink-input ID")
    observed={(x["sample_format"],x["channels"],x["rate_hz"]) for x in entries}
    require(observed==set(ROUTES),
            "Unexpected original NeXium PulseAudio stream format/profile")
    require(len({e["_private_run_pid"] for e in entries})==1,
            "Snapshot includes multiple unrelated NeXium processes")
    return {
        "original_snapshot_sha256":hashlib.sha256(raw).hexdigest(),
        "original_snapshot_bytes":len(raw),
        "by_route":{
            (e["sample_format"],e["channels"],e["rate_hz"]):e for e in entries
        },
    }

def derived_entry(e):
    # PID and raw process/host properties must never enter the report.
    return {k:e[k] for k in ("sink_input_id","corked","muted",
                              "client","sink","sample_format",
                              "channels","rate_hz")}

def audit_one(root,hint):
    root=Path(root)
    require(root.is_dir() and not root.is_symlink(),"Source run evidence absent")
    identity=read_json(root/"stage299-pinned-new-host-guest.json")
    receipt=read_json(root/"stage299-source-pinned-real-lifetime-receipt.json")
    pproof=read_json(root/"host-cpal-lifetime-audit.json")
    pcm=read_json(root/"virtual-pcm-health.json")
    require(identity["schema"]=="vh-map02-stage299-pinned-new-elf-and-generated-nro/v1"
            and identity["actual_stage299_run_id"]==STAGE299_RUN
            and identity["attempt"]==1
            and identity["hint_ms"]==hint
            and identity["stage298_build_run_id"]==39509934054
            and identity["exact_stage298_elf_sha256"]==HOST_SHA
            and identity["exact_generated_nro_sha256"]==NRO_SHA
            and identity["rom_or_licensed_audio_used"] is False,
            "Stage299 original independently verified ELF/NRO identity changed")
    require(receipt["schema"]=="vh-map02-stage299-real-new-elf-lifetime-guest-evidence/v1"
            and receipt["result"]==
                 "REAL_STAGE299_NEW_SHA_PINNED_P_L_GUEST_FILELOGGER_VERIFIED"
            and receipt["actual_run_id"]==STAGE299_RUN
            and receipt["hint_ms"]==hint
            and receipt["stage298_compiled_elf_sha256"]==HOST_SHA
            and receipt["original_generated_nro_sha256"]==NRO_SHA
            and receipt["actual_P_reporter_redecoded"] is True
            and receipt["actual_original_L_reporter_redecoded"] is True
            and receipt["actual_guest_prejoin_and_final_png_redecoded"] is True
            and receipt["actual_virtual_pcm_sha256_and_nonzero_count_redecoded"] is True
            and receipt["raw_gui_filelogger_uploaded"] is False
            and receipt["physical_switch_audio_proven"] is False,
            "Stage299 original genuine guest/FileLogger proof changed")
    require(pproof["result"]=="REAL_SOURCE_SYNCHRONIZED_CPAL_P_AND_L_REPARSED",
            "Stage299 original P+L proof changed")
    a=int((root/"guest-first-input-monotonic-ns.txt").read_text().strip())
    b=int((root/"guest-final-observation-monotonic-ns.txt").read_text().strip())
    fresh=reparse_p_l(root/"host-cpal-lifetime-p.csv",
                      root/"host-cpal-audioout-timeline.csv",a,b)
    require(fresh==pproof,
            "Original Stage299 genuine monotonic P/L raw proof does not match")
    require(receipt["host_L_guest_window_callback_delta"]==
            fresh["guest_window_original_l_cpal_entry_delta"]
            and receipt["host_P_guest_window_callback_delta"]==
            fresh["guest_window_p_cpal_entry_delta"]
            and receipt["host_P_last_counter"]==
            fresh["final_p_cpal_entry_counter"],
            "Stage299 P/L counters do not match guest receipt")
    original_pcm=(root/"virtual-pulse-48k-stereo-s16le.pcm").read_bytes()
    require(len(original_pcm)>100_000 and len(original_pcm)%4==0
            and hashlib.sha256(original_pcm).hexdigest()==pcm["raw_sha256"]
            and pcm["bytes"]==len(original_pcm)
            and pcm["valid_pcm16le_stereo"] is True
            and pcm["nonzero_pcm16_samples"]==receipt["virtual_pcm_nonzero_samples"]
            and pcm["physical_switch_dac_proven"] is False,
            "Original virtual PCM raw SHA/health mismatch")
    during=parse_pulse_snapshot(root/"pulse-sink-inputs-during.txt")
    after=parse_pulse_snapshot(root/"pulse-sink-inputs-after.txt")
    before_by=during["by_route"];after_by=after["by_route"]
    pids={e["_private_run_pid"] for e in
          list(before_by.values())+list(after_by.values())}
    require(len(pids)==1,
            "Pulse snapshots do not refer to the same guest NeXium process")
    routes=[]
    for route in ROUTES:
        d=before_by[route];e=after_by[route]
        require(d["client"]==e["client"] and d["sink"]==e["sink"],
                "Cannot establish same Pulse client/sink lineage across samples")
        routes.append({
            "profile":f"{route[1]}ch_{route[2]}Hz_{route[0]}",
            "during":derived_entry(d),
            "after":derived_entry(e),
            "same_pulse_client_and_sink_across_samples":True,
            "same_sink_input_id_across_samples":
                d["sink_input_id"]==e["sink_input_id"],
            "observed_sink_input_id_replacement":
                d["sink_input_id"]!=e["sink_input_id"],
            "both_snapshots_uncorked":
                not d["corked"] and not e["corked"],
            "both_snapshots_unmuted":
                not d["muted"] and not e["muted"],
        })
    return {
        "hint_ms":hint,
        "source_stage299_run_id":STAGE299_RUN,
        "new_elf_sha256":HOST_SHA,
        "generated_guest_nro_sha256":NRO_SHA,
        "snapshot_during_sha256":during["original_snapshot_sha256"],
        "snapshot_after_sha256":after["original_snapshot_sha256"],
        "same_nexium_process_in_both_snapshots_verified":True,
        "raw_process_pids_and_hostnames_excluded_from_report":True,
        "guest_window_cpal_callback_entry_delta":
            receipt["host_L_guest_window_callback_delta"],
        "guest_window_cpal_error_callback_delta":
            receipt["host_L_guest_window_error_callback_delta"],
        "virtual_pcm_nonzero_samples":receipt["virtual_pcm_nonzero_samples"],
        "guest_optical_result":receipt["guest_final_optical_result"],
        "stream_play_ok_event_ns":receipt["host_P_play_ok_ns"],
        "routes":routes,
    }

def audit(root):
    root=Path(root)
    expected={f"map02-stage299-new-host-P-L-hint{hint}-evidence" for hint in (21,22)}
    require(root.is_dir(),"Source artifact parent absent")
    got={p.name for p in root.iterdir() if p.is_dir()}
    require(got==expected,
            "Stage299 immutable source artifact pair missing/extra/misnamed")
    runs=[audit_one(root/f"map02-stage299-new-host-P-L-hint{hint}-evidence",hint)
          for hint in (21,22)]
    require(runs[0]["new_elf_sha256"]==runs[1]["new_elf_sha256"]
            and runs[0]["generated_guest_nro_sha256"]==
                runs[1]["generated_guest_nro_sha256"],
            "Independent trials used unequal source build/guest")
    return {
        "schema":SCHEMA,
        "result":"REAL_STAGE299_PULSE_SINK_INPUT_LINEAGE_REPARSED",
        "original_independent_actions_run_id":STAGE299_RUN,
        "original_stage299_head_sha":STAGE299_HEAD,
        "source_host_elf_sha256":HOST_SHA,
        "source_generated_guest_nro_sha256":NRO_SHA,
        "trials":runs,
        "snapshot_order_during_then_after_not_event_timestamps":True,
        "pulse_sink_input_uncorked_does_not_prove_cpal_callbacks_or_playback":True,
        "sink_input_id_change_not_proof_of_alsa_or_cpal_causality":True,
        "pulse_profile_not_proven_equivalent_to_one_specific_cpal_stream":True,
        "two_trials_do_not_establish_statistical_reliability":True,
        "backend_root_cause_or_production_audio_fix_proven":False,
        "original_ps1_soundtrack_or_switch_speaker_tested":False,
    }

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    try:
        report=audit(args.root);rc=0
    except (ValueError,KeyError,TypeError,OSError,UnicodeError,
            json.JSONDecodeError) as err:
        report={
            "schema":SCHEMA,"result":"UNVERIFIED","reason":str(err),
            "backend_root_cause_or_production_audio_fix_proven":False,
            "original_ps1_soundtrack_or_switch_speaker_tested":False,
        }
        rc=1
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,indent=2,sort_keys=True))
    return rc

if __name__=="__main__":
    raise SystemExit(main())
