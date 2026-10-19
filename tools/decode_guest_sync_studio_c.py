#!/usr/bin/env python3
"""Decode guest-owned exact-clock synthetic STUDIO_C wet-tail counterfactual."""
import argparse
import json
import struct
import zlib
from pathlib import Path

from decode_map02_guest_scene_trace import decode_packet_image

CRC_OFFSET=909
FIELDS=("initial_hash","wet_hash","reset_hash")
def decode(packet):
    if len(packet)!=924 or packet[:8]!=b"VHSYNC01" or packet[8]!=1:
        raise ValueError("Invalid STUDIO_C guest counterfactual packet identity")
    if any(packet[11:12]) or any(packet[72:CRC_OFFSET]) or any(packet[913:]):
        raise ValueError("Nonzero reserved guest counterfactual bytes")
    if struct.unpack_from("<I",packet,CRC_OFFSET)[0]!=zlib.crc32(packet[:CRC_OFFSET]):
        raise ValueError("Bad guest synchronized tail witness CRC32")
    if packet[9]!=0 or packet[10]!=15:
        raise ValueError("Guest synchronized DSP witness reports an incomplete/failed check")
    pre,tail,different,wet_n,reset_n=struct.unpack_from("<IIIII",packet,12)
    initial_hash,wet_hash,reset_hash=struct.unpack_from("<QQQ",packet,32)
    pre_notes,next_notes,replays,failure=struct.unpack_from("<IIII",packet,56)
    if failure:
        raise ValueError("Guest replay failed at source line")
    if (pre,tail,different)!=(64,48,48) or not wet_n or reset_n:
        raise ValueError("Guest synthesized tail not aligned or unexpectedly dry/silent")
    if (pre_notes,next_notes,replays,failure)!=(1,0,2,0):
        raise ValueError("Wrong synchronized input, note ownership or replay")
    if not initial_hash or not wet_hash or not reset_hash or wet_hash==reset_hash:
        raise ValueError("No isolated guest STUDIO_C synthetic tail fingerprint difference")
    return {
        "schema":"vh-map02-guest-synchronized-studio-c/v1",
        "pre_blocks":pre, "post_switch_blocks":tail,
        "different_blocks":different,
        "wet_nonzero_sample_values":wet_n,
        "reset_nonzero_sample_values":reset_n,
        "original_note_ons":pre_notes,"new_scene_note_ons":next_notes,
        "identical_input_replays":replays,
        "pre_switch_pcm_fnv1a64":f"{initial_hash:016x}",
        "retained_tail_pcm_fnv1a64":f"{wet_hash:016x}",
        "reset_tail_pcm_fnv1a64":f"{reset_hash:016x}",
        "synchronized_guest_synthetic_dsp_causality":True,
        "guest_live_audout_studio_c_causality_proven":False,
        "sample_aligned_external_virtual_audio":False,
        "original_game_music_verified":False,
        "physical_switch_audio_tested":False,
        "result":"GUEST_SYNCHRONIZED_SYNTHETIC_STUDIO_C_TAIL_PROVEN"
    }

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image",type=Path,required=True)
    ap.add_argument("--mode",type=int,choices=(0,1),required=True)
    ap.add_argument("--output",type=Path,required=True)
    options=ap.parse_args()
    try:
        result=decode(decode_packet_image(options.image))
        result["outer_nro_wet_tail_mode"]=options.mode
    except (OSError,ValueError,TypeError) as exc:
        result={"schema":"vh-map02-guest-synchronized-studio-c/v1",
                "outer_nro_wet_tail_mode":options.mode,
                "result":"GUEST_SYNCHRONIZED_TAIL_UNVERIFIED",
                "reason":str(exc),
                "synchronized_guest_synthetic_dsp_causality":False,
                "physical_switch_audio_tested":False}
    options.output.parent.mkdir(parents=True,exist_ok=True)
    options.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0 if result["result"]=="GUEST_SYNCHRONIZED_SYNTHETIC_STUDIO_C_TAIL_PROVEN" else 1
if __name__=="__main__":
    raise SystemExit(main())
