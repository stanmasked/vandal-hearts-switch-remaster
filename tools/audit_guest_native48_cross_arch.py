#!/usr/bin/env python3
"""Exact 48-kHz host GCC/Clang versus two NeXium synthetic guest receipts."""
import argparse
import json
import re
from pathlib import Path

LINE=re.compile(
    r"^native48 pre=([0-9a-f]{16}) wet=([0-9a-f]{16}) reset=([0-9a-f]{16}) "
    r"prefix_frames=(\d+) tail_frames=(\d+) different_pages=(\d+) "
    r"wet_nonzero=(\d+) reset_first=(\d+) reset_later=(\d+)$"
)
KEYS=("pre_switch_native_fnv1a64","wet_native_fnv1a64",
      "reset_native_fnv1a64","pre_switch_native_frames",
      "post_switch_native_frames","different_post_switch_native_pages",
      "retained_tail_nonzero_sample_values",
      "reset_first_page_nonzero_sample_values",
      "reset_later_pages_nonzero_sample_values")

def host_receipt(path):
    matches=[m for line in Path(path).read_text().splitlines()
             if (m:=LINE.fullmatch(line.strip()))]
    if len(matches)!=1:
        raise ValueError("Host must contain exactly one 48-kHz fingerprint receipt")
    strings=matches[0].groups()
    d={key:strings[i] if i<3 else int(strings[i]) for i,key in enumerate(KEYS)}
    return d

def audit(gcc,clang,guest0,guest1,run_id,attempt,sha):
    if not (isinstance(sha,str) and len(sha)==40 and
            all(ch in "0123456789abcdef" for ch in sha) and
            isinstance(run_id,int) and run_id>0 and
            isinstance(attempt,int) and attempt>0):
        raise ValueError("Invalid GitHub run/attempt/exact SHA provenance")
    baseline=host_receipt(gcc)
    if baseline!=host_receipt(clang):
        raise ValueError("GCC and Clang 48-kHz PCM fingerprints differ")
    pre=baseline["pre_switch_native_frames"]
    tail=baseline["post_switch_native_frames"]
    if not (64*555<=pre<=64*559 and 48*555<=tail<=48*559 and
            baseline["different_post_switch_native_pages"]==48 and
            0<baseline["retained_tail_nonzero_sample_values"]<=2*tail and
            0<=baseline["reset_first_page_nonzero_sample_values"]<=2 and
            baseline["reset_later_pages_nonzero_sample_values"]==0 and
            baseline["wet_native_fnv1a64"]!=baseline["reset_native_fnv1a64"]):
        raise ValueError("Host output-stage proof violates native 48k bounds")
    for i,file in enumerate((guest0,guest1)):
        receipt=json.loads(Path(file).read_text())
        if (receipt.get("result")!="GUEST_NATIVE_48K_SYNCHRONIZED_TAIL_OBSERVED" or
            receipt.get("outer_nro_wet_tail_mode")!=i or
            receipt.get("identical_complete_replays")!=2 or
            receipt.get("rate_hz")!=48000 or
            receipt.get("guest_synthetic_postprocess_causality") is not True or
            receipt.get("live_audout_music_sample_aligned") is not False or
            receipt.get("physical_switch_speakers_verified") is not False):
            raise ValueError(f"Guest mode {i} 48k audit status or claim boundary invalid")
        observed={key:receipt.get(key) for key in KEYS}
        if observed!=baseline:
            raise ValueError(f"Guest mode {i} 48k values differ from GCC/Clang")
    return {"schema":"vh-map02-guest-native48-cross-arch/v1",
            "result":"GCC_CLANG_BOTH_NEXIUM_NATIVE_48K_EQUAL",
            "run_id":run_id,"attempt":attempt,"git_sha":sha,
            "host_compilers":["gcc","clang"],
            "guest_outer_modes":[0,1],
            "synthetic_output_stage_exact_match":True,
            "metrics":baseline,
            "one_boundary_stereo_frame_max":True,
            "later_reset_output_silent":True,
            "live_audout_sample_aligned":False,
            "physical_switch_audio_tested":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for a in ("gcc","clang","guest0","guest1"):
        p.add_argument("--"+a,required=True,type=Path)
    p.add_argument("--run-id",required=True,type=int)
    p.add_argument("--attempt",required=True,type=int)
    p.add_argument("--sha",required=True)
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args()
    try:
        result=audit(args.gcc,args.clang,args.guest0,args.guest1,
                     args.run_id,args.attempt,args.sha)
    except (OSError,TypeError,ValueError,KeyError,json.JSONDecodeError) as exc:
        result={"schema":"vh-map02-guest-native48-cross-arch/v1",
                "result":"NATIVE_48K_CROSS_ARCH_UNVERIFIED",
                "reason":str(exc),
                "live_audout_sample_aligned":False,
                "physical_switch_audio_tested":False}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result["result"]=="GCC_CLANG_BOTH_NEXIUM_NATIVE_48K_EQUAL" else 1
if __name__=="__main__":
    raise SystemExit(main())
