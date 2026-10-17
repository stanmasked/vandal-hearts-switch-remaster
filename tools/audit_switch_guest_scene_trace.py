#!/usr/bin/env python3
"""Audit bounded guest-side scene trace; do not infer audible output.

Accept only the exact BEGIN/CSV/END envelope written after the native
audio worker joins. Guest logging may be unsupported in an emulator;
missing output is NOT_OBSERVED, never a pass or a fabricated zero latency.
"""
from __future__ import annotations
import argparse
import csv
import io
import json
from pathlib import Path

KINDS = ("INPUT", "POST", "ACCEPT", "SUBMIT_CALL",
         "RELEASE_RETURN", "SUBMIT_ERROR")
HEADER = "index,event,serial,scene,monotonic_ns"
BEGIN = "VH_AUDIO_SCENE_TRACE_BEGIN"
END = "VH_AUDIO_SCENE_TRACE_END,"

class TraceError(ValueError):
    pass

def analyze(log: str) -> dict:
    lines = log.splitlines()
    starts = [i for i, line in enumerate(lines) if line.endswith(BEGIN)]
    result = {"schema": "vh-guest-audio-scene-trace/v1",
              "source": "guest stderr after audio thread joined",
              "hardware_status": "HARDWARE NOT TESTED",
              "audible_music_confirmed": False,
              "hardware_input_to_audio_latency_ms": None,
              "dac_output_timestamp_confirmed": False}
    if not starts:
        result["result"] = "GUEST_TRACE_NOT_OBSERVED"
        result["reason"] = "guest stdout/stderr transport unavailable, or guest never exited"
        return result
    if len(starts) != 1:
        raise TraceError("duplicate trace headers")
    start = starts[0]
    ends = [i for i in range(start+1,len(lines))
            if END in lines[i]]
    if len(ends) != 1:
        raise TraceError("missing or duplicate trace end")
    end = ends[0]
    footer = lines[end][lines[end].index(END)+len(END):]
    parts = footer.split(",")
    if len(parts)!=2 or not parts[0].startswith("rows=") or not parts[1].startswith("dropped="):
        raise TraceError("invalid footer")
    try:
        expected_rows = int(parts[0][5:])
        dropped = int(parts[1][8:])
    except ValueError as exc:
        raise TraceError("non-integer footer counters") from exc
    if not 0 <= expected_rows <= 64 or dropped < 0:
        raise TraceError("out-of-range counters")
    payload = lines[start+1:end]
    if not payload or payload[0] != HEADER:
        raise TraceError("exact CSV header missing")
    if len(payload)-1 != expected_rows:
        raise TraceError("CSV/footer row count mismatch")
    items = list(csv.DictReader(io.StringIO("\n".join(payload)+"\n")))
    if len(items) != expected_rows:
        raise TraceError("invalid CSV rows")
    normalized = []
    for i, row in enumerate(items):
        if set(row) != {"index", "event", "serial", "scene", "monotonic_ns"}:
            raise TraceError("unknown CSV columns")
        if row["event"] not in KINDS:
            raise TraceError("unknown event")
        try:
            idx, serial, scene, ns = [int(row[field]) for field
                                      in ("index","serial","scene","monotonic_ns")]
        except (TypeError,ValueError) as exc:
            raise TraceError("non-integer row") from exc
        if idx != i or not 0 <= serial <= 0xffffffff or scene not in (0,1,2) or ns < 0:
            raise TraceError("invalid row identifiers")
        normalized.append((row["event"],serial,scene,ns))
    serials = {}
    for event,serial,scene,ns in normalized:
        if serial==0:
            continue # startup / ambiguous mailbox receipt cannot be matched
        group = serials.setdefault(serial,{"scene":scene})
        if group["scene"] != scene:
            raise TraceError("same serial refers to two scenes")
        if event in group:
            raise TraceError("repeated event kind in one serial")
        group[event] = ns

    full = []
    partial = []
    for serial,group in sorted(serials.items()):
        if "POST" in group and "INPUT" not in group:
            raise TraceError("post without an observed input")
        if "INPUT" in group and "POST" in group and group["INPUT"] > group["POST"]:
            raise TraceError("post before input timestamp")
        if "ACCEPT" in group and "POST" in group and group["POST"] > group["ACCEPT"]:
            raise TraceError("accept before post timestamp")
        if ("ACCEPT" in group and "SUBMIT_CALL" in group
            and group["ACCEPT"] > group["SUBMIT_CALL"]):
            raise TraceError("submit call precedes cue acceptance")
        if ("SUBMIT_CALL" in group and "RELEASE_RETURN" in group
            and group["SUBMIT_CALL"] > group["RELEASE_RETURN"]):
            raise TraceError("buffer return before submit call")
        complete = all(kind in group for kind in
                       ("INPUT", "POST", "ACCEPT", "SUBMIT_CALL", "RELEASE_RETURN"))
        if complete and not "SUBMIT_ERROR" in group:
            full.append({
                "serial":serial,"scene":group["scene"],
                "observed_input_to_cue_accepted_ms":
                    round((group["ACCEPT"]-group["INPUT"])/1e6,3),
                "observed_input_to_page_return_ms":
                    round((group["RELEASE_RETURN"]-group["INPUT"])/1e6,3),
                "observed_submit_call_to_return_ms":
                    round((group["RELEASE_RETURN"]-group["SUBMIT_CALL"])/1e6,3),
            })
        else:
            partial.append(serial)
    result.update({
        "result": ("GUEST_INTERNAL_PHASES_OBSERVED" if full and not dropped
                   else "GUEST_TRACE_PARTIAL"),
        "rows": expected_rows,"dropped":dropped,
        "complete_scene_serials":full,"partial_scene_serials":partial,
        "unmatched_serial_zero_events":sum(serial==0 for _,serial,_,_ in normalized),
        "note":"Internal buffer-return confirmation is not DAC delivery; mixed producer CSV row ordering is reservation order, not a total guest-timestamp ordering.",
    })
    return result

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("guest_log",type=Path)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    try:
        report=analyze(args.guest_log.read_text(errors="replace"))
        text=json.dumps(report,indent=2)+"\n"
        if args.output:
            if args.output.exists() or args.output.is_symlink():
                raise TraceError("refuse overwrite")
            args.output.write_text(text)
        else:
            print(text,end="")
    except (TraceError,OSError) as exc:
        print(json.dumps({"result":"INVALID_GUEST_TRACE","error":str(exc)}))
        return 2
    return 0

if __name__=="__main__":
    raise SystemExit(main())
