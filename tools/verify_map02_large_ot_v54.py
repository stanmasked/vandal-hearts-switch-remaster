#!/usr/bin/env python3
"""v54 independent 256-packet original DrawOTag path / depth-bucket oracle.

Distinct observation types:
- Walk events come from REAL original DrawOTag -> TrcPrim shim, not C's
  intended pre-registration order.
- Summary pixels/hashes are actual original native/2x raster output.
- The expected ordering and BGR555 formulas are independently Python.
All raster inputs are synthetic, no retail asset authentication.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from .verify_map02_pixels_v48 import pack,modulate,blend
from .verify_map02_actual_ot_v53 import S_SEQ

BURSTS=24
COUNT=8
FILLERS=64
TOTAL=256
SCENES=(0,1)
WORKERS=(1,2,4)
FLOAT_RE=re.compile(r"^V54(WALK|TRACE|SUMMARY) (.*)$")
KEY_RE=re.compile(r"([a-z0-9_]+)=(-?[0-9a-f]+)")
WALK_FIELDS={"frame","seq","burst","slot","bucket","filler","type"}
TRACE_FIELDS={"frame","count","registered"}
SUMMARY_FIELDS={"scene","workers","bursts","buckets","packets","native",
"hires","direct","othash","directhash","pixels","clut4","clut8",
"sprite_tpage","sprite_mask","sprite_offset"}

class BadLargeOT(ValueError):pass

def parse(line):
    m=FLOAT_RE.fullmatch(line.strip())
    if m is None:
        if line.startswith("V54"):raise BadLargeOT("malformed original DrawOTag evidence")
        return None
    kind=m.group(1)
    d={}
    for item in m.group(2).split():
        z=KEY_RE.fullmatch(item)
        if not z:raise BadLargeOT("invalid OT evidence field "+item[:40])
        name,val=z.groups()
        if name in d:raise BadLargeOT("duplicate evidence field "+name)
        if name in ("othash","directhash"):
            if not re.fullmatch(r"[0-9a-f]{16}",val):raise BadLargeOT("invalid region hash")
            d[name]=val
        else:
            if not re.fullmatch(r"-?[0-9]+",val):raise BadLargeOT("nondecimal numeric field")
            d[name]=int(val)
    fields={"WALK":WALK_FIELDS,"TRACE":TRACE_FIELDS,"SUMMARY":SUMMARY_FIELDS}[kind]
    if set(d)!=fields:raise BadLargeOT("missing or extra "+kind+" fields")
    return kind,d

def color(scene,x,y):
    if scene not in SCENES:raise BadLargeOT("invalid OT scene")
    out=0
    for k in range(BURSTS):
        for id in S_SEQ[scene]:
            if id==0 or id==3 or id==5:continue
            if id==1:
                if k==0:out=pack(40,64,88)
            elif id==2:
                out=blend(modulate(0x801f,128,128,128,x,y,0),out,0)
            elif id==4:
                out=blend(modulate(0x83e0,128,128,128,x,y,0),out,1)
            elif id==6:
                out=blend(pack(128,0,128),out,3)&0x7fff
            elif id==7:
                out=blend(modulate(0x801f,128,128,128,x,y,0),out,2)
    return out

def ordered_expected(scene):
    events=[]
    for burst in range(BURSTS):
        for slot in range(COUNT):
            events.append((burst,slot,burst//6,0))
    for i in range(FILLERS):
        events.append((-1,i,7,1))
    return events

def audit_worker(lines,threads):
    records={0:{"walk":[]},1:{"walk":[]}}
    errors=[]
    for line in lines:
        try:
            parsed=parse(line)
            if parsed is None:continue
            kind,d=parsed
            frame=d.get("frame",d.get("scene",-1))
            if frame not in (0,1):raise BadLargeOT("unexpected trace frame/scene")
            slot=records[frame]
            if kind=="WALK":
                slot["walk"].append(d)
            elif kind=="TRACE":
                if "trace" in slot:raise BadLargeOT("duplicate full OT trace")
                slot["trace"]=d
            else:
                if "summary" in slot:raise BadLargeOT("duplicate original OT summary")
                slot["summary"]=d
        except (BadLargeOT,KeyError) as e:
            errors.append(str(e))
    out={}
    expected_by_scene={}
    for scene,record in records.items():
        walk=record["walk"]
        if len(walk)!=TOTAL:errors.append(f"scene{scene}: not {TOTAL} real TrcPrim packets")
        expected=ordered_expected(scene)
        kinds={}
        for seq,(e,w) in enumerate(zip(expected,walk)):
            burst,slot,bucket,filler=e
            if (w["frame"],w["seq"],w["burst"],w["slot"],w["bucket"],w["filler"]) != (
                 scene,seq,burst,slot,bucket,filler):
                errors.append(f"scene{scene}: walk order differs from exact bucket/token manifest at {seq}")
                break
            if w["type"]<0 or w["type"]>255:errors.append("out-of-range primitive type")
            signature="TILE" if filler else ("DR_MODE" if S_SEQ[scene][slot] in (0,3,5) else
                  "TILE" if S_SEQ[scene][slot]==1 else "FT4" if S_SEQ[scene][slot] in (2,7) else
                  "SPRT" if S_SEQ[scene][slot]==4 else "F4")
            if signature in kinds and kinds[signature]!=w["type"]:
                errors.append(f"scene{scene}: primitive type for {signature} changes during walk")
            kinds[signature]=w["type"]
        if len(set(kinds.values()))!=5:
            errors.append(f"scene{scene}: original walk did not cover five distinct GPU primitive types")
        trace=record.get("trace")
        if trace is None or (trace["frame"],trace["count"],trace["registered"])!=(scene,TOTAL,TOTAL):
            errors.append(f"scene{scene}: incorrect real TrcPrim frame delimiter")
        summary=record.get("summary")
        if summary is None:
            errors.append(f"scene{scene}: missing original GPU full framebuffer summary")
            continue
        if any(summary[k]!=v for k,v in (
             ("scene",scene),("workers",threads),("bursts",BURSTS),
             ("buckets",4),("packets",TOTAL),("pixels",10240),
             ("clut4",31978),("clut8",31914),("sprite_tpage",166),
             ("sprite_mask",1),("sprite_offset",1))):
            errors.append(f"scene{scene}: source metadata, depth bucket, packet or worker mismatch")
        actual=(summary["native"],summary["hires"],summary["direct"])
        want=(color(scene,88,88),color(scene,177,176),color(scene,177,176))
        if actual!=want:
            errors.append(f"scene{scene}: original GPU overdraw color differs from independent 24-burst BGR555 reference, expected={want}, got={actual}")
        if summary["othash"]!=summary["directhash"]:
            errors.append(f"scene{scene}: original DrawOTag 32x320 HD differs from direct original-C baseline")
        out[str(scene)]={"native":summary["native"],"hires":summary["hires"],
                         "region_hash":summary["othash"],"packets_seen":len(walk),
                         "depth_bucket_counts":{str(j):sum(w["bucket"]==j for w in walk)
                                                for j in (0,1,2,3,7)}}
    if all(str(i) in out for i in SCENES) and out["0"]["native"]==out["1"]["native"]:
        errors.append("reversed semi-transparent FT4 order is not observable")
    return {"schema":"vh-map02-v54-256-real-ot-walk",
            "status":"original_256_ot_verified" if not errors else "refused",
            "synthetic_inputs_only":True,"retail_map_authenticity_proven":False,
            "HD_replacement_approved":False,"threads":threads,
            "scenes":out,"packet_count_per_frame":TOTAL,
            "overlapping_semantic_packets_per_frame":BURSTS*COUNT,
            "depth_sorted_buckets":[0,1,2,3,7],
            "full_hires_pixels_per_scene":10240,
            "errors":errors[:30]}

def cross_worker(logs):
    reports={n:audit_worker(logs[n],n) for n in logs}
    errors=[]
    if set(reports)!=set(WORKERS):errors.append("missing one/two/four worker evidence")
    for n,r in reports.items():
        if r["status"]!="original_256_ot_verified":
            errors.append(f"worker{n} rejected: "+str(r["errors"][:3]))
    if not errors:
        for sc in ("0","1"):
            base=reports[1]["scenes"][sc]
            for threads in (2,4):
                if reports[threads]["scenes"][sc]!=base:
                    errors.append(f"scene{sc}: 1 vs {threads} worker full frame mismatch")
    return {"schema":"vh-map02-v54-256-ot-cross-workers",
            "status":"verified" if not errors else "refused",
            "workers_checked":[1,2,4],"scenes_per_worker":2,
            "packets_walked_per_compiler":TOTAL*2*3,
            "full_HD_halfwords_compared_per_compiler":10240*2*3,
            "retail_map_authenticity_proven":False,"HD_replacement_approved":False,
            "reports":reports,"errors":errors}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("logs",nargs=3,type=Path)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    try:
        logs={}
        for n,path in zip(WORKERS,a.logs):
            if path.stat().st_size>3*1024*1024:raise BadLargeOT("oversized GPU trace")
            logs[n]=path.read_text(encoding="utf-8").splitlines()
        result=cross_worker(logs)
        text=json.dumps(result,sort_keys=True,indent=2)+"\n"
        if a.output:
            with a.output.open("x",encoding="utf-8") as f:f.write(text)
        else:print(text,end="")
        return 0 if result["status"]=="verified" else 1
    except (ValueError,OSError,UnicodeError) as exc:
        print("[v54-gpu] REFUSED: "+str(exc),file=__import__("sys").stderr)
        return 1

if __name__=="__main__":raise SystemExit(main())
