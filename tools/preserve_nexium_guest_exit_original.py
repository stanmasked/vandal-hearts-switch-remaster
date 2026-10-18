#!/usr/bin/env python3
"""Stage310: preserve original guest exit CSV bytes with end-to-end source audit.

The original guest SD CSV is recorded after audio-thread join and contains
ONLY five diagnostic software clock timestamps, never retail game data.
Never invent the source from an already-derived JSON report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from audit_nexium_guest_exit_timeline import (
    audit_guest_root,parse_exit_csv,OBSERVED,UNOBSERVED,SUBDIR,ExitTimelineError,
)
from audit_nexium_guest_optical_exit_clock import audit_guest_clocks,BOTH
from audit_switch_guest_scene_trace import TraceError

SCHEMA="vh-nexium-original-guest-exit-csv-preservation/v1"
FILE_NAME="audio-exit-timeline-000.csv"


def preserve_original(root: Path, stage307: dict, stage308: dict,
                      optical_png: bytes, destination: Path) -> dict:
    if (not isinstance(stage307,dict) or not isinstance(stage308,dict)
            or destination.exists() or destination.is_symlink()):
        raise TraceError("invalid source/report arguments or existing destination")
    # Always inspect original isolated guest SD, not only a prior receipt.
    observed=audit_guest_root(root)
    if observed!=stage307:
        raise TraceError("existing Stage307 receipt not identical to reread original guest SD")
    current_optical=audit_guest_clocks(optical_png,observed)
    if current_optical!=stage308:
        raise TraceError("Stage308 guest CRC optical source receipt does not reproduce")
    if observed["result"]==UNOBSERVED:
        return {
            "schema":SCHEMA,
            "result":"ORIGINAL_GUEST_EXIT_SD_NOT_OBSERVED",
            "original_guest_exit_csv_preserved":False,
            "guest_exit_receipt_sha256":None,
            "optical_scene_png_sha256":current_optical["optical_scene_png_sha256"],
            "original_source_csv_bytes_independently_reaudited":False,
            "guest_to_host_pcm_clock_mapping_verified":False,
            "original_soundtrack_or_audible_dropout_verified":False,
            "physical_Nintendo_Switch_audio_tested":False,
        }
    if observed["result"]!=OBSERVED or current_optical["result"]!=BOTH:
        raise TraceError("original observed guest software exit incomplete")
    # File path is a constant in the checked Stage307 guest export, not
    # supplied by another report or untrusted CSV cell.
    name=SUBDIR/FILE_NAME
    if observed.get("guest_csv_path")!=str(name):
        raise TraceError("guest exit CSV path changed")
    p=root/name
    if p.is_symlink() or not p.is_file() or p.stat().st_size>1024:
        raise TraceError("unsafe original guest exit CSV")
    raw=p.read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    if (parse_exit_csv(raw)["result"]!=OBSERVED
            or digest!=observed["guest_exit_csv_sha256"]
            or digest!=current_optical["guest_exit_csv_sha256"]):
        raise TraceError("source original SHA and guest software exit witness mismatch")
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive write: never truncate a previously preserved source file.
    with destination.open("xb") as file:
        file.write(raw)
    if destination.read_bytes()!=raw:
        raise TraceError("postcopy guest original source bytes changed")
    return {
        "schema":SCHEMA,
        "result":"ORIGINAL_GUEST_EXIT_CSV_BYTES_PRESERVED_AND_REAUDITED",
        "original_guest_exit_csv_preserved":True,
        "original_guest_exit_csv_filename":destination.name,
        "original_guest_exit_csv_size":len(raw),
        "guest_exit_receipt_sha256":digest,
        "optical_scene_png_sha256":current_optical["optical_scene_png_sha256"],
        "guest_exit_software_chronology_verified":True,
        "original_source_csv_bytes_independently_reaudited":True,
        "guest_to_host_pcm_clock_mapping_verified":False,
        "original_soundtrack_or_audible_dropout_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("guest-root-file","stage307","stage308","optical-image",
                "output-original","output-report"):
        parser.add_argument("--"+key,required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        if args.output_report.exists() or args.output_report.is_symlink():
            raise TraceError("refuse overwrite original guest provenance report")
        if args.guest_root_file.is_symlink() or not args.guest_root_file.is_file():
            raise TraceError("guest SD root locator not original regular file")
        root_text=args.guest_root_file.read_text(encoding="utf-8").strip()
        if not root_text.startswith("/") or "\n" in root_text or "\x00" in root_text:
            raise TraceError("invalid original guest SD root path")
        if (args.stage307.is_symlink() or args.stage308.is_symlink()
                or args.optical_image.is_symlink()):
            raise TraceError("source reports or optical PNG are symlinks")
        original307=json.loads(args.stage307.read_text(encoding="utf-8"))
        original308=json.loads(args.stage308.read_text(encoding="utf-8"))
        preserved=preserve_original(
            Path(root_text),original307,original308,
            args.optical_image.read_bytes(),args.output_original)
        args.output_report.write_text(
            json.dumps(preserved,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print(json.dumps({
            "result":preserved["result"],
            "original_guest_exit_csv_preserved":
                preserved["original_guest_exit_csv_preserved"],
            "hardware_audio_verified":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({"result":"STAGE310_GUEST_ORIGINAL_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
