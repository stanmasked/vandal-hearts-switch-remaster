#!/usr/bin/env python3
"""Stage371: two *new* isolated, same-build NeXium audout exit captures.

Each run independently exports original Stage351/357/368 guest SD files.
Rejects ambiguous/linked sources, inconsistent original return tuples, a
missing optical image, stale SD roots, and NRO/run/attempt substitutions.
Never interprets an emulator video frame as physical speaker output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
from pathlib import Path

from audit_nexium_stage368_wait_descriptor import NAMES, audit_directory

VERDICT="STAGE371_TWO_SEPARATE_GUEST_WAIT_TUPLES_FROM_SAME_NRO_RECORDED"
EXPECTED_NRO="SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED"
RUN_GUEST_PATH="sdmc/switch/vandal-hearts-remake"
TRIALS=(("a",6),("b",12))

def demand(condition,reason):
    if not condition:
        raise ValueError(reason)

def regular(path:Path,max_bytes:int)->bool:
    return (path.is_file() and not any(p.is_symlink() for p in (path,*path.parents))
            and 0<path.stat().st_size<=max_bytes)

def load(path:Path)->dict:
    demand(regular(path,8192),"invalid original NRO preflight")
    item=json.loads(path.read_text(encoding="utf-8"))
    demand(type(item) is dict,"preflight is not an object")
    return item

def png_original(path:Path)->str:
    demand(regular(path,5_000_000),"missing optical frame from original NeXium")
    with path.open("rb") as f:
        header=f.read(24)
    demand(len(header)==24 and
           header[:8]==b"\x89PNG\r\n\x1a\n" and
           header[12:16]==b"IHDR" and
           struct.unpack(">II",header[16:24])==(1280,720),
           "not an original-size 1280x720 NeXium screenshot")
    return hashlib.sha256(path.read_bytes()).hexdigest()

def trial(root:Path,run_id:int,tag:str,dwell:int,runner_temp:Path)->dict:
    expected_sd_root=runner_temp/f"vh-nexium-stage266-{run_id}-{tag}"
    guest_pointer=root/"guest-sd-root.txt"
    demand(regular(guest_pointer,1024),"missing exact isolated guest-root locator")
    guest_text=guest_pointer.read_text(encoding="utf-8")
    demand(guest_text==str(expected_sd_root)+"\n",
           "guest SD root not unique to current CI run and trial")
    demand(not expected_sd_root.is_symlink() and expected_sd_root.is_dir(),
           "missing/linked original per-trial guest SD root")
    sd=expected_sd_root/RUN_GUEST_PATH
    demand(sd.is_dir() and not any(p.is_symlink() for p in (sd,*sd.parents)),
           "missing/linked original guest data")
    checked=audit_directory(sd)  # stage351/357/368 genuine source bytes reread
    hashes=checked["source_sha256"]
    optical=png_original(root/"scene-optical-trace.png")
    out={
        "capture_tag":tag,
        "exit_dwell_seconds":dwell,
        "source_guest_sd_root":str(expected_sd_root),
        "source_guest_csv_sha256":hashes,
        "source_guest_reason_code":checked["tail_reason_code"],
        "original_service_result":checked["raw_wait_result"],
        "reported_return_count":checked["reported_released_count"],
        "reported_pointer_present":checked["returned_pointer_present"],
        "reported_pointer_matches_submitted":checked["returned_pointer_matches_submitted"],
        "original_optical_frame_sha256":optical,
        "optical_content_independently_decoded":False,
        "original_guest_speaker_audio_observed":False,
        "guest_source_run_id":run_id,
    }
    return out

def audit(run_id:int,git_sha:str,attempt:int,runner_temp:Path,
          preflight:dict,trial_a:Path,trial_b:Path)->dict:
    demand(type(run_id) is int and run_id>0 and type(attempt) is int and
           attempt>0 and type(git_sha) is str and len(git_sha)==40 and
           all(c in "0123456789abcdef" for c in git_sha),
           "invalid current run identity")
    demand(type(preflight) is dict and preflight.get("result")==EXPECTED_NRO and
           preflight.get("git_sha")==git_sha and
           type(preflight.get("run_id")) is int and preflight["run_id"]==run_id
           and type(preflight.get("run_attempt")) is int
           and preflight["run_attempt"]==attempt and
           type(preflight.get("nro_sha256")) is str and
           len(preflight["nro_sha256"])==64 and
           type(preflight.get("nro_bytes")) is int and
           preflight["nro_bytes"]>=1024 and
           preflight.get("hardware_status")=="HARDWARE NOT TESTED",
           "original NRO not bound to the same CI run and attempt")
    demand(trial_a!=trial_b and trial_a.is_dir() and trial_b.is_dir() and
           not any(x.is_symlink() for root in (trial_a,trial_b)
                   for x in (root,*root.parents)),
           "duplicated or linked trial output")
    receipts=[
        trial(trial_a,run_id,"a",6,runner_temp),
        trial(trial_b,run_id,"b",12,runner_temp)
    ]
    demand(receipts[0]["source_guest_sd_root"]!=receipts[1]["source_guest_sd_root"],
           "reused guest SD source")
    return {
        "schema":"vh-stage371-two-isolated-neXium-exit-sessions/v1",
        "result":VERDICT,
        "source_git_sha":git_sha,
        "source_run_id":run_id,
        "source_run_attempt":attempt,
        "single_verified_nro_sha256":preflight["nro_sha256"],
        "two_isolated_original_guest_roots":True,
        "two_original_guest_source_families_reopened":True,
        "captures":receipts,
        "old_0xEA01_root_cause_proven":False,
        "two_dwell_observations_are_not_a_controlled_causal_pair":True,
        "direct_exit_queue_depth_measured":False,
        "physical_nintendo_switch_audio_tested":False,
    }

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("runner-temp","nro-preflight","trial-a","trial-b","output","preserve-dir"):
        p.add_argument("--"+name,required=True,type=Path)
    p.add_argument("--run-id",required=True,type=int)
    p.add_argument("--run-attempt",required=True,type=int)
    p.add_argument("--git-sha",required=True)
    a=p.parse_args(argv)
    try:
        demand(not a.output.exists() and not a.output.is_symlink(),
               "refuse overwrite of original audit verdict")
        demand(not a.preserve_dir.exists() and not a.preserve_dir.is_symlink(),
               "refuse overwrite of original guest source archive")
        doc=audit(a.run_id,a.git_sha,a.run_attempt,a.runner_temp,
                  load(a.nro_preflight),a.trial_a,a.trial_b)
        a.preserve_dir.mkdir(parents=True)
        for tag,source in (("a",a.trial_a),("b",a.trial_b)):
            folder=a.preserve_dir/tag
            folder.mkdir()
            expected_root=a.runner_temp/f"vh-nexium-stage266-{a.run_id}-{tag}"
            source_dir=expected_root/RUN_GUEST_PATH
            expected_hashes=doc["captures"][0 if tag=="a" else 1]["source_guest_csv_sha256"]
            for kind,name in NAMES.items():
                data=(source_dir/name).read_bytes()
                demand(hashlib.sha256(data).hexdigest()==expected_hashes[kind],
                       "original guest CSV changed after audit")
                (folder/name).write_bytes(data)
            img=source/"scene-optical-trace.png"
            data=img.read_bytes()
            demand(hashlib.sha256(data).hexdigest()==
                   doc["captures"][0 if tag=="a" else 1]["original_optical_frame_sha256"],
                   "original screenshot changed after audit")
            (folder/img.name).write_bytes(data)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        demand(not any(p.is_symlink() for p in (a.output,*a.output.parents)),
               "linked output evidence")
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(doc,f,indent=2,sort_keys=True)
            f.write("\n")
        print(json.dumps({"result":VERDICT,
                          "run_id":a.run_id,
                          "service_results":[c["original_service_result"] for c in doc["captures"]],
                          "descriptor_counts":[c["reported_return_count"] for c in doc["captures"]],
                          "physical_audio_verified":False},sort_keys=True))
        return 0
    except (ValueError,TypeError,KeyError,OSError,UnicodeError) as exc:
        print(json.dumps({"result":"STAGE371_TWO_GUEST_ORIGINALS_NOT_VERIFIED",
                          "error_kind":type(exc).__name__,
                          "root_cause_proven":False},sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
