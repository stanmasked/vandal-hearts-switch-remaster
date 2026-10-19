#!/usr/bin/env python3
"""Fail-closed host/guest fingerprint parity; synthetic STUDIO_C DSP only."""
import argparse
import json
import re
from pathlib import Path

LINE = re.compile(r"^initial=([0-9a-f]{16}) wet=([0-9a-f]{16}) reset=([0-9a-f]{16}) wet_nonzero=([0-9]+)$")

def read_host(path):
    found = [LINE.fullmatch(s.strip()) for s in Path(path).read_text().splitlines()]
    matches = [m for m in found if m]
    if len(matches) != 1:
        raise ValueError("Expected exactly one four-field synthetic PCM host fingerprint")
    m = matches[0]
    values = {"pre_switch_pcm_fnv1a64":m.group(1),
              "retained_tail_pcm_fnv1a64":m.group(2),
              "reset_tail_pcm_fnv1a64":m.group(3),
              "wet_nonzero_sample_values":int(m.group(4))}
    if (values["wet_nonzero_sample_values"] <= 0 or
        values["retained_tail_pcm_fnv1a64"] == values["reset_tail_pcm_fnv1a64"]):
        raise ValueError("Host synthetic DSP tail is not causal/nonzero")
    return values

def compare(host_gcc, host_clang, guest0, guest1, run_id, attempt, git_sha):
    if not (len(git_sha) == 40 and all(x in "0123456789abcdef" for x in git_sha)):
        raise ValueError("Invalid checkout SHA provenance")
    if run_id <= 0 or attempt <= 0:
        raise ValueError("Invalid workflow run provenance")
    host0,host1 = read_host(host_gcc),read_host(host_clang)
    if host0 != host1:
        raise ValueError("GCC/Clang synthesized PCM results differ")
    results=[]
    for mode, path in enumerate((guest0,guest1)):
        guest=json.loads(Path(path).read_text())
        if guest.get("outer_nro_wet_tail_mode") != mode or guest.get("result") != "GUEST_SYNCHRONIZED_SYNTHETIC_STUDIO_C_TAIL_PROVEN":
            raise ValueError("Guest mode/receipt proof invalid")
        if (guest.get("post_switch_blocks") != 48 or guest.get("different_blocks") != 48 or
            guest.get("pre_blocks") != 64 or guest.get("reset_nonzero_sample_values") != 0 or
            guest.get("new_scene_note_ons") != 0 or guest.get("identical_input_replays") != 2 or
            guest.get("guest_live_audout_studio_c_causality_proven") is not False):
            raise ValueError("Guest synthetic DSP causal invariants missing")
        evidence={key:guest.get(key) for key in host0}
        if evidence != host0:
            raise ValueError(f"Guest mode {mode} differs from exact GCC and Clang synthetic PCM")
        results.append(guest)
    return {"schema":"vh-map02-cross-architecture-synthetic-dsp/v1",
            "result":"GCC_CLANG_NEXIUM_SYNTHETIC_PCM_IDENTICAL",
            "git_sha":git_sha, "run_id":run_id, "attempt":attempt,
            "gcc_clang_equal":True,"guest_0_1_equal_to_host":True,
            "evidence":host0, "guest_modes":[0,1],
            "one_clock_per_guest_counterfactual":True,
            "live_audout_sample_aligned":False,
            "original_game_music_verified":False,
            "physical_switch_audio_tested":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gcc",type=Path,required=True)
    p.add_argument("--clang",type=Path,required=True)
    p.add_argument("--guest0",type=Path,required=True)
    p.add_argument("--guest1",type=Path,required=True)
    p.add_argument("--run-id",type=int,required=True)
    p.add_argument("--attempt",type=int,required=True)
    p.add_argument("--sha",required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    try:result=compare(a.gcc,a.clang,a.guest0,a.guest1,a.run_id,a.attempt,a.sha)
    except (OSError,KeyError,TypeError,ValueError,json.JSONDecodeError) as exc:
        result={"schema":"vh-map02-cross-architecture-synthetic-dsp/v1",
                "result":"SYNTHETIC_HOST_GUEST_PARITY_UNVERIFIED",
                "reason":str(exc),
                "live_audout_sample_aligned":False,
                "physical_switch_audio_tested":False}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0 if result["result"]=="GCC_CLANG_NEXIUM_SYNTHETIC_PCM_IDENTICAL" else 1

if __name__=="__main__":raise SystemExit(main())
