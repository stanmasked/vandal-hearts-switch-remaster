#!/usr/bin/env python3
"""Describe WHY original Stage304 buffered Plus-control snapshots are nonmonotone.

Read ONLY original host-control CSV (not PCM). Report adjacent byte and
millisecond deltas, never absolute host epochs. This does not bypass
the STRICT Stage304 canonical ordering/source checks or establish which
in-run event caused the old failed capture. This is a postmortem.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from audit_nexium_pcm_exit_controls import HEADER, EVENT_NAMES
from analyze_nexium_pcm_stream_integrity import VirtualPcmEvidenceError

SCHEMA="vh-stage304-archived-host-control-pair-deltas/v1"

def classify_original_host_controls(raw:bytes)->dict:
    if (not isinstance(raw,bytes) or len(raw)>4096 or not raw
            or b"\r" in raw or b"\x00" in raw or not raw.endswith(b"\n")):
        raise VirtualPcmEvidenceError("noncanonical original Stage304 postmortem control CSV")
    try:
        decoded=raw.decode("ascii")
        reader=csv.DictReader(io.StringIO(decoded),strict=True)
        if reader.fieldnames!=HEADER:
            raise VirtualPcmEvidenceError("original Stage304 CSV header changed")
        values=list(reader)
    except (UnicodeError,csv.Error) as exc:
        raise VirtualPcmEvidenceError("cannot read original host controls") from exc
    if len(values)!=3:
        raise VirtualPcmEvidenceError("original Stage304 control evidence is incomplete")
    events=[]
    for name,row in zip(EVENT_NAMES,values):
        if set(row)!=set(HEADER) or row["event"]!=name:
            raise VirtualPcmEvidenceError("noncanonical Stage304 original control event order")
        numbers={}
        for k in ("pcm_bytes","host_epoch_ms"):
            v=row[k]
            if (not isinstance(v,str) or not v.isascii() or
                    not v.isdecimal() or
                    (len(v)>1 and v.startswith("0"))):
                raise VirtualPcmEvidenceError("noncanonical original host-control number")
            n=int(v)
            if n>(1<<64)-1:
                raise VirtualPcmEvidenceError("original host-control value exceeds uint64")
            numbers[k]=n
        if numbers["host_epoch_ms"]==0:
            raise VirtualPcmEvidenceError("invalid zero original host epoch")
        events.append((name,numbers["pcm_bytes"],numbers["host_epoch_ms"]))
    pairs=[]
    for first,second in zip(events,events[1:]):
        byte_delta=second[1]-first[1]
        ms_delta=second[2]-first[2]
        pairs.append({
            "first_event":first[0],
            "second_event":second[0],
            "pcm_file_size_delta_bytes":byte_delta,
            "host_epoch_delta_ms":ms_delta,
            "original_buffer_size_decreased":byte_delta<0,
            "host_epoch_was_not_strictly_increasing":ms_delta<=0,
        })
    size_regressions=sum(p["original_buffer_size_decreased"] for p in pairs)
    clock_backsteps=sum(p["host_epoch_delta_ms"]<0 for p in pairs)
    clock_ties=sum(p["host_epoch_delta_ms"]==0 for p in pairs)
    nonmonotone=bool(size_regressions or clock_backsteps or clock_ties)
    # The label describes ONLY the ordering of archived host CSV records.
    # It does not identify the original live failure, NTP adjustments, or
    # any guest/DAC timing defect.
    if size_regressions and (clock_backsteps or clock_ties):
        violation="MULTIPLE_HOST_CONTROL_INVARIANTS"
    elif size_regressions:
        violation="PCM_FILE_SIZE_DECREASED"
    elif clock_backsteps:
        violation="HOST_EPOCH_MOVED_BACKWARD"
    elif clock_ties:
        violation="HOST_EPOCH_EQUAL_ADJACENT"
    else:
        violation="NO_ARCHIVED_CONTROL_ORDER_VIOLATION"
    return {
        "schema":SCHEMA,
        "result":"STAGE304_ARCHIVED_CONTROL_PAIRS_CLASSIFIED",
        "original_canonical_event_names":[v[0] for v in events],
        "adjacent_original_host_control_pairs":pairs,
        "reproduces_nonmonotone_exit_control_source_refusal":nonmonotone,
        "archived_control_order_violation_kind":violation,
        "pcm_size_regression_pair_count":size_regressions,
        "host_epoch_backward_pair_count":clock_backsteps,
        "host_epoch_equal_pair_count":clock_ties,
        "archive_replay_not_proof_original_in_run_failure_cause":True,
        "buffered_file_size_not_guest_audio_sample_clock":True,
        "physical_Nintendo_Switch_audio_tested":False,
        "audible_audio_defect_verified":False,
    }
