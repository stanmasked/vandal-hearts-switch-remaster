#!/usr/bin/env python3
"""v51 original GPU native vs direct hi-res vs genuinely threaded-hires oracle.

Every output is the ACTUAL original C FillQuad DDA framebuffer halfword.
No retail content, no HD artwork replacement, no assumptions that hires
equals native at different (x,y) dither cells or fractional UV coordinates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .verify_map02_gpu_modes_v50 import audit as audit_v50, parse as parse_v50, EXPECTED

class BadHiresProof(ValueError): pass

PREFIXES={"native":"V50 ","hires":"V51HD ","threaded":"V51THREAD "}
INPUT_FIELDS=("name","depth","tpage","clut","u","v","maskx","masky","offx","offy",
              "tx","ty","word","index","palx","paly","palette","raw","before",
              "semi","abr","dither")


def split_cases(lines):
    groups={k:[] for k in PREFIXES}
    for line in lines:
        found=[name for name,prefix in PREFIXES.items() if line.startswith(prefix)]
        if not found:
            if line.startswith(("V50","V51")):
                raise BadHiresProof("malformed GPU mode record")
            continue
        key=found[0]
        groups[key].append("V50 "+line[len(PREFIXES[key]):])
    parsed={}
    summaries={}
    for kind,normalized in groups.items():
        result=audit_v50(normalized)
        if result["status"]!="original_dda_modes_verified":
            raise BadHiresProof(kind+" original GPU oracle refused: "+str(result["errors"][:5]))
        records=[parse_v50(row) for row in normalized]
        if len(records)!=len(EXPECTED) or len({record["name"] for record in records})!=len(EXPECTED):
            raise BadHiresProof(kind+" duplicates or missing modes")
        parsed[kind]={record["name"]:record for record in records}
        summaries[kind]=result
    return parsed,summaries


def audit(lines):
    records,results=split_cases(lines)
    errors=[]
    checks=[]
    diffs=[]
    for name in sorted(EXPECTED):
        native=records["native"][name]
        hd=records["hires"][name]
        worker=records["threaded"][name]
        for kind,record in (("hires",hd),("threaded",worker)):
            for key in INPUT_FIELDS:
                if record[key]!=native[key]:
                    errors.append(f"{name}/{kind}: original GPU input {key} disagrees with native")
            if (record["x"],record["y"])!=(2*native["x"]+1,2*native["y"]):
                errors.append(f"{name}/{kind}: rendered target pixel not in correct 2x block")
        if (hd["x"],hd["y"])!=(worker["x"],worker["y"]):
            errors.append(name+": different direct/threaded HD pixel addresses")
        if hd["after"]!=worker["after"]:
            errors.append(name+": direct and threaded original HD pixel results differ")
        if native["after"]!=hd["after"]:
            diffs.append(name)
        checks.append({"case":name,"native_after":native["after"],
                       "hires_direct_after":hd["after"],
                       "hires_threaded_after":worker["after"],
                       "same_hd_color":hd["after"]==worker["after"],
                       "same_native_hd_color":native["after"]==hd["after"]})
    # At least one actual dither test should prove the HD reference is NOT
    # merely nearest-neighbor copied native VRAM: (88,88) sees matrix -4,
    # (177,176) sees matrix 0, so the BGR555 threshold is crossed.
    if records["native"]["indexed4_dither"]["after"]==records["hires"]["indexed4_dither"]["after"]:
        errors.append("2x dither test did not demonstrate distinct native-vs-HD rendering")
    return {
        "schema":"vh-map02-v51-original-native-hires-worker-dda",
        "status":"original_hires_modes_verified" if not errors else "refused",
        "all_inputs_synthetic":True,
        "real_original_gpu_dda_executed":True,
        "genuine_gameplay_proven":False,
        "full_map_original_visual_fidelity_proven":False,
        "HD_replacement_approved":False,
        "actual_modes_per_pass":len(EXPECTED),
        "total_original_GPU_mode_executions":3*len(EXPECTED),
        "true_hires_scale":2,
        "deferred_renderer_workers_requested":2,
        "direct_hires_vs_deferred_equal_count":sum(c["same_hd_color"] for c in checks),
        "native_vs_hires_different_cases":diffs,
        "native_original_summary":results["native"]["status"],
        "hires_original_summary":results["hires"]["status"],
        "deferred_original_summary":results["threaded"]["status"],
        "cases":checks,
        "errors":errors[:30],
        "note":"Actual original 2x rendering and deferred worker pool on synthetic texture data. No game asset authenticity or HD texture replacement.",
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("log",type=Path)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    try:
        if a.log.stat().st_size>2*1024*1024:
            raise BadHiresProof("GPU test log too large")
        result=audit(a.log.read_text(encoding="utf-8").splitlines())
        data=json.dumps(result,indent=2,sort_keys=True)+"\n"
        if a.output:
            with a.output.open("x",encoding="utf-8") as fp:fp.write(data)
        else:
            sys.stdout.write(data)
        return 0 if result["status"]=="original_hires_modes_verified" else 1
    except (OSError,UnicodeError,ValueError) as exc:
        print("[v51-original-hires] REFUSED: "+str(exc),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
