#!/usr/bin/env python3
"""Stage308: verify guest-observed exit time relative to CRC-verified optical scene events.

Only two actual guest-origin records may establish guest software order.
Never infer host PCM / guest clock alignment or physical audible output.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

from PIL import Image
from audit_nexium_guest_exit_timeline import (
    OBSERVED, UNOBSERVED, audit_guest_root,
)
from decode_nexium_guest_trace_frame import analyze_image
from audit_switch_guest_scene_trace import TraceError

SCHEMA = "vh-nexium-guest-optical-scene-versus-exit-monotonic/v1"
NO_EXIT = "OPTICAL_SCENES_CONFIRMED_EXIT_SD_NOT_OBSERVED"
INCOMPLETE = "OPTICAL_SCENES_CONFIRMED_EXIT_GUEST_INCOMPLETE"
BOTH = "GUEST_OPTICAL_SCENES_PRECEDE_VERIFIED_GUEST_EXIT"


def audit_guest_clocks(optical_bytes: bytes, guest: dict) -> dict:
    if not isinstance(guest, dict):
        raise TraceError("guest exit data missing")
    with Image.open(io.BytesIO(optical_bytes)) as im:
        optical, csv_original = analyze_image(im, require_four_scenes=True)
    if (optical["result"] != "FOUR_GUEST_SCENE_INTERNAL_PHASES_PIXELS_VERIFIED"
            or optical["guest_trace_audit"]["dropped"] != 0
            or optical["guest_trace_audit"]["partial_scene_serials"]
            or optical["audible_music_confirmed"] is not False):
        raise TraceError("original guest optical scene evidence failed")
    reader = csv.DictReader(io.StringIO(csv_original), strict=True)
    rows = list(reader)
    if reader.fieldnames != [
            "index", "event", "serial", "scene", "monotonic_ns", "dropped_total"]:
        raise TraceError("unexpected original guest optical event schema")
    if not rows or len(rows) != optical["event_rows"]:
        raise TraceError("original optical decoded row count mismatch")
    newest = max(int(x["monotonic_ns"]) for x in rows)
    input_rows = [x for x in rows if x["event"] == "INPUT"]
    if len(input_rows) != 4 or not all(int(x["monotonic_ns"]) for x in input_rows):
        raise TraceError("optical guest input scene sequence incomplete")
    last_input = max(int(x["monotonic_ns"]) for x in input_rows)
    if last_input > newest:
        raise TraceError("last observed input beyond optical event maximum")

    found = guest.get("result")
    report = {
        "schema": SCHEMA,
        "optical_scene_png_sha256": hashlib.sha256(optical_bytes).hexdigest(),
        "optical_packet_sha256": optical["packet_sha256"],
        "optical_guest_event_rows": len(rows),
        "optical_scene_dropped_rows": 0,
        "optical_guest_last_input_ns": last_input,
        "optical_guest_last_scene_event_ns": newest,
        "guest_exit_receipt_observed": False,
        "same_guest_monotonic_clock_provenance": (
            "armGetSystemTick/armTicksToNs guest software timebase"),
        "guest_to_host_PCM_sample_clock_alignment_verified": False,
        "exit_control_caused_audible_dropouts": False,
        "original_retail_soundtrack_confirmed": False,
        "physical_Nintendo_Switch_audio_tested": False,
    }
    if found == UNOBSERVED:
        if guest.get("guest_sd_receipt_observed") is not False:
            raise TraceError("unobserved SD source claims to be observed")
        report.update({
            "result": NO_EXIT,
            "guest_exit_observed": False,
            "guest_exit_csv_sha256": None,
            "guest_exit_plus_observed_ns": None,
            "scene_last_event_to_plus_ns": None,
            "guest_exit_order_verified": False,
        })
        return report
    if found == "GUEST_EXIT_EVENTS_INCOMPLETE":
        if (guest.get("guest_sd_receipt_observed") is not True or
                "guest_exit_csv_sha256" not in guest):
            raise TraceError("incomplete exit not original guest SD receipt")
        report.update({
            "result": INCOMPLETE,
            "guest_exit_observed": True,
            "guest_exit_receipt_observed": True,
            "guest_exit_csv_sha256": guest["guest_exit_csv_sha256"],
            "guest_exit_plus_observed_ns": None,
            "scene_last_event_to_plus_ns": None,
            "guest_exit_order_verified": False,
        })
        return report
    if found != OBSERVED or guest.get("guest_sd_receipt_observed") is not True:
        raise TraceError("unrecognized or forged guest software exit receipt")
    times = guest.get("guest_monotonic_timestamps_ns")
    if not isinstance(times, dict):
        raise TraceError("missing guest exit software times")
    plus = times.get("plus_observed")
    stop = times.get("stop_requested")
    closed = times.get("audout_closed")
    joined = times.get("worker_joined")
    if any(type(x) is not int or x <= 0 for x in (plus,stop,closed,joined)):
        raise TraceError("missing measured software exit event")
    if (not newest <= plus < stop < closed < joined
            or guest.get("host_PCM_to_guest_timestamp_mapping_verified") is not False
            or guest.get("physical_Nintendo_Switch_audio_tested") is not False):
        raise TraceError("guest scene/exit times reversed or overclaimed")
    digest = guest.get("guest_exit_csv_sha256")
    if not isinstance(digest,str) or len(digest) != 64:
        raise TraceError("missing guest exit source hash")
    report.update({
        "result": BOTH,
        "guest_exit_observed": True,
        "guest_exit_receipt_observed": True,
        "guest_exit_csv_sha256": digest,
        "guest_exit_plus_observed_ns": plus,
        "scene_last_event_to_plus_ns": plus - newest,
        "guest_exit_stop_requested_ns": stop,
        "guest_exit_audout_closed_ns": closed,
        "guest_exit_worker_joined_ns": joined,
        "guest_exit_order_verified": True,
    })
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--optical-image",type=Path,required=True)
    parser.add_argument("--guest-root-file",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise TraceError("refuse overwrite Stage308 output")
        if args.optical_image.is_symlink() or not args.optical_image.is_file():
            raise TraceError("source optical screenshot missing or symlink")
        if args.guest_root_file.is_symlink() or not args.guest_root_file.is_file():
            raise TraceError("original NeXium SD root locator missing")
        root=args.guest_root_file.read_text(encoding="utf-8").strip()
        if not root.startswith("/") or "\n" in root or "\x00" in root:
            raise TraceError("invalid original SD mount root")
        guest = audit_guest_root(Path(root))
        result = audit_guest_clocks(args.optical_image.read_bytes(),guest)
        args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",
                               encoding="utf-8")
        print(json.dumps({
            "result":result["result"],
            "guest_exit_order_verified":result["guest_exit_order_verified"],
            "cross_guest_host_clock_verified":False,
            "audible_sound_verified":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({"result":"STAGE308_GUEST_CLOCK_CORRELATION_NOT_VERIFIED",
                          "error":str(exc),
                          "audible_audio_verified":False}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
