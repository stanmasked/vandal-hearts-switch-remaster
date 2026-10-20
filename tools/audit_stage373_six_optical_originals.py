#!/usr/bin/env python3
"""Stage373: re-audit six original Stage371 guest optical packets without Pillow.

The pixel decoder is independent of Stage267's Pillow-based decoder and uses
only Python stdlib. Archived guest software evidence != physical Switch audio.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

REPO = "stanmasked/vandal-hearts-switch-remaster"
NRO_SHA = "cfc49a8ac8dcfe4704e697c1bea8fc750ea32d498c2942176c2ca9b9cbcae71b"
RESULT = "STAGE373_SIX_ORIGINAL_OPTICAL_GUEST_SCENE_AND_WAIT_PAIRS_VERIFIED"
BASE_SHA = "61143dcf3517f1f3ea60bcc5acb8aa9c803ede3c"
# Historical original GitHub metadata and source hashes are pinned; no
# program argument can replace these original identities or image bytes.
RUNS = {
  39396243731: {
    "head": "8ccf7b4c354e6a78277a0ffe453e714d8a1a5519",
    "merge": "7322cd893638bdcbda168242093c7d20a20d5c85",
    "artifact": 12255245917,
    "digest": "sha256:a8382e51c326e64e09f9ae7dedd238d5494b7c95bdb328fab534b2ed0d0e5f3c",
    "optical": ["ec9720188debd29be6305848c5302aab3402eb8ef7140586f499d53aa8243f00", "2daffa349ab54ce22d53874d80a39f6e49ee1dd22159039707687bac5de9bfea"],
    "reason": ["463f7abf23c6841b812d07b1fb13e3c428915dc5b649c334b4177afc4eda541b", "f7a8d188828edff8456aa7da0da5787a5e5d73c8809c6b5d6f3c240671494cff"],
  },
  39398650528: {
    "head": "90fa8380b625e9c6598dc6ed977e19fe31cdcd80",
    "merge": "14276a2b2326eff4b3d9c8a7de675205261048ed",
    "artifact": 12257811667,
    "digest": "sha256:9065bd14de4c36c957b8b1a0b504f5c8425209c80ddcf34c26d59f174d70794e",
    "optical": ["6426c793c0ade351430dcd4734b67a80696ec1faf59021073e5b388ae2567b52", "dbb90a7e60b0a293d81fcd937f65128b132da15a7479e245625bf4b662448f68"],
    "reason": ["a716ccf15103342546d0a4cace40a759df1912dc51bb155aefae649bd9ad0fe7", "a92f7f84620760404591e45e70b98e2c3961b09d8cf7b11ac673f1d497a89612"],
  },
  39406193313: {
    "head": "d9e3e4d2b55e75d3c9c535d3f37efd9ee1005688",
    "merge": "38318d3080a2813183704b2d9113015a3b51e464",
    "artifact": 12261315952,
    "digest": "sha256:0afef1e1bdd1b05a6acfd8ca7660dfef70a7d329d64217c4842f7a93369bf82a",
    "optical": ["82bafb97bd93c7c2a2a55dab849ac85d7905bb2e5ec05ed761850be753ed7fd9", "c6119322016b73ac9d75d24a27f8762c8e1f396535c9b3737ea3a1c23ae90ec2"],
    "reason": ["dd097652ec427e296deb99789137d4f4d8785c0d0128fe6c005a56a28d969b04", "9f952ad877553e895d8ee696ef98d2e3178e7a6071d0d478e2bf72cd479946f7"],
  },
}
FILES = {"reason":"audio-exit-tail-reason-000.csv", "result":"audio-exit-tail-wait-result-000.csv", "descriptor":"audio-exit-wait-descriptor-000.csv"}
GUEST_STEPS=("First isolated original guest exit with baseline dwell","Second isolated original guest exit with longer dwell","Reopen BOTH original guest SD source families and bind to same NRO","Upload original source receipts without raw sound assets")

def need(condition: bool, description: str):
    if not condition: raise ValueError(description)

def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def safe_bytes(path: Path, bound: int) -> bytes:
    need(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), "missing/linked original: "+path.name)
    stat=path.stat()
    need(stat.st_nlink==1 and 0 < stat.st_size <= bound, "linked/oversized original: "+path.name)
    return path.read_bytes()

def metadata(path: Path) -> dict:
    v=json.loads(safe_bytes(path,256_000).decode("utf-8"))
    need(type(v) is dict,"invalid GitHub JSON")
    return v

def scopes(raw: bytes) -> dict:
    need(0 < len(raw) <= 2048 and raw.startswith(b"scope,value\n") and raw.endswith(b"\n") and b"\r" not in raw,"invalid source CSV framing")
    out={}
    for line in raw.decode("ascii").splitlines()[1:]:
        values=line.split(",")
        need(len(values)==2 and values[0] not in out and values[1].isdecimal() and (len(values[1])==1 or values[1][0]!="0"),"invalid original CSV field")
        out[values[0]]=int(values[1])
    return out

def png_pixels(raw: bytes):
    """Bounded, CRC-verified PNG 8-bit RGB decoder (filters 0-4); no PIL/OCR."""
    need(45 <= len(raw) <= 5_000_000 and raw[:8]==b"\x89PNG\r\n\x1a\n","invalid PNG signature")
    off=8; compressed=[]; got_header=False; got_idat=False; terminal=False
    while off < len(raw):
        need(off+12<=len(raw),"truncated PNG chunk header")
        count=struct.unpack_from(">I",raw,off)[0]
        stop=off+12+count
        need(stop<=len(raw),"truncated PNG chunk")
        kind=raw[off+4:off+8]
        need(zlib.crc32(raw[off+4:off+8+count])==struct.unpack_from(">I",raw,off+8+count)[0],"PNG CRC mismatch")
        if not got_header:
            need(kind==b"IHDR" and count==13 and struct.unpack_from(">IIBBBBB",raw,off+8)==(1280,720,8,2,0,0,0),"wrong PNG dimensions/format")
            got_header=True
        elif kind==b"IHDR":
            raise ValueError("duplicate PNG IHDR")
        elif kind==b"IDAT":
            need(not terminal,"IDAT after PNG end")
            compressed.append(raw[off+8:off+8+count]);got_idat=True
        elif kind==b"IEND":
            need(count==0 and got_idat and stop==len(raw),"bad terminal PNG chunk")
            terminal=True
            break
        else:
            # reject unknown critical PNG chunks; ancillary metadata OK
            need(kind[0]&32 != 0,"unrecognized critical PNG chunk")
        off=stop
    need(terminal,"missing PNG IEND")
    limit=720*(1+1280*3)
    data=zlib.decompressobj()
    decoded=data.decompress(b"".join(compressed),limit+1)
    need(not data.unconsumed_tail and len(decoded)<=limit,"PNG decompression exceeds bound")
    decoded+=data.flush(limit+1-len(decoded))
    need(data.eof and not data.unused_data and len(decoded)==limit,"PNG truncated/oversized decoded pixels")
    pixels=bytearray(720*1280*3)
    stride=1280*3; pos=0
    last=bytes(stride)
    for row in range(720):
        filt=decoded[pos];pos+=1
        need(0 <= filt <= 4,"PNG filter out of range")
        source=decoded[pos:pos+stride];pos+=stride
        current=bytearray(stride)
        for j,value in enumerate(source):
            left=current[j-3] if j>=3 else 0
            up=last[j]
            ul=last[j-3] if j>=3 else 0
            if filt==0:predict=0
            elif filt==1:predict=left
            elif filt==2:predict=up
            elif filt==3:predict=(left+up)//2
            else:
                p=left+up-ul
                a,b,c=abs(p-left),abs(p-up),abs(p-ul)
                predict=left if a<=b and a<=c else (up if b<=c else ul)
            current[j]=(value+predict)&255
        pixels[row*stride:(row+1)*stride]=current
        last=current
    return pixels

def optical_decode(raw: bytes) -> dict:
    pixels=png_pixels(raw)
    def pixel(x,y):
        off=(y*1280+x)*3
        return pixels[off],pixels[off+1],pixels[off+2]
    # Independent decoder: detect the magenta calibration border and its 4 corners.
    x0,y0,x1,y1=1280,720,-1,-1
    markers=0
    for y in range(720):
        for x in range(1280):
            r,g,b=pixel(x,y)
            if r>=185 and b>=185 and g<=85:
                x0=min(x,x0);y0=min(y,y0);x1=max(x,x1);y1=max(y,y1);markers+=1
    w=x1-x0+1;h=y1-y0+1
    need(markers>=700 and w>=500 and h>=300 and abs(w/h-798/476)<0.11,"optical calibration missing")
    for x,y in ((x0+3,y0+3),(x1-3,y0+3),(x0+3,y1-3),(x1-3,y1-3)):
        r,g,b=pixel(x,y)
        need(r>=185 and b>=185 and g<=85,"optical calibration corner damaged")
    packet=bytearray(924)
    for bit in range(924*8):
        col,row=bit%112,bit//112
        x=x0+round((col+1.5)*w/114)
        y=y0+round((row+1.5)*h/68)
        need(0<=x<1280 and 0<=y<720,"bit outside optical frame")
        color=pixel(x,y)
        if min(color)>=177:value=0
        elif max(color)<=80:value=1
        else:raise ValueError("ambiguous optical pixel")
        packet[bit//8]|=value<<(7-bit%8)
    need(packet[:8]==b"VHFBTRC1","guest optical packet magic mismatch")
    count=packet[8];dropped=int.from_bytes(packet[9:13],"little")
    need(count==23 and dropped==0,"missing/dropped guest optical rows")
    need(not any(packet[13+count*14:909]) and not any(packet[913:]),"nonzero optical reserved data")
    crc=zlib.crc32(packet[:909])&0xffffffff
    need(crc==int.from_bytes(packet[909:913],"little"),"guest optical packet CRC mismatch")
    serials={};startup=0
    for i in range(count):
        off=13+i*14
        kind,scene=packet[off],packet[off+1]
        serial=int.from_bytes(packet[off+2:off+6],"little")
        ns=int.from_bytes(packet[off+6:off+14],"little")
        need(1<=kind<=6 and scene<=2 and ns>0,"invalid guest optical event")
        if serial==0:startup+=1;continue
        d=serials.setdefault(serial,{"scene":scene})
        need(d["scene"]==scene and kind not in d,"duplicated/misassigned scene event")
        d[kind]=ns
    need(startup==3 and sorted(serials)==[1,2,3,4],"unexpected guest scene serials")
    observed=[]
    for serial,scene in enumerate([2,1,2,1],start=1):
        item=serials[serial]
        need(item["scene"]==scene and set(k for k in item if type(k) is int)==set(range(1,6)),"missing or reordered guest scenes")
        timings=[item[k] for k in range(1,6)]
        need(timings==sorted(timings),"guest events out of time order")
        observed.append(round((item[5]-item[1])/1e6,3))
    return {"pixel_packet_sha256":sha(bytes(packet)),"pixel_packet_crc32":f"{crc:08x}",
            "guest_event_rows":count,"dropped_guest_events":dropped,
            "complete_scene_serials":4,"input_to_buffer_return_ms":observed,
            "last_release_return_guest_ns":max(serials[k][5] for k in serials)}

def verify(run_id: int, original: Path, meta: Path) -> list[dict]:
    pin=RUNS[run_id]
    run=metadata(meta/f"{run_id}-run.json")
    jobs=metadata(meta/f"{run_id}-jobs.json")
    artifact=metadata(meta/f"{run_id}-artifact.json")
    merge=metadata(meta/f"{run_id}-merge.json")
    need(run.get("id")==run_id and run.get("status")=="completed" and run.get("conclusion")=="success" and run.get("event")=="pull_request" and run.get("head_sha")==pin["head"] and run.get("run_attempt")==1 and run.get("repository",{}).get("full_name")==REPO,"source workflow identity invalid")
    need(merge.get("sha")==pin["merge"] and [p.get("sha") for p in merge.get("parents",[])]==[BASE_SHA,pin["head"]],"unbound PR source commit")
    need(artifact.get("id")==pin["artifact"] and artifact.get("name")=="stage371-two-guest-exit-original-observations" and artifact.get("digest")==pin["digest"] and artifact.get("expired") is False and artifact.get("workflow_run",{}).get("id")==run_id and artifact["workflow_run"].get("head_sha")==pin["head"],"invalid archived artifact origin")
    jobs_list=jobs.get("jobs")
    need(type(jobs_list) is list,"missing workflow jobs")
    relevant={j.get("name"):j for j in jobs_list}
    for name in ("Validate Stage371 isolated-source invariants before building NRO","Build one original libnx NRO without SDL2","Run two separate NeXium guest exits and audit original CSV files"):
        j=relevant.get(name)
        need(j and j.get("run_id")==run_id and j.get("status")=="completed" and j.get("conclusion")=="success","original build or guest job not successful")
    steps=relevant["Run two separate NeXium guest exits and audit original CSV files"].get("steps",[])
    step_names=[s.get("name") for s in steps]
    need(len(step_names)==len(set(step_names)) and all(any(s.get("name")==name and s.get("conclusion")=="success" for s in steps) for name in GUEST_STEPS),"original NeXium/archival steps missing")
    report=metadata(original/"stage371-two-authentic-guest-exits.json")
    manifest=metadata(original/"stage371-nro-preflight.json")
    need(report.get("result")=="STAGE371_TWO_SEPARATE_GUEST_WAIT_TUPLES_FROM_SAME_NRO_RECORDED" and report.get("source_run_id")==run_id and report.get("source_git_sha")==pin["merge"] and report.get("source_run_attempt")==1 and report.get("single_verified_nro_sha256")==NRO_SHA and report.get("two_isolated_original_guest_roots") is True and report.get("old_0xEA01_root_cause_proven") is False and report.get("physical_nintendo_switch_audio_tested") is False,"Stage371 report identity mismatch")
    need(manifest.get("result")=="SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED" and manifest.get("git_sha")==pin["merge"] and manifest.get("nro_sha256")==NRO_SHA and manifest.get("run_id")==run_id and manifest.get("run_attempt")==1 and manifest.get("hardware_status")=="HARDWARE NOT TESTED" and manifest.get("nro_bytes")==299064,"source manifest identity mismatch")
    captures=report.get("captures")
    need(type(captures) is list and len(captures)==2,"not two guest captures")
    answer=[]
    for idx,tag in enumerate(("a","b")):
        item=captures[idx]
        need(item.get("capture_tag")==tag and item.get("exit_dwell_seconds")==[6,12][idx] and item.get("guest_source_run_id")==run_id and item.get("source_guest_sd_root","").endswith(f"vh-nexium-stage266-{run_id}-{tag}") and item.get("original_guest_speaker_audio_observed") is False,"wrong original source guest")
        directory=original/"stage371-originals"/tag
        need(directory.is_dir() and not directory.is_symlink(),"original guest directory absent")
        found={x.name for x in directory.iterdir()}
        expected=set(FILES.values())|{"scene-optical-trace.png","audio-exit-probe-context-000.csv","audio-lease-reconciliation-000.csv"}
        need(found==expected,"ambiguous or missing original guest family")
        parsed={}
        for kind,name in FILES.items():
            raw=safe_bytes(directory/name,1024)
            digest=sha(raw)
            need(item["source_guest_csv_sha256"][kind]==digest,"CSV not bound to original receipt")
            if kind=="reason":need(digest==pin["reason"][idx],"original independent reason SHA changed")
            parsed[kind]=scopes(raw)
        reason,result,desc=parsed["reason"],parsed["result"],parsed["descriptor"]
        need(reason["tail_reason_code"]==result["stage351_tail_reason_code"]==desc["stage351_tail_reason_code"]==7 and result["audout_wait_result_raw"]==desc["audout_wait_result_raw"]==item["original_service_result"]==0 and desc["released_count_reported"]==item["reported_return_count"]==1 and desc["returned_pointer_present"]==desc["returned_pointer_matches_submitted"]==1 and item["reported_pointer_matches_submitted"] is True and reason["abandoned_sessions"]==0 and reason["lease_pages_acquired"]==reason["lease_pages_released"]>0,"guest returned buffer or PCM accounting invalid")
        context={}
        for name in ("audio-exit-probe-context-000.csv","audio-lease-reconciliation-000.csv"):
            raw=safe_bytes(directory/name,2048)
            need(item["optional_original_telemetry"][name]=={"present":True,"parsed":False,"sha256":sha(raw)},"guest optional telemetry hash mismatch")
            context[name]=scopes(raw)
        clock=context["audio-exit-probe-context-000.csv"]
        leases=context["audio-lease-reconciliation-000.csv"]
        need(clock["tail_elapsed_ns"]==clock["tail_end_guest_ns"]-clock["tail_begin_guest_ns"] and 0<clock["tail_elapsed_ns"]<12_000_000 and clock["stage351_tail_reason_code"]==7 and leases["lease_pages_acquired"]==leases["lease_pages_released"]==reason["lease_pages_acquired"] and leases["abandoned_sessions"]==0,"guest clocks or PCM software leases inconsistent")
        raw=safe_bytes(directory/"scene-optical-trace.png",5_000_000)
        need(sha(raw)==pin["optical"][idx]==item["original_optical_frame_sha256"],"original PNG source substitution")
        optical=optical_decode(raw)
        need(optical["last_release_return_guest_ns"]<clock["tail_begin_guest_ns"],"scene event not before tail begin")
        answer.append({"run_id":run_id,"trial":tag,"dwell_seconds":item["exit_dwell_seconds"],"original_optical_sha256":sha(raw),"original_reason_sha256":sha(safe_bytes(directory/FILES["reason"],1024)),"guest_result":0,"released_descriptors":1,"pcm_pages_acquired_and_released":reason["lease_pages_acquired"],"tail_interval_ms":round(clock["tail_elapsed_ns"]/1e6,6),"last_guest_scene_to_tail_ms":round((clock["tail_begin_guest_ns"]-optical["last_release_return_guest_ns"])/1e6,3),**optical})
    return answer

def audit(input_dir:Path,metadata_dir:Path)->dict:
    results=[]
    for id in RUNS:
        results.extend(verify(id,input_dir/str(id),metadata_dir))
    need(len(results)==6 and len({x["pixel_packet_sha256"] for x in results})==6 and len({x["original_reason_sha256"] for x in results})==6 and len({x["original_optical_sha256"] for x in results})==6,"duplicate original guest evidence")
    return {"schema":"vh-stage373-six-independent-original-optical-replays/v1","result":RESULT,"nro_sha256":NRO_SHA,"source_workflow_run_ids":list(RUNS),"all_six_original_guest_waits_succeeded":True,"all_six_optical_packets_unique":True,"sessions":results,"historical_0xEA01_cause_proven":False,"direct_exit_queue_depth_measured":False,"physical_nintendo_switch_audio_tested":False,"new_guest_sessions_created_by_replay":False}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--originals",type=Path,required=True)
    p.add_argument("--metadata",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        need(not a.output.exists() and not a.output.is_symlink(),"refuse overwrite of Stage373 receipt")
        report=audit(a.originals,a.metadata)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x",encoding="utf-8") as f:json.dump(report,f,indent=2,sort_keys=True);f.write("\n")
        print(json.dumps({"result":RESULT,"guest_sessions":6,"original_results":[x["guest_result"] for x in report["sessions"]],"physical_audio_tested":False},sort_keys=True))
        return 0
    except (ValueError,KeyError,IndexError,OSError,UnicodeError,TypeError,zlib.error) as e:
        print(json.dumps({"result":"STAGE373_ORIGINAL_SIX_GUEST_OPTICAL_NOT_VERIFIED","error_kind":type(e).__name__,"old_timeout_cause_proven":False},sort_keys=True))
        return 2

if __name__=="__main__":raise SystemExit(main())
