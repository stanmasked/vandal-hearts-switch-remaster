#!/usr/bin/env python3
"""Stage301 actual Pulse subscribe RECEIPT timestamps, coupled to genuine CPAL P/L.

No Pulse server event timestamps are available from 'pactl subscribe': monotonic
times below are when our separate Python reader received each line. A changed
sink input does NOT establish CPAL/ALSA recreation or a causal audio fix.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from audit_map02_cpal_lifetime_stage299 import analyze as parse_host
from audit_map02_pulse_sinks_stage300 import parse_pulse_snapshot, ROUTES

SCHEMA="vh-map02-stage301-pulse-subscribe-monotonic-real-guest/v1"
HOST_SHA="fb154cbd581826a4f217485eff338badf0ea14c28a82bff258e7baf32c84153a"
NRO_SHA="371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b"
MAX_ROWS=20_005

def require(condition,msg):
    if not condition:
        raise ValueError(msg)

def source_marker(root,name):
    path=root/name
    require(path.is_file() and not path.is_symlink(),"Missing original monotonic "+name)
    try:
        raw=path.read_text(encoding="ascii")
        val=int(raw.strip())
    except (ValueError,UnicodeError) as e:
        raise ValueError("Invalid original monotonic marker "+name) from e
    require(0<val<2**64,"Bad original monotonic marker "+name)
    return val

def parse_subscribe(path):
    path=Path(path)
    require(path.is_file() and not path.is_symlink(),"Real Pulse subscribe receipt missing")
    raw=path.read_bytes()
    require(20<len(raw)<=900000,"Real Pulse subscribe receipt absent or over limit")
    try:
        rows=list(csv.reader(raw.decode("ascii").splitlines()))
    except UnicodeError as e:
        raise ValueError("Non-ASCII Pulse subscribe receipt") from e
    require(3<=len(rows)<=MAX_ROWS,"No bounded Stage301 Pulse subscribe records")
    results=[]
    for line in rows:
        require(len(line)==3,"Invalid sanitized subscribe row schema")
        tag,when,identifier=line
        require(tag in ("S","new","remove","change"),
                "Unexpected unsanitized Pulse subscription event")
        try:
            clock=int(when)
        except ValueError as e:
            raise ValueError("Pulse receipt clock not numeric") from e
        require(0<clock<2**64,"Pulse receive time nonmonotonic/uint64 invalid")
        if tag=="S":
            require(identifier in ("monitor_started","monitor_stopped",
                                   "event_limit_reached"),
                    "Unknown Pulse subscribe marker")
            id_safe=identifier
        else:
            try:
                id_safe=int(identifier)
            except ValueError as e:
                raise ValueError("Non-numeric sink-input identifier") from e
            require(0<=id_safe<=2**32-1,"Sink-input identifier out of range")
        if results:
            require(results[-1]["received_ns"]<=clock,
                    "Pulse event receipt times decreased")
        results.append({"kind":tag,"received_ns":clock,"id":id_safe})
    require(results[0]["kind"]=="S" and results[0]["id"]=="monitor_started",
            "Pulse subscription was not initialized")
    require(results[-1]["kind"]=="S" and results[-1]["id"]=="monitor_stopped",
            "Pulse subscription did not finish cleanly")
    require(sum(e["kind"]=="S" and e["id"]=="monitor_started" for e in results)==1
            and sum(e["kind"]=="S" and e["id"]=="monitor_stopped" for e in results)==1,
            "Ambiguous Pulse subscribe begin/end")
    require(any(e["kind"]=="new" for e in results),
            "No REAL sink input 'new' notifications were observed")
    return results,hashlib.sha256(raw).hexdigest()

def event_phase(clock,snap_d_start,snap_d_end,guest_input,
                snap_a_start,snap_a_end,final):
    if clock<snap_d_start:
        return "BEFORE_FIRST_SNAPSHOT_STARTED"
    if clock<=snap_d_end:
        return "DURING_FIRST_SNAPSHOT_CAPTURE"
    if clock<guest_input:
        return "AFTER_FIRST_SNAPSHOT_BEFORE_GUEST_INPUT"
    if clock<snap_a_start:
        return "BETWEEN_GUEST_INPUT_AND_LATE_SNAPSHOT"
    if clock<=snap_a_end:
        return "DURING_LATE_SNAPSHOT_CAPTURE"
    if clock<=final:
        return "AFTER_LATE_SNAPSHOT_BEFORE_GUEST_FINAL_MARKER"
    return "AFTER_GUEST_FINAL_MARKER"

def audit(root,hint,run_id):
    root=Path(root)
    require(root.is_dir() and not root.is_symlink(),"Actual Stage301 evidence root missing")
    require(hint in (21,22) and type(run_id) is int and run_id>0,
            "Stage301 actual Actions identity missing")
    pinned=json.loads((root/"stage299-pinned-new-host-guest.json").read_text())
    stage299=json.loads((root/"stage299-source-pinned-real-lifetime-receipt.json").read_text())
    require(pinned["schema"]=="vh-map02-stage299-pinned-new-elf-and-generated-nro/v1"
            and pinned["actual_stage299_run_id"]==run_id
            and pinned["attempt"]==1
            and pinned["hint_ms"]==hint
            and pinned["stage298_build_run_id"]==39509934054
            and pinned["stage298_build_source_sha"]==
                "e801588983a866c76dcedb52e818859a68ad113d"
            and pinned["exact_stage298_elf_sha256"]==HOST_SHA
            and pinned["exact_generated_nro_sha256"]==NRO_SHA,
            "Actual compiled host/generated NRO identity mismatch")
    require(stage299["result"]=="REAL_STAGE299_NEW_SHA_PINNED_P_L_GUEST_FILELOGGER_VERIFIED"
            and stage299["actual_run_id"]==run_id
            and stage299["hint_ms"]==hint
            and stage299["stage298_compiled_elf_sha256"]==HOST_SHA
            and stage299["original_generated_nro_sha256"]==NRO_SHA
            and stage299["actual_P_reporter_redecoded"] is True
            and stage299["actual_original_L_reporter_redecoded"] is True
            and stage299["actual_guest_prejoin_and_final_png_redecoded"] is True
            and stage299["actual_virtual_pcm_sha256_and_nonzero_count_redecoded"] is True,
            "Stage299 independent actual guest proof failed")
    guest_input=source_marker(root,"guest-first-input-monotonic-ns.txt")
    final=source_marker(root,"guest-final-observation-monotonic-ns.txt")
    host=parse_host(root/"host-cpal-lifetime-p.csv",
                    root/"host-cpal-audioout-timeline.csv",guest_input,final)
    require(host==json.loads((root/"host-cpal-lifetime-audit.json").read_text())
            and host["result"]=="REAL_SOURCE_SYNCHRONIZED_CPAL_P_AND_L_REPARSED"
            and stage299["host_L_guest_window_callback_delta"]==
                host["guest_window_original_l_cpal_entry_delta"],
            "Stage301 actual P/L host counters not source-verified")
    during_start=source_marker(root,"pulse-snapshot-during-start-ns.txt")
    during_end=source_marker(root,"pulse-snapshot-during-end-ns.txt")
    after_start=source_marker(root,"pulse-snapshot-after-start-ns.txt")
    after_end=source_marker(root,"pulse-snapshot-after-end-ns.txt")
    ready=source_marker(root,"pulse-event-subscriber-ready-ns.txt")
    records,receipt_sha=parse_subscribe(root/"pulse-sink-input-events-monotonic.csv")
    watch_start=records[0]["received_ns"]
    watch_end=records[-1]["received_ns"]
    require(watch_start<=ready<=during_start<=during_end<guest_input<
            after_start<=after_end<=final<watch_end,
            "Subscriber and actual guest/Pulse snapshots not same ordered monotonic clock")
    before=parse_pulse_snapshot(root/"pulse-sink-inputs-during.txt")
    after=parse_pulse_snapshot(root/"pulse-sink-inputs-after.txt")
    pids={e["_private_run_pid"] for e in
          list(before["by_route"].values())+list(after["by_route"].values())}
    require(len(pids)==1,"Different NeXium guest process in Pulse snapshots")
    events=[e for e in records if e["kind"]!="S"]
    routes=[]
    for route in ROUTES:
        b=before["by_route"][route];a=after["by_route"][route]
        require(b["client"]==a["client"] and b["sink"]==a["sink"],
                "Pulse profile changed owning client/sink across guest snapshots")
        ids={b["sink_input_id"],a["sink_input_id"]}
        matched=[e for e in events if e["id"] in ids]
        after_new=[e for e in matched
                   if e["kind"]=="new" and e["id"]==a["sink_input_id"]]
        if b["sink_input_id"]!=a["sink_input_id"]:
            require(after_new,
                    "Replaced sink-input ID was not observed in real subscribe stream")
        routes.append({
            "profile":f"{route[1]}ch_{route[2]}Hz_{route[0]}",
            "during_sink_input_id":b["sink_input_id"],
            "late_sink_input_id":a["sink_input_id"],
            "both_snapshots_uncorked":not b["corked"] and not a["corked"],
            "both_snapshots_unmuted":not b["muted"] and not a["muted"],
            "same_pulse_sink_and_client":True,
            "sink_input_id_replaced":b["sink_input_id"]!=a["sink_input_id"],
            "notification_count_for_observed_ids":len(matched),
            "first_new_for_late_sink_input_RECEIVED_ns":
                after_new[0]["received_ns"] if after_new else None,
            "first_new_for_late_sink_input_received_phase":
                event_phase(after_new[0]["received_ns"],
                    during_start,during_end,guest_input,after_start,after_end,final)
                if after_new else "NOT_OBSERVED",
            "notifications_for_observed_sink_input_ids":[
                {"kind":e["kind"],"id":e["id"],
                 "received_ns":e["received_ns"],
                 "phase":event_phase(e["received_ns"],during_start,during_end,
                                    guest_input,after_start,after_end,final)}
                for e in matched[:80]
            ],
            "notifications_truncated_to_80":len(matched)>80,
        })
    return {
        "schema":SCHEMA,
        "result":"REAL_STAGE301_GUEST_CPAL_PULSE_RECEIPT_CLOCKS_REPARSED",
        "hint_ms":hint,
        "source_actions_run_id":run_id,
        "exact_compiled_neXium_elf_sha256":HOST_SHA,
        "exact_generated_research_nro_sha256":NRO_SHA,
        "pulse_subscribe_receipt_sha256":receipt_sha,
        "pulse_during_snapshot_sha256":before["original_snapshot_sha256"],
        "pulse_after_snapshot_sha256":after["original_snapshot_sha256"],
        "pulse_monitor_start_receipt_ns":watch_start,
        "pulse_subscriber_ready_ns":ready,
        "pulse_monitor_last_receipt_ns":watch_end,
        "first_snapshot_window_ns":[during_start,during_end],
        "guest_first_input_monotonic_ns":guest_input,
        "last_snapshot_window_ns":[after_start,after_end],
        "guest_last_observation_monotonic_ns":final,
        "host_cpal_play_return_ok_ns":host["non_rt_event_timestamps_ns"]["play_ok_ns"],
        "host_guest_window_cpal_callback_entries":
            host["guest_window_original_l_cpal_entry_delta"],
        "host_first_l_sample_cpal_callback_entries":host["first_p_cpal_entry_counter"],
        "guest_final_8_page_crc_verified":stage299["guest_8_pages_crc_verified"],
        "virtual_pcm_nonzero_samples":stage299["virtual_pcm_nonzero_samples"],
        "actual_sink_input_notification_count":len(events),
        "sink_input_new_notification_count":sum(e["kind"]=="new" for e in events),
        "sink_input_remove_notification_count":sum(e["kind"]=="remove" for e in events),
        "observed_profile_routes":routes,
        "timestamp_measures_notification_RECEPTION_not_Pulse_generation":True,
        "subscription_startup_may_miss_events":True,
        "pulse_events_not_source_proven_CPAl_callback_or_ALSA_recovery":True,
        "not_excluded_instrumentation_scheduling_perturbation":True,
        "no_original_game_rom_or_PS1_audio_material":True,
        "no_production_audio_fix_or_physical_switch_output_proven":True,
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--hint",type=int,required=True)
    p.add_argument("--run-id",type=int,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try:
        report=audit(a.evidence,a.hint,a.run_id)
        result=0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,
            json.JSONDecodeError,csv.Error) as e:
        report={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(e),
                "no_production_audio_fix_or_physical_switch_output_proven":True}
        result=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps(report,sort_keys=True,indent=2))
    return result

if __name__=="__main__":
    raise SystemExit(main())
