#!/usr/bin/env python3
"""Decode separate post-join first-page PCM metrics, not guest reverb causality."""
import argparse
import hashlib
import json
import math
import struct
import zlib
from pathlib import Path

from decode_map02_guest_scene_trace import decode_packet_image

MAGIC=b"VHPCM01A"
CRC_OFFSET=909
ROW_START=12
ROW_LEN=28

def decode(packet):
    if len(packet)!=924 or packet[:8]!=MAGIC or packet[8]!=2:
        raise ValueError("Invalid guest quantitative PCM packet identity")
    if any(packet[9:12]) or any(packet[68:CRC_OFFSET]) or any(packet[913:]):
        raise ValueError("Nonzero metric reserved bytes")
    if struct.unpack_from("<I",packet,CRC_OFFSET)[0]!=zlib.crc32(packet[:CRC_OFFSET]):
        raise ValueError("Quantitative guest PCM CRC32 mismatch")
    results=[]
    for index, expected_scene in enumerate((2,1)):
        serial,scene,flags,frames,nonzero,peak,energy,fingerprint=struct.unpack_from(
            "<IBBHHHQQ",packet,ROW_START+index*ROW_LEN)
        if serial!=index+1 or scene!=expected_scene or flags!=1:
            raise ValueError("PCM metrics cannot be linked to expected A/B ticket")
        sample_count=frames*2
        if not (1<=frames<=1024 and 1<=nonzero<=sample_count and
                1<=peak<=32768 and nonzero<=energy<=sample_count*peak*peak):
            raise ValueError("PCM metrics violate physical integer bounds")
        results.append({
            "serial":serial,"scene":scene,"frames":frames,
            "sample_values":sample_count,"nonzero_sample_values":nonzero,
            "absolute_peak_s16":peak,"sum_squares_s16":energy,
            "rms_s16":round(math.sqrt(energy/sample_count),6),
            "first_page_fnv1a64":f"{fingerprint:016x}"
        })
    return results

def report(path, mode):
    records=decode(decode_packet_image(path))
    return {
        "schema":"vh-map02-first-page-metrics/v1",
        "mode":mode,
        "tickets":records,
        "result":"GUEST_FIRST_PAGES_QUANTIFIED",
        "first_pages_nonzero":True,
        "crc32_and_ticket_integrity_verified":True,
        "sample_aligned_between_guest_modes":False,
        "reverb_tail_causality_proven":False,
        "original_ps1_soundtrack_fidelity_proven":False,
        "physical_switch_audio_tested":False
    }

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image",type=Path,required=True)
    ap.add_argument("--mode",type=int,choices=(0,1),required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    try:
        result=report(args.image,args.mode)
    except (OSError,ValueError,TypeError) as exc:
        result={"schema":"vh-map02-first-page-metrics/v1",
                "mode":args.mode,"result":"GUEST_FIRST_PAGE_METRICS_UNVERIFIED",
                "reason":str(exc),"reverb_tail_causality_proven":False,
                "physical_switch_audio_tested":False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result["result"]=="GUEST_FIRST_PAGES_QUANTIFIED" else 1

if __name__=="__main__":
    raise SystemExit(main())
