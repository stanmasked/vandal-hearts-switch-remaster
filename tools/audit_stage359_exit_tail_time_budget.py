#!/usr/bin/env python3
"""Stage359: deterministic NON-CAUSAL exit-tail time-budget sensitivity.

No game service calls, no NeXium playback, no emulator timing measured by
this model. Compare a 96-frame 48kHz fade with the unchanged 12ms software
event-return bound under multiple hypothetical queue and scheduler budgets.
Never use the model to claim a new safe timeout or audible improvement.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

FRAME_RATE=48000
FADE_FRAMES=96
WAIT_NS=12_000_000
GUEST_FAILURE_RUN=39325440778
GUEST_RAW_RESULT=0xEA01
CASES=(
    ("empty_queue_no_delay",0,0),
    ("one_fade_only",2_000_000,0),
    ("moderate_queue_and_jitter",8_000_000,2_000_000),
    ("boundary_equal_wait",10_000_000,2_000_000),
    ("long_queue",13_000_000,0),
    ("scheduler_lag_only",0,15_000_000),
    ("mixed_lag_above_bound",9_000_000,5_000_000),
)
def analyze()->dict:
    if FADE_FRAMES*1_000_000_000 % FRAME_RATE:
        raise ValueError("fade duration is not integral nanoseconds")
    fade_ns=FADE_FRAMES*1_000_000_000//FRAME_RATE
    assert fade_ns==2_000_000
    assert WAIT_NS==12_000_000
    data=[]
    for name,queued_ns,lag_ns in CASES:
        total=queued_ns+lag_ns
        data.append({
            "case":name,
            "assumed_queue_delay_ns":queued_ns,
            "assumed_scheduler_delay_ns":lag_ns,
            "assumed_total_return_delay_ns":total,
            "strictly_below_12ms_budget":total<WAIT_NS,
            "exactly_on_12ms_boundary":total==WAIT_NS,
            "beyond_12ms_budget":total>WAIT_NS,
            "measured_or_inferred_from_guest":False,
        })
    if len(data)!=7 or not any(p["beyond_12ms_budget"] for p in data):
        raise ValueError("sensitivity cases incomplete")
    return {
        "schema":"vh-stage359-hypothetical-exit-tail-time-budget-sensitivity/v1",
        "result":"12MS_BOUNDED_WAIT_VS_2MS_FADE_HYPOTHESIS_TABLE_CREATED",
        "original_stop_taper_frames":FADE_FRAMES,
        "original_stop_taper_sample_rate_hz":FRAME_RATE,
        "stop_taper_pcm_duration_ns":fade_ns,
        "unchanged_guest_wait_timeout_ns":WAIT_NS,
        "wait_budget_minus_fade_duration_ns":WAIT_NS-fade_ns,
        "original_real_timeout_run_id":GUEST_FAILURE_RUN,
        "original_real_timeout_raw_result":GUEST_RAW_RESULT,
        "failure_mode_in_original_run":"KernelError_TimedOut",
        "hypotheses":data,
        "real_guest_queue_depth_at_shutdown_known":False,
        "actual_scheduler_latency_inferred":False,
        "change_to_production_timeout_recommended":False,
        "causal_attribution_to_audio_fade_proven":False,
        "audible_dropout_or_DAC_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink():
            raise ValueError("refuse overwrite analytical document")
        report=analyze()
        a.output.parent.mkdir(parents=True,exist_ok=True)
        if any(p.is_symlink() for p in (a.output,*a.output.parents)):
            raise ValueError("linked output")
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(report,f,indent=2,sort_keys=True)
            f.write("\n")
        print(json.dumps({
            "result":report["result"],
            "fade_ns":report["stop_taper_pcm_duration_ns"],
            "wait_ns":report["unchanged_guest_wait_timeout_ns"],
            "cases":len(report["hypotheses"]),
            "physical_Nintendo_Switch_audio_tested":False,
        },sort_keys=True))
        return 0
    except (ValueError,OSError,TypeError) as error:
        print(json.dumps({
            "result":"STAGE359_HYPOTHETICAL_WAIT_SENSITIVITY_NOT_CREATED",
            "error_kind":type(error).__name__,
            "physical_Nintendo_Switch_audio_tested":False,
        },sort_keys=True))
        return 2
if __name__=="__main__":
    raise SystemExit(main())
