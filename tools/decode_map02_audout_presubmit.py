#!/usr/bin/env python3
"""Strictly decode opt-in PCM16 pre-audout guest screen (not DAC evidence)."""
import argparse
import json
import struct
import zlib
from pathlib import Path

from decode_map02_guest_scene_trace import decode_packet_image

MAGIC=b"VHPRE001"
FRAMES=(557,558)
ROWS=8

def decode(packet):
    if len(packet)!=924 or packet[:8]!=MAGIC:
        raise ValueError("Invalid pre-submit packet identity")
    if packet[8]!=ROWS or packet[9]!=0:
        raise ValueError("Pre-submit page count/pending state invalid")
    if any(packet[10:12]) or any(packet[208:909]) or any(packet[913:]):
        raise ValueError("Nonzero pre-submit reserved bytes")
    if struct.unpack_from("<I",packet,909)[0]!=zlib.crc32(packet[:909]):
        raise ValueError("Invalid pre-submit packet CRC32")
    mismatches=struct.unpack_from("<I",packet,12)[0]
    if mismatches!=0:
        raise ValueError("Pre-submit PCM changed before audout")
    pages=[]
    for i in range(ROWS):
        frames,attempts,returned,fnv,crc=struct.unpack_from(
            "<IIIQI",packet,16+i*24)
        if frames not in FRAMES or not 1<=attempts<=4 or returned!=1:
            raise ValueError(f"Pre-submit page {i} invalid frame/return state")
        if not fnv or not crc:
            raise ValueError(f"Pre-submit page {i} missing digest")
        pages.append({"index":i,"frames":frames,"attempts":attempts,
                      "descriptor_released_returns":returned,
                      "fnv1a64":f"{fnv:016x}","crc32":f"{crc:08x}"})
    return {
        "schema":"vh-map02-presubmit-optical/v1",
        "result":"GUEST_PRESUBMIT_PCM_PAGES_MATCHED",
        "observed_pages":ROWS,"mismatches":mismatches,"pages":pages,
        "actual_audout_call_observed":True,
        "live_dac_samples_proven":False,
        "physical_switch_speaker_audio_verified":False,
        "original_ps1_music_fidelity_verified":False
    }

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    try:
        result=decode(decode_packet_image(args.image))
    except (OSError,TypeError,ValueError) as exc:
        result={"schema":"vh-map02-presubmit-optical/v1",
                "result":"GUEST_PRESUBMIT_UNVERIFIED",
                "reason":str(exc),"live_dac_samples_proven":False,
                "physical_switch_speaker_audio_verified":False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0 if result["result"]=="GUEST_PRESUBMIT_PCM_PAGES_MATCHED" else 1

if __name__=="__main__":
    raise SystemExit(main())
