#!/usr/bin/env python3
"""Stage276: original-SD verified 50+ second audio baseline with NO scene switches.

Guest and NeXium software measurements, not audible DAC output or causality.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

from audit_nexium_audout_queue import (
    stable_guest_bytes,bind_export_receipt,parse_telemetry
)
from audit_nexium_audout_latency import parse_latency
from audit_nexium_audout_scene_correlation import (
    CorrelationError,parse_clock,integer,read_json
)
from audit_nexium_audout_slow_calls import parse_slow

BASE="audio-audout-"
SCENE_HEADER=["index","event","serial","scene","monotonic_ns","dropped_total"]
RUN_CSV="soak-"

def digest(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def original_and_copy(folder:Path,evidence:Path,stem:str,copy_name:str,
                      locations:str,receipt:str|None=None)->bytes:
    originals=list(folder.glob(stem))
    if len(originals)!=1 or originals[0].is_symlink():
        raise CorrelationError("expected one regular original guest SD "+stem)
    locations_path=evidence/locations
    copy_path=evidence/copy_name
    if (locations_path.is_symlink() or copy_path.is_symlink()
            or not copy_path.is_file()
            or copy_path.resolve()==originals[0].resolve()
            or locations_path.read_text(encoding="utf-8").splitlines()
               !=[str(originals[0])]):
        raise CorrelationError("unbound or nonindependent guest SD "+stem)
    raw=stable_guest_bytes(originals[0])
    copied=stable_guest_bytes(copy_path)
    if raw!=copied or stable_guest_bytes(originals[0])!=copied:
        raise CorrelationError("guest original and copied bytes disagree "+stem)
    if receipt is not None:
        bind_export_receipt(evidence/receipt,len(raw))
    return raw

def parse_idle_scene(raw:bytes,origin:int)->list[dict]:
    if (len(raw)>2048 or b"\r" in raw or not raw.endswith(b"\n")):
        raise CorrelationError("idle scene CSV malformed/oversized")
    try:
        rows=list(csv.reader(io.StringIO(raw.decode("ascii"),newline=""),strict=True))
    except (UnicodeError,csv.Error) as exc:
        raise CorrelationError("invalid original idle scene CSV") from exc
    if len(rows)!=4 or rows[0]!=SCENE_HEADER:
        raise CorrelationError("idle control needs exactly 3 startup events; NO INPUTs")
    stamps=[]
    for i,entry in enumerate(rows[1:]):
        if (len(entry)!=6 or entry[:4]!=[
                str(i),("ACCEPT","SUBMIT_CALL","RELEASE_RETURN")[i],"0","1"]
                or entry[5]!="0"):
            raise CorrelationError("scene changed during no-switch control")
        stamps.append(integer(entry[4],allow_zero=False))
    if (stamps!=sorted(set(stamps)) or
            not stamps[1]<=origin<=stamps[2]):
        raise CorrelationError("first audout call outside idle startup submit/return")
    return [{"event":entry[1],"monotonic_ns":stamp}
            for entry,stamp in zip(rows[1:],stamps)]

def audit(*,sd_root:Path,evidence:Path,preflight:Path,
          git_sha:str,run_id:int,run_attempt:int)->dict:
    folder=sd_root/"sdmc"/"switch"/"vandal-hearts-remake"
    if (sd_root.is_symlink() or folder.is_symlink() or
            not sd_root.is_dir() or not folder.is_dir()
            or evidence.is_symlink()):
        raise CorrelationError("missing isolated guest SD root")
    manifest=read_json(preflight)
    if (manifest.get("result")!="SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED"
            or manifest.get("git_sha")!=git_sha
            or manifest.get("run_id")!=run_id
            or manifest.get("run_attempt")!=run_attempt
            or not isinstance(manifest.get("nro_sha256"),str)
            or len(manifest["nro_sha256"])!=64):
        raise CorrelationError("idle control not bound to current-run NRO")
    series={}
    for label,pattern,copy,loc,receipt in [
        ("scene","audio-scene-trace-*.csv","soak-sd-unverified.csv","soak-sd-locations.txt",None),
        ("queue","audio-audout-queue-*.csv","soak-audout-sd-unverified.csv","soak-audout-sd-locations.txt","soak-audout-export-result.txt"),
        ("latency","audio-audout-latency-*.csv","soak-audout-latency-unverified.csv","soak-audout-latency-locations.txt","soak-audout-latency-export-result.txt"),
        ("clock","audio-audout-clock-*.csv","soak-audout-clock-unverified.csv","soak-audout-clock-locations.txt","soak-audout-clock-export-result.txt"),
        ("slow","audio-audout-slow-*.csv","soak-audout-slow-unverified.csv","soak-audout-slow-locations.txt","soak-audout-slow-export-result.txt")
    ]:
        series[label]=original_and_copy(folder,evidence,pattern,copy,loc,receipt)
    clock=parse_clock(series["clock"])
    startup=parse_idle_scene(series["scene"],clock["origin_ns"])
    queue=parse_telemetry(series["queue"])
    latency=parse_latency(series["latency"])
    slow=parse_slow(series["slow"],clock["origin_ns"],latency)
    if (queue["attempts"]!=latency["attempts"] or
            queue["attempts"]!=clock["attempts"] or
            queue["windows"]!=latency["windows"] or
            queue["windows"]!=clock["last_second"]+1 or
            queue["max_call_us"]!=latency["max_call_us"] or
            queue["failed_attempts"]!=0 or latency["failed_attempts"]!=0
            or queue["releases"]!=queue["attempts"]
            or queue["windows"]<50 or
            len(slow)!=latency["from40to50ms_calls"]+latency["ge50ms_calls"]
            or any(not x["returned"] for x in slow)):
        raise CorrelationError("idle audout queue/clock/latency/slow accounting inconsistent")
    event_lines=stable_guest_bytes(evidence/"soak-events.csv")
    try:
        events=list(csv.reader(io.StringIO(event_lines.decode("ascii"),newline=""),
                               strict=True))
    except (UnicodeError,csv.Error) as exc:
        raise CorrelationError("invalid idle host snapshot schedule") from exc
    if (len(events)!=12 or events[0]!=["scene","serial","pcm_bytes","epoch_ms"]
            or events[1][0:2]!=["field_initial","0"]
            or any(row[:2]!=[f"idle_{i}",str(i)]
                   for i,row in enumerate(events[2:],1))):
        raise CorrelationError("control host sent an unexpected music-switch schedule")
    snapshots=[evidence/f"soak-scene-{i:02d}.png" for i in range(11)]
    if any(p.is_symlink() or not p.is_file() or p.stat().st_size<100
           for p in snapshots):
        raise CorrelationError("missing or invalid baseline framebuffer snapshots")
    return {
        "schema":"vh-nexium-no-scene-switch-guest-audout/v1",
        "result":"ORIGINAL_SD_IDLE_50S_AUDOUT_VERIFIED",
        "nro_sha256":manifest["nro_sha256"],
        "git_sha":git_sha,"run_id":run_id,
        "run_attempt":run_attempt,
        "source_mode":"NO_AB_SCENE_KEYS_SENT",
        "guest_scene_change_inputs":0,
        "guest_scene_events":startup,
        "guest_audio_second_windows":latency["windows"],
        "guest_audout_attempts":latency["attempts"],
        "audout_failed_attempts":latency["failed_attempts"],
        "slow_ge40ms_calls":len(slow),
        "slow_ge50ms_calls":latency["ge50ms_calls"],
        "slow_max_call_us":latency["max_call_us"],
        "slow_records_dropped":0,
        "idle_guest_sd_sha256":{k:digest(v) for k,v in series.items()},
        "original_sd_verified_during_run":True,
        "physical_switch_tested":False,
        "audible_underruns_measured":False,
        "baseline_does_not_prove_scene_causality":True,
    }

def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sd-root",type=Path,required=True)
    p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--preflight",type=Path,required=True)
    p.add_argument("--git-sha",required=True)
    p.add_argument("--run-id",type=int,required=True)
    p.add_argument("--run-attempt",type=int,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try:
        if a.output.exists() or a.output.is_symlink():
            raise CorrelationError("refusing to overwrite prior idle report")
        report=audit(sd_root=a.sd_root,evidence=a.evidence,
                     preflight=a.preflight,git_sha=a.git_sha,
                     run_id=a.run_id,run_attempt=a.run_attempt)
        a.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",
                            encoding="utf-8")
        print(json.dumps({"result":report["result"],
            "slow_ge40ms_calls":report["slow_ge40ms_calls"],
            "slow_ge50ms_calls":report["slow_ge50ms_calls"],
            "guest_scene_change_inputs":0},sort_keys=True))
        return 0
    except (ValueError,OSError,UnicodeError,csv.Error) as exc:
        print(json.dumps({"result":"IDLE_AUDIO_CONTROL_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
