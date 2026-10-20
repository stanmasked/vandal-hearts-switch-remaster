#!/usr/bin/env python3
"""Stage374: provenance-bound eight-session cross-run replay using Stage373 decoder.

Only original completed NeXium SD/optical evidence; not physical Switch audio.
The first six remain immutable Stage373 pins, with a separately pinned fourth
run independently fetched from GitHub and re-decoded by the same strict parser.
"""
from __future__ import annotations
import argparse
import json
import zlib
from pathlib import Path
import audit_stage373_six_optical_originals as previous

FOURTH_RUN = 39451930021
FOURTH_PIN = {
    "head": "86570c1bd6f05addd80bd975f59e62a81f15fd62",
    "merge": "3f213b94d25dc0d2b0687c27655fb823418732ed",
    "artifact": 12279117713,
    "digest": "sha256:4cc6b9591a57af4ab021d35d91f876eb0fd7044795620966f3494e5df1f2af97",
    "optical": ["248d5be1146e02e82d65447563fc840d8a83a1f60842d75578f5d67243e12912",
                "f9198a80382fc97ec600fbf3ba6c7da484d69283c0d08b4ac320d9038f52fa56"],
    "reason": ["4558ce4a58f5826e6687bb00239ac2f15a5cae210e5dad7c50fe53996c78a241",
               "435fe59b8e7be0d7c5c9018dce1086ce64b19da4b9f4eed0d726f4ee06275210"],
}
RESULT = "STAGE374_EIGHT_ORIGINAL_GUEST_OPTICAL_EXITS_REPLAYED"
SIX_RUNS = (39396243731, 39398650528, 39406193313)


def combine(six: dict, fourth: list[dict]) -> dict:
    need = previous.need
    need(six.get("result") == previous.RESULT and
         six.get("source_workflow_run_ids") == list(SIX_RUNS) and
         six.get("nro_sha256") == previous.NRO_SHA and
         six.get("all_six_optical_packets_unique") is True and
         six.get("all_six_original_guest_waits_succeeded") is True and
         six.get("physical_nintendo_switch_audio_tested") is False,
         "old six-session receipt does not meet Stage373 constraints")
    originals = six.get("sessions")
    need(type(originals) is list and len(originals) == 6,
         "missing original six source sessions")
    need(type(fourth) is list and len(fourth) == 2 and
         [(s.get("run_id"), s.get("trial"), s.get("dwell_seconds")) for s in fourth] ==
         [(FOURTH_RUN, "a", 6), (FOURTH_RUN, "b", 12)],
         "fourth original guest trial identity mismatch")
    sessions = originals + fourth
    need(len(sessions) == 8 and
         [(s.get("run_id"),s.get("trial")) for s in sessions] ==
         [(run,tag) for run in (*SIX_RUNS,FOURTH_RUN) for tag in ("a","b")],
         "missing or duplicated guest session")
    for s in sessions:
        need(s.get("guest_result") == 0 and s.get("released_descriptors") == 1 and
             s.get("complete_scene_serials") == 4 and s.get("guest_event_rows") == 23 and
             s.get("dropped_guest_events") == 0 and
             type(s.get("tail_interval_ms")) in (float,int) and
             0 < s["tail_interval_ms"] < 12 and
             type(s.get("pcm_pages_acquired_and_released")) is int and
             s["pcm_pages_acquired_and_released"] > 0,
             "failed/ambiguous guest wait, scene chronology or software lease")
        for key in ("pixel_packet_sha256","original_reason_sha256","original_optical_sha256"):
            need(type(s.get(key)) is str and len(s[key]) == 64 and
                 all(c in "0123456789abcdef" for c in s[key]),
                 "malformed guest source digest")
    for key in ("pixel_packet_sha256","original_reason_sha256","original_optical_sha256"):
        need(len({s[key] for s in sessions}) == 8,
             "stale or duplicated source family: "+key)
    return {
        "schema":"vh-stage374-eight-original-guest-optical-replays/v1",
        "result":RESULT,
        "source_workflow_run_ids":list(SIX_RUNS) + [FOURTH_RUN],
        "original_guest_session_count":8,
        "nro_sha256":previous.NRO_SHA,
        "all_eight_wait_results_zero":True,
        "all_eight_returned_descriptors_one":True,
        "all_eight_guest_optical_packets_unique":True,
        "min_guest_tail_interval_ms":min(s["tail_interval_ms"] for s in sessions),
        "max_guest_tail_interval_ms":max(s["tail_interval_ms"] for s in sessions),
        "sessions":sessions,
        "new_guest_sessions_created_by_replay":False,
        "causal_effect_of_dwell_proven":False,
        "historical_0xEA01_root_cause_proven":False,
        "direct_exit_queue_depth_measured":False,
        "physical_switch_speaker_audio_tested":False,
    }


def audit(originals: Path, metadata: Path) -> dict:
    previous.need(tuple(previous.RUNS) == SIX_RUNS and FOURTH_RUN not in previous.RUNS,
                  "Stage373 source pins unexpectedly changed")
    six = previous.audit(originals, metadata)
    previous.RUNS[FOURTH_RUN] = FOURTH_PIN
    try:
        fourth = previous.verify(FOURTH_RUN, originals / str(FOURTH_RUN), metadata)
    finally:
        del previous.RUNS[FOURTH_RUN]
    return combine(six, fourth)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("originals", "metadata", "output"):
        p.add_argument("--"+key, type=Path, required=True)
    args = p.parse_args(argv)
    try:
        previous.need(not args.output.exists() and not args.output.is_symlink(),
                      "refuse overwrite of Stage374 report")
        report = audit(args.originals,args.metadata)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open("x",encoding="utf-8") as f:
            json.dump(report,f,sort_keys=True,indent=2); f.write("\n")
        print(json.dumps({"result":RESULT,"original_guest_sessions":8,
                          "guest_wait_results":[0]*8,
                          "physical_audio_verified":False},sort_keys=True))
        return 0
    except (ValueError,KeyError,TypeError,IndexError,OSError,UnicodeError,zlib.error) as e:
        print(json.dumps({"result":"STAGE374_EIGHT_ORIGINAL_SOURCES_NOT_VERIFIED",
                          "error_kind":type(e).__name__,"physical_audio_verified":False},sort_keys=True))
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
