#!/usr/bin/env python3
"""Stage382: re-open eight independently pinned original NeXium guest pairs.

Source identity and PNG packet CRCs are checked by Stage373/378's original
stdlib decoder. Byte-identical counter CSVs are allowed across independent
runs; original PNGs AND decoded packets must remain distinct. This is NOT a
new guest execution, real speaker test, or proof of timeout root cause.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import zlib
import audit_stage373_six_optical_originals as original
import audit_stage378_twelve_optical_originals as twelve
import audit_stage374_eight_optical_originals as eight

NEW_RUNS = (39466729315, 39476667373)
PINS = {
    39466729315: {
        "head": "8b3c8a6df47ded9b597166806ffa65083c947134",
        "merge": "1f361b89ccbfa50f85c0ea932f6a81e19fcecfba",
        "artifact": 12286756628,
        "digest": "sha256:e21ea3b31f4ce3b46bd078886b84308f0c228a20e95c2778fe61927558253eec",
        "optical": ["52f88f5ab16019005a51ab1a89c14fc76365412b928a53855585a844b09f3947", "c6e6d0d3ce4d264ed1cf66bd5f084ef9f71f3d079ac2f37d09a966d6bf967ca5"],
        "reason": ["1a4385efef47ae364c240f4a47215441019159fe391f37a460cb995d0dd77777", "c20a26cae5383291812b167ff7c6e085684a3afe5d6a59c8ece3d2548c158429"],
    },
    39476667373: {
        "head": "93230691ba184888ead11c8d18657212a946e63e",
        "merge": "83d0252ec61274acb070bae74e49394992f44f4c",
        "artifact": 12289084323,
        "digest": "sha256:4d271269be02f425614fc1beb2ceeaa225c80dece6b89f16d9424daad8bbc995",
        "optical": [
            "5794b4589d1956e4bf3088a7117933da6263185738910836191966197d7e61ab",
            "2d7b4ebfa322d1b73997dd5ac090f75879fc96f3bcb9c00c70ed7c1997f4344b",
        ],
        "reason": [
            "b94d00e7977ea0f742a01feca9645f1b5d149a06f869c5f69b7ca9f41f2e64fb",
            "7b4348fe0cd905475110158a0549760cf6c7dfa6b3af8881763973983a94bbd3",
        ],
    },
}
PRIOR_RUNS = tuple(getattr(twelve, "RUNS", getattr(twelve, "SOURCE_RUNS", ())))
ALL_RUNS = (*PRIOR_RUNS, *NEW_RUNS)
RESULT = "STAGE382_SIXTEEN_SOURCE_PINNED_NEIXUM_OPTICAL_EXITS_REPLAYED"


def combine(previous: dict, seventh: list[dict], eighth: list[dict]) -> dict:
    need = original.need
    need(type(previous) is dict and previous.get("result") == twelve.RESULT
         and previous.get("source_run_ids") == list(PRIOR_RUNS)
         and previous.get("nro_sha256") == original.NRO_SHA
         and previous.get("guest_sessions") == 12
         and previous.get("all_wait_results_zero") is True
         and previous.get("all_release_counts_one") is True
         and previous.get("all_optical_packet_hashes_distinct") is True
         and previous.get("new_guest_sessions_created_by_audit") is False
         and previous.get("physical_switch_speaker_audio_tested") is False
         and previous.get("cause_of_historical_0xEA01_proven") is False,
         "prior original twelve guest verdict invalid")
    previous_sessions = previous.get("sessions")
    need(type(previous_sessions) is list and len(previous_sessions) == 12,
         "original twelve guest records missing")
    for run, pair in zip(NEW_RUNS, (seventh, eighth)):
        need(type(pair) is list and len(pair) == 2
             and [(s.get("run_id"), s.get("trial"), s.get("dwell_seconds")) for s in pair]
             == [(run, "a", 6), (run, "b", 12)],
             "new original run, trial or dwell substitution")
    rows = previous_sessions + seventh + eighth
    need(len(rows) == 16 and
         [(s.get("run_id"), s.get("trial"), s.get("dwell_seconds")) for s in rows]
         == [(r, tag, d) for r in ALL_RUNS for tag,d in (("a",6),("b",12))],
         "missing, repeated or out-of-order original guest session")
    for s in rows:
        need(s.get("guest_result") == 0 and s.get("released_descriptors") == 1
             and type(s.get("pcm_pages_acquired_and_released")) is int
             and s["pcm_pages_acquired_and_released"] > 0
             and type(s.get("tail_interval_ms")) in (float, int)
             and 0 < s["tail_interval_ms"] < 12
             and s.get("guest_event_rows") == 23
             and s.get("complete_scene_serials") == 4
             and s.get("dropped_guest_events") == 0,
             "wrong wait, release, timing, optical events or PCM accounting")
        for field in ("original_reason_sha256", "original_optical_sha256", "pixel_packet_sha256"):
            digest = s.get(field)
            need(type(digest) is str and len(digest) == 64
                 and all(c in "0123456789abcdef" for c in digest),
                 "malformed source SHA256")
        crc = s.get("pixel_packet_crc32")
        need(type(crc) is str and len(crc) == 8
             and all(c in "0123456789abcdef" for c in crc),
             "malformed original guest pixel CRC32")
    for field in ("original_optical_sha256", "pixel_packet_sha256"):
        need(len({s[field] for s in rows}) == 16,
             "optical frame or decoded packet reused between source runs: " + field)
    # Intentionally NOT demanding 16 distinct reason-CSV hashes. Two
    # authentic runs have equal numeric PCM counters, hence identical CSV
    # bytes. Individual original CSV SHA is verified against each immutable
    # source pin; PNG/optical packet uniqueness establishes distinct scenes.
    reason_groups = {}
    for s in rows:
        reason_groups.setdefault(s["original_reason_sha256"], []).append(
            {"run_id": s["run_id"], "trial": s["trial"]})
    repeated = [dict(reason_sha256=k, source_sessions=v)
                for k,v in sorted(reason_groups.items()) if len(v) > 1]
    return {
        "schema": "vh-stage382-sixteen-original-guest-optical-exits/v1",
        "result": RESULT,
        "source_run_ids": list(ALL_RUNS),
        "nro_sha256": original.NRO_SHA,
        "original_guest_sessions": 16,
        "all_software_wait_results_zero": True,
        "all_returned_descriptors_exactly_one": True,
        "all_sixteen_optical_pngs_and_packets_distinct": True,
        "distinct_reason_csv_sha256_count": len(reason_groups),
        "repeated_reason_csv": repeated,
        "reason_csv_policy": "PER_SOURCE_SHA_PIN_AND_ORIGINAL_GUEST_BINDING__BYTE_IDENTICAL_COUNTERS_ALLOWED",
        "complete_scene_transitions": 64,
        "dropped_guest_events": 0,
        "min_tail_interval_ms": min(s["tail_interval_ms"] for s in rows),
        "max_tail_interval_ms": max(s["tail_interval_ms"] for s in rows),
        "sessions": rows,
        "new_guest_sessions_created_by_audit": False,
        "physical_switch_speaker_audio_tested": False,
        "direct_exit_queue_depth_measured": False,
        "cause_of_historical_0xEA01_proven": False,
        "controlled_dwell_causality_proven": False,
    }


def audit(originals: Path, metadata: Path) -> dict:
    original.need(tuple(original.RUNS) == tuple(eight.SIX_RUNS)
                  and not any(r in original.RUNS for r in NEW_RUNS)
                  and PRIOR_RUNS == ALL_RUNS[:6],
                  "historical Stage373/378 pins changed")
    prior = twelve.audit(originals, metadata)
    new_pairs = []
    for run in NEW_RUNS:
        original.need(run not in original.RUNS, "source pin collision")
        original.RUNS[run] = PINS[run]
        try:
            new_pairs.append(original.verify(run, originals / str(run), metadata))
        finally:
            del original.RUNS[run]
    return combine(prior, *new_pairs)


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("originals", "metadata", "output"):
        p.add_argument("--"+k, type=Path, required=True)
    a=p.parse_args(argv)
    try:
        original.need(not a.output.exists() and not a.output.is_symlink(),
                      "refuse to overwrite original verification report")
        report = audit(a.originals, a.metadata)
        a.output.parent.mkdir(parents=True, exist_ok=True)
        with a.output.open("x", encoding="utf-8") as f:
            json.dump(report,f,indent=2,sort_keys=True)
            f.write("\n")
        print(json.dumps({"result":RESULT,"original_guest_sessions":16,
                          "distinct_reason_csv":report["distinct_reason_csv_sha256_count"],
                          "hardware_status":"HARDWARE NOT TESTED"},sort_keys=True))
        return 0
    except (ValueError,KeyError,TypeError,IndexError,OSError,UnicodeError,zlib.error) as exc:
        print(json.dumps({"result":"STAGE382_ORIGINAL_GUEST_SOURCES_NOT_VERIFIED",
                          "error_kind":type(exc).__name__,
                          "hardware_status":"HARDWARE NOT TESTED"},sort_keys=True))
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
