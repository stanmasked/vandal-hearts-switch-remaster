#!/usr/bin/env python3
"""Audit ten NeXium scene transitions from real guest pixels, SD and PCM.

Guest INPUT and audout-buffer-return timings are internal software intervals:
neither is a physical keypress-to-speaker measurement, nor proof of no xruns.
"""
from __future__ import annotations

import argparse
from array import array
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

from PIL import Image, ImageChops
from audit_switch_guest_scene_trace import TraceError
from decode_nexium_guest_trace_frame import analyze_image

SCHEMA = "vh-nexium-scene-soak/v1"
RATE = 48000
FRAME_BYTES = 4
SCENE_COUNT = 10
EXPECTED_EVENTS = 3 + 5 * SCENE_COUNT
EXPECTED_NAMES = ("field_initial",) + tuple(
    f"{'focus' if i % 2 else 'field'}_{i}" for i in range(1, 11))
EXPECTED_SCENES = tuple(2 if i % 2 else 1 for i in range(1, 11))
STABLE_BEGIN_S = 1.35
STABLE_END_GUARD_S = .50
SAMPLE_FRAMES = RATE
EXPECTED_NRO_SHA256 = "58a438082f282ba279044d2a25fc1369e8493571a67b2082da41e0d8c0405929"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_file(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise TraceError(f"not a regular evidence file: {path.name}")
    return path.read_bytes()


def load_markers(path: Path, pcm_bytes: int) -> list[dict]:
    raw = read_file(path)
    if len(raw) > 4096 or not raw.endswith(b"\n"):
        raise TraceError("host event markers oversized or truncated")
    try:
        reader = csv.DictReader(raw.decode("ascii").splitlines(), strict=True)
        if reader.fieldnames != ["scene", "serial", "pcm_bytes", "epoch_ms"]:
            raise TraceError("host event schema differs")
        rows = list(reader)
    except (UnicodeError, csv.Error) as exc:
        raise TraceError("cannot parse host event markers") from exc
    if len(rows) != SCENE_COUNT + 1:
        raise TraceError("expected eleven host states for ten transitions")
    previous_byte, previous_epoch = -1, -1
    result = []
    for index, (row, phase) in enumerate(zip(rows, EXPECTED_NAMES)):
        if set(row) != {"scene", "serial", "pcm_bytes", "epoch_ms"}:
            raise TraceError("unknown or duplicated marker fields")
        if row["scene"] != phase or row["serial"] != str(index):
            raise TraceError(f"wrong host scene sequence at index {index}")
        for key in ("pcm_bytes", "epoch_ms"):
            v = row[key]
            if not v or not v.isdecimal() or (len(v)>1 and v[0]=="0"):
                raise TraceError("noncanonical marker integer")
        b, e = int(row["pcm_bytes"]), int(row["epoch_ms"])
        if b <= previous_byte or b % FRAME_BYTES or b >= pcm_bytes or e <= previous_epoch:
            raise TraceError("marker offsets/times not increasing or frame aligned")
        result.append({"scene": phase, "serial": index, "pcm_bytes": b, "epoch_ms": e})
        previous_byte, previous_epoch = b, e
    return result


def settled_pcm_metrics(raw: bytes, markers: list[dict]) -> list[dict]:
    if len(raw) % FRAME_BYTES or len(raw) < RATE*FRAME_BYTES*35:
        raise TraceError("PCM truncated or not stereo s16le of sufficient duration")
    samples = array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    whole_frames = len(samples)//2
    result = []
    for index, marker in enumerate(markers):
        begin = marker["pcm_bytes"]//FRAME_BYTES + round(RATE*STABLE_BEGIN_S)
        end = ((markers[index+1]["pcm_bytes"]//FRAME_BYTES)
               if index+1<len(markers) else whole_frames) - round(RATE*STABLE_END_GUARD_S)
        if end-begin < SAMPLE_FRAMES:
            raise TraceError(f"scene {index} has no full settled PCM interval")
        # Anchor the settled comparison to the first complete second
        # after the fixed stabilization interval. The final state has
        # no following input marker; the PCM monitor continues after
        # diagnostic Plus exits the guest. Taking the *midpoint* of
        # that unbounded tail would falsely classify post-exit monitor
        # silence as silence in MUSIC FIELD.
        start = begin
        summed = crossings = 0
        prev_l = prev_r = None
        for i in range(start,start+SAMPLE_FRAMES):
            left,right = samples[2*i],samples[2*i+1]
            summed += left*left+right*right
            if prev_l is not None:
                crossings += ((left<0)!=(prev_l<0))
                crossings += ((right<0)!=(prev_r<0))
            prev_l,prev_r=left,right
        rms = math.sqrt(summed/(SAMPLE_FRAMES*2))
        zcr = crossings*RATE/(4*SAMPLE_FRAMES)
        result.append({"scene":marker["scene"],"settled_slice_seconds":1.0,
                       "rms":round(rms,3),"zero_crossings_hz_proxy":round(zcr,3),
                       "non_silent":rms>=50})
    clipped = sum(abs(value)>=32767 for value in samples)
    if clipped:
        raise TraceError(f"full PCM contains {clipped} clipped sample values")
    if not all(x["non_silent"] for x in result):
        raise TraceError("settled scene window silent")
    field = [x["zero_crossings_hz_proxy"] for x in result
             if x["scene"].startswith("field")]
    focus = [x["zero_crossings_hz_proxy"] for x in result
             if x["scene"].startswith("focus")]
    if min(focus) <= max(field)*1.15:
        raise TraceError("repeated host PCM scene class separation not established")
    return result


def images_verify(root: Path) -> dict:
    screens, hashes = [], []
    for index in range(11):
        file = root/f"soak-scene-{index:02d}.png"
        raw = read_file(file)
        hashes.append(digest(raw))
        with Image.open(file) as opened:
            im = opened.convert("RGB")
        if im.size!=(1280,720):
            raise TraceError("unexpected NeXium screenshot geometry")
        screens.append(im.crop((960,600,1140,638)))
    changes=[]
    for before,after in zip(screens,screens[1:]):
        delta=ImageChops.difference(before,after)
        changes.append(sum(max(r,g,b)>24 for r,g,b in delta.getdata()))
    if len(changes)!=SCENE_COUNT or min(changes)<25:
        raise TraceError(f"ten visible MUSIC labels did not change: {changes}")
    return {"label_changed_pixels":changes,"scene_screenshot_sha256":hashes}


def near_rank(values: list[float],percentage: float) -> float:
    ordered=sorted(values)
    return round(ordered[max(0,math.ceil(len(ordered)*percentage)-1)],3)


def guest_timing(guest: dict) -> dict:
    audit=guest["guest_trace_audit"]
    serials=audit["complete_scene_serials"]
    if (audit["result"]!="GUEST_INTERNAL_PHASES_OBSERVED"
        or guest["event_rows"]!=EXPECTED_EVENTS or guest["dropped"]!=0
        or audit["unmatched_serial_zero_events"]!=3
        or audit["partial_scene_serials"] or len(serials)!=SCENE_COUNT
        or tuple(x["scene"] for x in serials)!=EXPECTED_SCENES
        or tuple(x["serial"] for x in serials)!=tuple(range(1,11))):
        raise TraceError("optical guest witness is not ten complete serials plus startup")
    specs=(
        ("observed_input_to_cue_accepted_ms","input_to_accept"),
        ("observed_input_to_page_return_ms","input_to_page_return"),
        ("observed_submit_call_to_return_ms","submit_call_to_return")
    )
    stats={}
    for source,label in specs:
        vals=[float(s[source]) for s in serials]
        if min(vals)<0:
            raise TraceError("negative guest internal interval")
        stats[label]={"median_ms":round(statistics.median(vals),3),
                      "p90_nearest_rank_ms":near_rank(vals,.9),
                      "max_ms":round(max(vals),3),
                      "over_50ms_count":sum(v>50 for v in vals)}
    return {"serials":serials,"statistics":stats}


def verify_run(root: Path,sd_root: Path,*,expected_sd_root: Path|None=None)->tuple[dict,str]:
    if not root.is_dir() or root.is_symlink():
        raise TraceError("scene-soak folder absent or symlinked")
    pcm=read_file(root/"soak-monitor-s16le-48k.pcm")
    markers=load_markers(root/"soak-events.csv",len(pcm))
    scene_pcm=settled_pcm_metrics(pcm,markers)
    visual=images_verify(root)
    optical=root/"soak-optical-trace.png"
    raw_png=read_file(optical)
    with Image.open(optical) as opened:
        guest, optical_csv=analyze_image(opened,require_four_scenes=False)
    timing=guest_timing(guest)
    raw_csv=optical_csv.encode("ascii")
    if sd_root.is_symlink() or not sd_root.is_dir():
        raise TraceError("SD root unavailable or symlinked")
    if expected_sd_root is not None and sd_root.resolve()!=expected_sd_root.resolve():
        raise TraceError("isolated SD root differs from expected session")
    expected_receipt=read_file(root/"soak-sd-root.txt").decode("utf-8").strip()
    if Path(expected_receipt).resolve()!=sd_root.resolve():
        raise TraceError("guest SD root receipt does not match session")
    sd_dir=sd_root/"sdmc"/"switch"/"vandal-hearts-remake"
    if sd_dir.is_symlink() or not sd_dir.is_dir():
        raise TraceError("guest SD directory missing")
    files=list(sd_dir.glob("audio-scene-trace-[0-9][0-9][0-9][0-9].csv"))
    if len(files)!=1:
        raise TraceError(f"expected one guest SD CSV, found {len(files)}")
    sd_bytes=read_file(files[0])
    if sd_bytes!=raw_csv or read_file(files[0])!=raw_csv:
        raise TraceError("optical and guest SD CSV bytes differ")
    return {
        "schema":SCHEMA,
        "result":"TEN_GUEST_SCENE_TRANSITIONS_DUAL_TRANSPORT_VERIFIED",
        "source":"real NeXium screenshot, separate guest SD CSV and virtual monitor PCM",
        "guest_nro_sha256_pinned":EXPECTED_NRO_SHA256,
        "guest_scene_serial_count":SCENE_COUNT,
        "guest_event_rows":guest["event_rows"],
        "guest_trace_dropped":guest["dropped"],
        "optical_packet_sha256":guest["packet_sha256"],
        "optical_packet_crc32":guest["packet_crc32"],
        "optical_png_sha256":digest(raw_png),
        "guest_csv_sha256":digest(raw_csv),
        "guest_sd_csv_filename":files[0].name,
        "guest_sd_csv_sha256":digest(sd_bytes),
        "host_scene_markers_sha256":digest(read_file(root/"soak-events.csv")),
        "pcm_sha256":digest(pcm),
        "pcm_bytes":len(pcm),
        "pcm_duration_seconds":round(len(pcm)/(RATE*FRAME_BYTES),3),
        "full_pcm_observed_clipped_values":0,
        "pcm_settled_1s_windows":scene_pcm,
        "visual_scene_assertions":visual,
        "guest_internal_events":timing["serials"],
        "guest_interval_statistics":timing["statistics"],
        "host_guest_clock_alignment_proven":False,
        "input_to_dac_latency_ms":None,
        "sample_accurate_music_onset_proven":False,
        "no_audout_underruns_proven":False,
        "real_soundtrack_confirmed":False,
        "hardware_status":"HARDWARE NOT TESTED"
    },optical_csv


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--soak-dir",type=Path,required=True)
    parser.add_argument("--sd-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--optical-csv-output",type=Path,required=True)
    args=parser.parse_args()
    if (args.output.exists() or args.output.is_symlink() or
        args.optical_csv_output.exists() or args.optical_csv_output.is_symlink()):
        print("refuse overwrite of scene-soak evidence",file=sys.stderr)
        return 2
    try:
        report,csv_text=verify_run(args.soak_dir,args.sd_root)
        args.optical_csv_output.write_text(csv_text,encoding="ascii")
        args.output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({"result":report["result"],
                          "guest_events":report["guest_event_rows"],
                          "pcm_duration_seconds":report["pcm_duration_seconds"],
                          "optical_and_sd_sha256":report["guest_csv_sha256"],
                          "hardware_status":report["hardware_status"]},indent=2))
        return 0
    except (TraceError,OSError,UnicodeError,ValueError) as exc:
        verdict={"schema":SCHEMA,"result":"GUEST_TEN_SCENE_SOAK_NOT_VERIFIED",
                 "error":str(exc),"hardware_status":"HARDWARE NOT TESTED"}
        if not args.output.exists() and not args.output.is_symlink():
            args.output.write_text(json.dumps(verdict,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(verdict),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
