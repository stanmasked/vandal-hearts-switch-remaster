#!/usr/bin/env python3
"""Stage289: original-SD-bound pre-submit audout SERVICE probe audit.

The 1/16 sampled queue service count is measured before audoutPlayBuffer,
not an OS scheduler trace, not device-buffer occupancy DURING blocking,
not a DAC sample clock, and not proof of audible underruns.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from audit_nexium_audout_queue import (
    stable_guest_bytes,bind_export_receipt,parse_telemetry
)
from audit_nexium_audout_scene_correlation import (
    CorrelationError,parse_clock,parse_scene_inputs
)
from audit_nexium_audout_latency import parse_latency
from audit_nexium_audout_slow_calls import parse_slow

HEADER=["scope","index","attempt","submit_begin_ns",
        "status","queue_count","total_probes","dropped_probes"]
CAP=256


def _number(value:str,*,signed:bool=False)->int:
    if signed and value=="-1":
        return -1
    if (not value or not value.isascii() or not value.isdecimal()
            or (len(value)>1 and value[0]=="0")):
        raise CorrelationError("noncanonical original guest service probe field")
    return int(value)


def parse_probes(raw:bytes,origin:dict,queue:dict,
                 latency:dict,slow:list[dict])->dict:
    if (len(raw)>64000 or b"\\r" in raw or not raw.endswith(b"\\n")):
        raise CorrelationError("oversized or noncanonical probe journal")
    try:
        rows=list(csv.reader(io.StringIO(raw.decode("ascii"),newline=""),
                             strict=True))
    except (UnicodeError,csv.Error) as exc:
        raise CorrelationError("bad guest queue service probe CSV") from exc
    if len(rows)<3 or rows[0]!=HEADER or any(
            len(row)!=len(HEADER) for row in rows[1:]):
        raise CorrelationError("missing or invalid probed service samples")
    if rows[1][:6]!=["TOTAL","-1","0","0","-1","0"]:
        raise CorrelationError("probe journal total row is invalid")
    total=_number(rows[1][6])
    dropped=_number(rows[1][7])
    if dropped or total>CAP or total!=len(rows)-2:
        raise CorrelationError("probe journal overflow/truncation or omission")
    attempts=origin["attempts"]
    if (queue["attempts"]!=attempts or latency["attempts"]!=attempts
            or (attempts+15)//16!=total
            or queue["queue_probes_ok"]+queue["queue_probes_failed"]!=total):
        raise CorrelationError("independent queue-clock probe totals differ")
    second_bounds=[]
    end=0
    for bucket in latency["per_second_call_bands"]:
        start=end
        end+=bucket["attempts"]
        second_bounds.append((start,end))
    if end!=attempts:
        raise CorrelationError("second attempt accounting incomplete")
    if len(slow)!=latency["from40to50ms_calls"]+latency["ge50ms_calls"]:
        raise CorrelationError("missing detailed slow-call source")
    exact_calls={c["attempt"]:c for c in slow}
    samples=[]
    status_ok=0
    status_failed=0
    min_count=None
    max_count=None
    matched_slow=[]
    last_ns=0
    for index,cols in enumerate(rows[2:]):
        if (cols[0]!="SAMPLE" or
                _number(cols[1])!=index or
                cols[6:]!=["0","0"]):
            raise CorrelationError("out-of-order or overwritten queue service sample")
        attempt=_number(cols[2])
        stamp=_number(cols[3])
        status=_number(cols[4])
        value=_number(cols[5])
        if (attempt!=1+16*index or stamp<origin["origin_ns"]
                or stamp<=last_ns or status not in (0,1)
                or (status==0 and value!=0)):
            raise CorrelationError("probe call order, timestamp or query status invalid")
        last_ns=stamp
        second=(stamp-origin["origin_ns"])//1_000_000_000
        if (second>=len(second_bounds) or
                not(second_bounds[second][0]<attempt<=second_bounds[second][1])):
            raise CorrelationError("service sample not within its guest audout second")
        sample={
            "index":index,"attempt":attempt,
            "submit_begin_ns":stamp,"audio_second":second,
            "query_succeeded":bool(status),
            "pre_submit_queue_count":value if status else None,
        }
        if status==1:
            status_ok+=1
            min_count=value if min_count is None else min(min_count,value)
            max_count=value if max_count is None else max(max_count,value)
        else:
            status_failed+=1
        slow_call=exact_calls.get(attempt)
        if slow_call is not None:
            if slow_call["begin_ns"]!=stamp:
                raise CorrelationError("probe submit clock differs from same audout slow call")
            matched_slow.append({
                **sample,
                "duration_ns":slow_call["duration_ns"],
            })
        samples.append(sample)
    if (status_ok!=queue["queue_probes_ok"]
            or status_failed!=queue["queue_probes_failed"]
            or min_count!=queue["queue_min_pre_submit"]
            or max_count!=queue["queue_max_pre_submit"]):
        raise CorrelationError("service probes do not reconcile original queue CSV")
    return {
        "schema":"vh-audout-service-probe-guest-clock/v1",
        "result":"GUEST_PRE_SUBMIT_SERVICE_PROBES_RECONCILED",
        "audout_attempts":attempts,
        "queue_probe_samples":len(samples),
        "queue_probe_successes":status_ok,
        "queue_probe_failures":status_failed,
        "queue_probe_dropped":0,
        "sample_records":samples,
        "probed_slow_calls":matched_slow,
        "pre_submit_queue_service_snapshot_only":True,
        "query_timestamp_is_exactly_recorded":False,
        "audout_submission_begin_timestamp_is_exactly_recorded":True,
        "scheduler_or_DAC_state_measured":False,
        "audible_underruns_measured":False,
        "physical_switch_tested":False,
    }


def audit(*,source:Path,locations:Path,receipt:Path,
          sd_root:Path,queue_csv:Path,clock_csv:Path,
          latency_csv:Path,slow_csv:Path,scene_csv:Path)->dict:
    if sd_root.is_symlink():
        raise CorrelationError("symlinked original NeXium guest SD root")
    directory=sd_root/"sdmc"/"switch"/"vandal-hearts-remake"
    if directory.is_symlink() or not directory.is_dir():
        raise CorrelationError("missing original guest SD directory")
    originals=sorted(directory.glob("audio-audout-probe-*.csv"))
    if (len(originals)!=1 or originals[0].is_symlink()
            or source.is_symlink() or locations.is_symlink()):
        raise CorrelationError("expected one non-symlink guest service probe journal")
    if locations.read_text(encoding="utf-8").splitlines()!=[str(originals[0])]:
        raise CorrelationError("guest original service probe location is unbound")
    if source.resolve()==originals[0].resolve():
        raise CorrelationError("copied probe CSV aliases original SD file")
    raw=stable_guest_bytes(originals[0])
    copied=stable_guest_bytes(source)
    if raw!=copied or stable_guest_bytes(originals[0])!=copied:
        raise CorrelationError("original and copied guest service probes differ")
    receipt_evidence=bind_export_receipt(receipt,len(raw))
    origin=parse_clock(stable_guest_bytes(clock_csv))
    queue=parse_telemetry(stable_guest_bytes(queue_csv))
    latency=parse_latency(stable_guest_bytes(latency_csv))
    slow=parse_slow(stable_guest_bytes(slow_csv),
                    origin["origin_ns"],latency)
    inputs=parse_scene_inputs(stable_guest_bytes(scene_csv))
    result=parse_probes(copied,origin,queue,latency,slow)
    result.update({
        "guest_original_probe_sha256":hashlib.sha256(raw).hexdigest(),
        "copied_probe_sha256":hashlib.sha256(copied).hexdigest(),
        "guest_writer_receipt_sha256":
            receipt_evidence["guest_export_receipt_sha256"],
        "original_guest_sd_opened_in_current_workflow":True,
        "scene_input_count":len(inputs),
        "probe_samples_begin_within_500ms_of_input":sum(
            abs(sample["submit_begin_ns"]-event["timestamp_ns"])<=500_000_000
            for sample in result["sample_records"] for event in inputs),
        "scene_to_probe_causality_proven":False,
    })
    return result


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("source","locations","receipt","sd-root","queue-csv",
                 "clock-csv","latency-csv","slow-csv","scene-csv","output"):
        p.add_argument("--"+name,type=Path,required=True)
    args=p.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise CorrelationError("refuse replacement of previous probe audit")
        report=audit(source=args.source,locations=args.locations,
                     receipt=args.receipt,sd_root=args.sd_root,
                     queue_csv=args.queue_csv,clock_csv=args.clock_csv,
                     latency_csv=args.latency_csv,slow_csv=args.slow_csv,
                     scene_csv=args.scene_csv)
        args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\\n",
                               encoding="utf-8")
        print(json.dumps({
            "result":report["result"],"queue_probe_samples":report["queue_probe_samples"],
            "probed_slow_calls":len(report["probed_slow_calls"]),
            "near_guest_input":report["probe_samples_begin_within_500ms_of_input"],
            "scheduler_state_measured":False,
        },sort_keys=True))
        return 0
    except (ValueError,OSError,UnicodeError,TypeError) as exc:
        print(json.dumps({"result":"GUEST_SERVICE_PROBE_NOT_VERIFIED",
                          "error":str(exc)}),file=__import__("sys").stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
