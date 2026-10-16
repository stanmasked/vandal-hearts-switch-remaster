#!/usr/bin/env python3
"""Map02 v55: independently verify real original DrawOTag in four screen zones.

256 genuine PsyQ packet visits per synthetic frame, four spatially isolated
six-burst STP/ABR groups, five untouched gap probes, full 2x framebuffer
parity. All inputs synthetic. Retail map authenticity is NEVER claimed.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
from collections import Counter

from .verify_map02_large_ot_v54 import parse as parse_walk, ordered_expected, TOTAL, S_SEQ
from .verify_map02_pixels_v48 import pack, modulate, blend

WORKERS=(1,2,4)
REGIONS=4
GAPS=((120,60),(120,120),(120,180),(120,216),(88,140))
P_RX=re.compile(r"^V55(REGION|GAP|SUMMARY) (.*)$")
PAIR=re.compile(r"([a-z][a-z0-9_]*)=(-?[0-9a-f]+)")
REGION_FIELDS={"scene","workers","region","firstburst","x","y","hx","hy",
               "native","hires","direct","othash","directhash"}
GAP_FIELDS={"scene","workers","slot","x","y","hx","hy","native","hires","direct"}
SUMMARY_FIELDS={"scene","workers","bursts","buckets","packets","native",
                "hires","direct","othash","directhash","pixels","clut4",
                "clut8","sprite_tpage","sprite_mask","sprite_offset",
                "regions","width","height"}
CATEGORIES=("DR_MODE","TILE","FT4","SPRT","F4")
class BadSpatial(ValueError): pass

def parse(line):
    m=P_RX.fullmatch(line.strip())
    if not m:
        if line.startswith("V55"):raise BadSpatial("malformed v55 GPU evidence")
        return None
    kind=m.group(1)
    result={}
    for segment in m.group(2).split():
        found=PAIR.fullmatch(segment)
        if not found:raise BadSpatial("bad GPU evidence field "+segment[:60])
        name,value=found.groups()
        if name in result:raise BadSpatial("duplicate GPU evidence key "+name)
        if name in ("othash","directhash"):
            if not re.fullmatch("[0-9a-f]{16}",value):
                raise BadSpatial("bad 64bit HD region checksum")
            result[name]=value
        else:
            if not re.fullmatch("-?[0-9]+",value):raise BadSpatial("nondecimal source field")
            result[name]=int(value)
    allowed={"REGION":REGION_FIELDS,"GAP":GAP_FIELDS,"SUMMARY":SUMMARY_FIELDS}[kind]
    if set(result)!=allowed:raise BadSpatial("wrong GPU field schema")
    return kind,result

def coords(region):
    return 80+(region&1)*64, (48,108,168,204)[region]

def expected_color(scene,region,x,y):
    """No invocation of original GPU C arithmetic or source fixture bytes."""
    if scene not in (0,1) or region not in range(REGIONS):
        raise BadSpatial("unknown spatial synthetic scene")
    color=0
    for burst in range(region*6,(region+1)*6):
        for primitive in S_SEQ[scene]:
            if primitive in (0,3,5):
                continue
            if primitive==1:
                if burst%6==0:color=pack(40,64,88)
            elif primitive==2:
                front=modulate(0x801f,128,128,128,x,y,0)
                color=blend(front,color,0)
            elif primitive==4:
                front=modulate(0x83e0,128,128,128,x,y,0)
                color=blend(front,color,1)
            elif primitive==6:
                color=blend(pack(128,0,128),color,3)&0x7fff
            elif primitive==7:
                front=modulate(0x801f,128,128,128,x,y,0)
                color=blend(front,color,2)
            else:
                raise BadSpatial("invalid source primitive")
    return color

def category(scene,slot,filler):
    if filler:return "TILE"
    source=S_SEQ[scene][slot]
    return ("DR_MODE" if source in (0,3,5) else "TILE" if source==1
            else "FT4" if source in (2,7) else "SPRT" if source==4 else "F4")

def audit_worker(lines,worker):
    data={0:{"walk":[],"regions":{},"gaps":{}},
          1:{"walk":[],"regions":{},"gaps":{}}}
    errors=[]
    for line in lines:
        try:
            obs=parse_walk(line) if line.startswith("V54") else parse(line)
            if obs is None:continue
            kind,d=obs
            scene=d.get("scene",d.get("frame",-1))
            if scene not in (0,1):raise BadSpatial("unknown scene/frame")
            rec=data[scene]
            if kind=="WALK":
                rec["walk"].append(d)
            elif kind=="TRACE":
                if "trace" in rec:raise BadSpatial("duplicate source frame delimiter")
                rec["trace"]=d
            elif kind=="REGION":
                reg=d["region"]
                if reg in rec["regions"]:raise BadSpatial("duplicate spatial GPU region")
                rec["regions"][reg]=d
            elif kind=="GAP":
                gap=d["slot"]
                if gap in rec["gaps"]:raise BadSpatial("duplicate untouched gap probe")
                rec["gaps"][gap]=d
            elif kind=="SUMMARY":
                if "summary" in rec:raise BadSpatial("duplicate original OT summary")
                rec["summary"]=d
            else:
                raise BadSpatial("unrecognized observed OT event")
        except (BadSpatial,KeyError,IndexError,ValueError) as exc:
            errors.append(str(exc))

    scenes={}
    expected=ordered_expected(0)
    for scene,rec in data.items():
        walk=rec["walk"]
        if len(walk)!=TOTAL:
            errors.append(f"scene{scene}: observed {len(walk)} instead of 256 packet visits")
        types={}
        category_count=Counter()
        for seq,(ref,record) in enumerate(zip(expected,walk)):
            burst,slot,bucket,filler=ref
            if (record["frame"],record["seq"],record["burst"],record["slot"],
                record["bucket"],record["filler"]) !=(scene,seq,burst,slot,bucket,filler):
                errors.append(f"scene{scene}: wrong actual depth/OT visit #{seq}")
                break
            label=category(scene,slot,filler)
            category_count[label]+=1
            if label in types and types[label]!=record["type"]:
                errors.append(f"scene{scene}: inconsistent original primitive type for {label}")
            types[label]=record["type"]
        if set(types)!=set(CATEGORIES) or len(set(types.values()))!=5:
            errors.append(f"scene{scene}: non-unique original sprite/terrain/DR_MODE/F4/TILE type")
        if category_count["SPRT"]!=24 or category_count["FT4"]!=48:
            errors.append(f"scene{scene}: wrong number of sprite and textured-quad packets")
        trace=rec.get("trace")
        if trace is None or (trace["frame"],trace["count"],trace["registered"])!=(scene,TOTAL,TOTAL):
            errors.append(f"scene{scene}: wrong real original DrawOTag frame delimiter")
        if set(rec["regions"])!=set(range(REGIONS)):
            errors.append(f"scene{scene}: missing/extra exact spatially separated rendered region")
        else:
            for region,observed in sorted(rec["regions"].items()):
                xx,yy=coords(region)
                x,y=xx+8,yy+12
                if any(observed[k]!=v for k,v in (("scene",scene),
                   ("workers",worker),("region",region),("firstburst",region*6),
                   ("x",x),("y",y),("hx",2*x+1),("hy",2*y))):
                    errors.append(f"scene{scene}/region{region}: bad actual source/destination region")
                n=expected_color(scene,region,x,y)
                h=expected_color(scene,region,2*x+1,2*y)
                if (observed["native"],observed["hires"],observed["direct"])!=(n,h,h):
                    errors.append(f"scene{scene}/region{region}: incorrect independent BGR555 source/HD color")
                if observed["othash"]!=observed["directhash"]:
                    errors.append(f"scene{scene}/region{region}: full 32x48 original HD region mismatch")
        if set(rec["gaps"])!=set(range(len(GAPS))):
            errors.append(f"scene{scene}: missing/extra untouched pixel gap samples")
        else:
            for slot,d in rec["gaps"].items():
                x,y=GAPS[slot]
                if any(d[k]!=v for k,v in (("scene",scene),("workers",worker),
                       ("slot",slot),("x",x),("y",y),("hx",2*x+1),("hy",2*y),
                       ("native",0),("hires",0),("direct",0))):
                    errors.append(f"scene{scene}: original GPU leaked into gap probe {slot}")
        summary=rec.get("summary")
        if summary is None:
            errors.append(f"scene{scene}: missing full-spatial-HD original GPU summary")
            continue
        if any(summary[k]!=v for k,v in (
            ("scene",scene),("workers",worker),("bursts",24),("buckets",4),
            ("packets",256),("regions",REGIONS),("pixels",57600),
            ("width",80),("height",180),
            ("clut4",31978),("clut8",31914),("sprite_tpage",166),
            ("sprite_mask",1),("sprite_offset",1))):
            errors.append(f"scene{scene}: wrong global framebuffer/CLUT/GP0 state")
        first=rec["regions"].get(0)
        if first and any(summary[key]!=first[k] for key,k in (
               ("native","native"),("hires","hires"),("direct","direct"))):
            errors.append(f"scene{scene}: global summary not same first spatial region sample")
        if summary["othash"]!=summary["directhash"]:
            errors.append(f"scene{scene}: complete 160x360 HD spatial bounding rectangle mismatched")
        scenes[str(scene)]={
            "full_hd_hash":summary["othash"],
            "regions":{str(j):{"native":p["native"],"hires":p["hires"],
                              "hash":p["othash"]} for j,p in rec["regions"].items()},
            "gap_count":len(rec["gaps"]),
            "sprites_distinct_from_terrain_FT4":category_count["SPRT"]==24 and category_count["FT4"]==48,
            "packets_observed":len(walk),
        }
    for reg in range(REGIONS):
        p0=scenes.get("0",{}).get("regions",{}).get(str(reg))
        p1=scenes.get("1",{}).get("regions",{}).get(str(reg))
        if p0 and p1 and p0["native"]==p1["native"]:
            errors.append(f"region {reg}: changed FT4 source OT ordering did not affect final pixel")
    return {
        "schema":"vh-map02-v55-spatial-original-ot",
        "status":"spatial_original_ot_verified" if not errors else "refused",
        "workers":worker,"scene_count":len(scenes),"regions_per_scene":4,
        "significant_packets_per_scene":192,"real_OT_packets_per_scene":256,
        "sprites_per_scene":24,"textured_quads_per_scene":48,
        "full_hires_bounding_pixels_per_scene":57600,
        "original_frame_data_synthetic":True,"retail_map_authenticity_proven":False,
        "genuine_gameplay_proven":False,"HD_replacement_approved":False,
        "scenes":scenes,"errors":errors[:35],
    }

def audit(logs):
    errors=[]
    if set(logs)!=set(WORKERS):errors.append("missing 1,2,4 worker logs")
    reports={worker:audit_worker(lines,worker) for worker,lines in logs.items()}
    for worker,r in reports.items():
        if r["status"]!="spatial_original_ot_verified":
            errors.append(f"worker {worker} failed: "+str(r["errors"][:4]))
    if not errors:
        for scene in ("0","1"):
            compare=reports[1]["scenes"][scene]
            for worker in (2,4):
                if reports[worker]["scenes"][scene]!=compare:
                    errors.append(f"worker {worker} differs at original 2x spatial output of scene {scene}")
    return {
        "schema":"vh-map02-v55-spatial-cross-thread",
        "status":"verified" if not errors else "refused",
        "workers_checked":[1,2,4],"real_OT_walk_events":256*2*3,
        "complete_original_GPU_pixels_compared_per_compiler":57600*2*3,
        "source_only_synthetic":True,
        "HD_replacement_approved":False,"retail_map_authenticity_proven":False,
        "reports":reports,"errors":errors,
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("logs",nargs=3,type=Path)
    p.add_argument("--output",type=Path)
    opts=p.parse_args()
    try:
        lines={}
        for w,path in zip(WORKERS,opts.logs):
            if path.stat().st_size>3*1024*1024:raise BadSpatial("GPU output too large")
            lines[w]=path.read_text(encoding="utf-8").splitlines()
        result=audit(lines)
        data=json.dumps(result,indent=2,sort_keys=True)+"\n"
        if opts.output:
            with opts.output.open("x",encoding="utf-8") as f:f.write(data)
        else:
            print(data,end="")
        return 0 if result["status"]=="verified" else 1
    except (ValueError,OSError,UnicodeError) as exc:
        print("[v55-original-gpu] REFUSED: "+str(exc),file=__import__("sys").stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
