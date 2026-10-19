#!/usr/bin/env python3
"""Decode same-clock 48-kHz native resampler/ramp guest bridge receipt."""
import argparse
import json
import struct
import zlib
from pathlib import Path

from decode_map02_guest_scene_trace import decode_packet_image

def decode(packet):
    if len(packet)!=924 or packet[:8]!=b"VH48K001" or packet[8]!=1:
        raise ValueError("Invalid native 48-kHz witness packet identity")
    if any(packet[11:12]) or any(packet[36:40]) or any(packet[68:909]) or any(packet[913:]):
        raise ValueError("Nonzero reserved output-stage bytes")
    if struct.unpack_from("<I",packet,909)[0]!=zlib.crc32(packet[:909]):
        raise ValueError("Invalid output-stage CRC32")
    if packet[9]!=0 or packet[10]!=15:
        raise ValueError("Native 48-kHz guest bridge flagged incomplete or failed")
    pre,tail,different,wet,first_residue,later_residue=struct.unpack_from("<IIIIII",packet,12)
    prehash,wethash,resethash=struct.unpack_from("<QQQ",packet,40)
    rounds=struct.unpack_from("<I",packet,64)[0]
    if not (64*555<=pre<=64*559 and 48*555<=tail<=48*559
            and different==48 and 0<wet<=2*tail and rounds==2):
        raise ValueError("Output-stage clocks, tail differences or replay invalid")
    if first_residue>2 or later_residue!=0:
        raise ValueError("Resampler reset residue exceeds one boundary stereo frame")
    if not prehash or not wethash or not resethash or wethash==resethash:
        raise ValueError("No native 48-kHz output-stage history contrast")
    return {
        "schema":"vh-map02-guest-native-48k-bridge/v1",
        "result":"GUEST_NATIVE_48K_SYNCHRONIZED_TAIL_OBSERVED",
        "pre_switch_native_frames":pre,"post_switch_native_frames":tail,
        "different_post_switch_native_pages":different,
        "retained_tail_nonzero_sample_values":wet,
        "reset_first_page_nonzero_sample_values":first_residue,
        "reset_later_pages_nonzero_sample_values":later_residue,
        "pre_switch_native_fnv1a64":f"{prehash:016x}",
        "wet_native_fnv1a64":f"{wethash:016x}",
        "reset_native_fnv1a64":f"{resethash:016x}",
        "identical_complete_replays":rounds,
        "rate_hz":48000,
        "guest_synthetic_postprocess_causality":True,
        "live_audout_music_sample_aligned":False,
        "physical_switch_speakers_verified":False
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--image",required=True,type=Path)
    p.add_argument("--mode",required=True,type=int,choices=(0,1))
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    try:
        result=decode(decode_packet_image(a.image))
        result["outer_nro_wet_tail_mode"]=a.mode
    except (OSError,TypeError,ValueError) as exc:
        result={"schema":"vh-map02-guest-native-48k-bridge/v1",
                "result":"NATIVE_48K_BRIDGE_UNVERIFIED","reason":str(exc),
                "outer_nro_wet_tail_mode":a.mode,
                "live_audout_music_sample_aligned":False,
                "physical_switch_speakers_verified":False}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0 if result["result"]=="GUEST_NATIVE_48K_SYNCHRONIZED_TAIL_OBSERVED" else 1

if __name__=="__main__":raise SystemExit(main())
