#!/usr/bin/env python3
"""Exact, source-attributed PCM16 stereo page search in one virtual 48k sink.

ROM-free experimental analysis only. A match proves identical PCM bytes in
the captured virtual sink; it does NOT prove DAC timing, actual loudspeakers,
PS1 soundtrack fidelity, or cue-level audiovisual synchronization.
"""
import argparse
import array
import json
import math
import re
import sys
import zlib
from collections import defaultdict
from pathlib import Path

FNV_OFFSET=0xcbf29ce484222325
FNV_PRIME=0x100000001b3
MASK=(1<<64)-1
FRAME_BYTES=4
RATE=48000
MAX_CAPTURE_BYTES=32*1024*1024
HEX16=re.compile(r"^[0-9a-f]{16}$")
HEX8=re.compile(r"^[0-9a-f]{8}$")

def fnv1a64(data):
    h=FNV_OFFSET
    for b in data:
        h=((h^b)*FNV_PRIME)&MASK
    return h

def validate_receipt(receipt):
    if not isinstance(receipt,dict) or (
        receipt.get("schema")!="vh-map02-presubmit-optical/v1" or
        receipt.get("result")!="GUEST_PRESUBMIT_PCM_PAGES_MATCHED" or
        receipt.get("observed_pages")!=8 or receipt.get("mismatches")!=0 or
        receipt.get("actual_audout_call_observed") is not True):
        raise ValueError("Guest optical receipt identity or proof invalid")
    pages=receipt.get("pages")
    if not isinstance(pages,list) or len(pages)!=8:
        raise ValueError("Guest receipt requires eight distinct pages")
    checked=[]
    for i,p in enumerate(pages):
        if not isinstance(p,dict) or type(p.get("index")) is not int or p["index"]!=i:
            raise ValueError("Page order or index invalid")
        if type(p.get("frames")) is not int or p["frames"] not in (557,558):
            raise ValueError("Incorrect native page frame count")
        if (type(p.get("attempts")) is not int or
            not 1<=p["attempts"]<=3 or
            type(p.get("descriptor_released_returns")) is not int or
            p["descriptor_released_returns"]!=1):
            raise ValueError("Guest descriptor return/attempts invalid")
        fnv=p.get("fnv1a64");crc=p.get("crc32")
        if not isinstance(fnv,str) or not HEX16.fullmatch(fnv) or not isinstance(crc,str) or not HEX8.fullmatch(crc):
            raise ValueError("Missing or malformed per-page fingerprint")
        checked.append({"frames":p["frames"],"fnv":int(fnv,16),"crc":int(crc,16)})
    return checked

def audit(receipt, raw, max_seconds=20):
    pages=validate_receipt(receipt)
    if not isinstance(raw,bytes) or not raw or len(raw)%FRAME_BYTES:
        raise ValueError("Monitor must be nonempty PCM16LE stereo frames")
    if len(raw)>MAX_CAPTURE_BYTES or len(raw)>int(max_seconds*RATE*FRAME_BYTES):
        raise ValueError("Monitor exceeds bounded 48-kHz capture limit")
    total=len(raw)//FRAME_BYTES
    view=memoryview(raw)
    targets=defaultdict(lambda:defaultdict(list))
    for i,p in enumerate(pages):
        targets[p["frames"]][p["crc"]].append(i)
    matched=[[] for _ in pages]
    examined=0
    for frames,crcs in targets.items():
        win=frames*FRAME_BYTES
        for start in range(total-frames+1):
            offset=start*FRAME_BYTES
            block=view[offset:offset+win]
            crc=zlib.crc32(block)
            indices=crcs.get(crc)
            if not indices:continue
            fnv=fnv1a64(block)
            examined+=1
            for i in indices:
                if pages[i]["fnv"]==fnv and len(matched[i])<32:
                    matched[i].append(start)
    # Every page must occur *in order with NO insertions, drops or skew*.
    matches=set()
    if all(matched):
        others=[set(x) for x in matched[1:]]
        for first in matched[0]:
            at=first
            for i,p in enumerate(pages[:-1]):
                at+=p["frames"]
                if at not in others[i]: break
            else: matches.add(first)
    exact=bool(matches)
    # The first real NeXium monitor proved that every independent page
    # occurred, yet the eight were not perfectly contiguous. Report the
    # observed offsets and signed gaps WITHOUT guessing the cause. With
    # duplicated/absent page fingerprints a single offset is ambiguous.
    unique_offsets=[x[0] if len(x)==1 else None for x in matched]
    all_unique=all(x is not None for x in unique_offsets)
    order_preserved=(all(unique_offsets[i]<unique_offsets[i+1]
                         for i in range(len(unique_offsets)-1))
                     if all_unique else None)
    gaps=[(unique_offsets[i+1]-unique_offsets[i]-pages[i]["frames"])
          if unique_offsets[i] is not None and unique_offsets[i+1] is not None
          else None for i in range(len(pages)-1)]
    # Positive = extra PCM frames between complete exact page spans;
    # negative = overlapping or reordered spans, not 'negative latency'.
    gap_ms=[round(1000*g/RATE,6) if g is not None else None for g in gaps]
    start_deltas=[unique_offsets[i+1]-unique_offsets[i]
                  if unique_offsets[i] is not None and unique_offsets[i+1] is not None
                  else None for i in range(len(pages)-1)]
    # Do not attribute the block cadence to audout/NeXium/PulseAudio
    # without a controlled timing experiment. These are raw observables.
    alignment_residues=[start % 512 if start is not None else None
                        for start in unique_offsets]
    same_512_phase=(len(set(alignment_residues))==1 if all_unique else None)
    deltas_512_aligned=(all(delta%512==0 for delta in start_deltas)
                        if all_unique else None)
    # Examine PCM samples in each *positive* inter-page region, not
    # only the position of individual CRC matches. An exact zero means
    # genuine PCM16 digital silence in the captured virtual stream.
    nonzero_between=[]
    for i,gap in enumerate(gaps):
        if gap is None or gap<0:
            nonzero_between.append(None)
            continue
        a=(unique_offsets[i]+pages[i]["frames"])*FRAME_BYTES
        b=unique_offsets[i+1]*FRAME_BYTES
        nonzero_between.append(sum(1 for x in view[a:b] if x!=0))
    all_gaps_silent=(all(n==0 for n in nonzero_between)
                     if all_unique and all(g>=0 for g in gaps) else None)
    signal=array.array("h")
    signal.frombytes(raw)
    if sys.byteorder!="little": signal.byteswap()
    sample_count=len(signal)
    count=sum(abs(int(x))>=256 for x in signal)
    rms=math.sqrt(sum(float(x)*x for x in signal)/sample_count)
    first=min(matches) if matches else None
    return {
        "schema":"vh-map02-presubmit-sink-audit/v1",
        "result":"EXACT_EIGHT_PAGE_VIRTUAL_SINK_MATCH" if exact else "NO_EXACT_EIGHT_PAGE_SINK_MATCH",
        "capture_frames":total,"capture_rate_hz":RATE,
        "capture_sample_format":"s16le","capture_channels":2,
        "capture_duration_seconds":round(total/RATE,6),
        "capture_rms":round(rms,6),"monitor_samples_ge_256":count,
        "per_page_matches":[len(x) for x in matched],
        "unique_page_frame_offsets":unique_offsets,
        "all_eight_pages_found_once":all_unique,
        "unique_page_order_preserved":order_preserved,
        "inter_page_gap_frames":gaps,
        "inter_page_gap_ms":gap_ms,
        "page_start_delta_frames":start_deltas,
        "page_start_modulo_512":alignment_residues,
        "all_page_starts_same_512_phase":same_512_phase,
        "all_page_start_deltas_multiple_of_512":deltas_512_aligned,
        "inter_page_gap_nonzero_pcm_bytes":nonzero_between,
        "all_nonnegative_inter_page_gaps_digital_silence":all_gaps_silent,
        "total_positive_gap_frames":(
            sum(max(0,g) for g in gaps) if all_unique else None),
        "all_pages_contiguous_in_order":(
            all(g==0 for g in gaps) and bool(order_preserved)
            if all_unique else False),
        "crc_collision_candidates_hashed":examined,
        "exact_contiguous_chain_count":len(matches),
        "first_exact_chain_frame_offset":first,
        "first_exact_chain_seconds":round(first/RATE,6) if first is not None else None,
        "verified_stereo_frames":sum(p["frames"] for p in pages) if exact else 0,
        "guest_pcm_to_virtual_sink_exact_bytes_verified":exact,
        "actual_physical_dac_samples_verified":False,
        "switch_speaker_audio_verified":False,
        "ps1_soundtrack_fidelity_verified":False,
        "sample_aligned_music_cue_proven":False,
        "note":("Exact unscaled, unswapped PCM16LE 48k stereo bytes found in one "
                "virtual sink recording; this is NOT physical output evidence") if exact
               else ("No contiguous eight-page byte-exact match. This does NOT prove "
                     "silence: virtual sink may delay, mix, gain-scale, resample, "
                     "swap channels, or record a different interval")
    }

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guest",type=Path,required=True)
    parser.add_argument("--monitor",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--max-seconds",type=float,default=20.)
    parser.add_argument("--require-exact",action="store_true")
    args=parser.parse_args()
    try:
        if not 0<args.max_seconds<=60:raise ValueError("Invalid capture limit")
        result=audit(json.loads(args.guest.read_text()),args.monitor.read_bytes(),
                     args.max_seconds)
    except (OSError,ValueError,TypeError,OverflowError) as exc:
        result={"schema":"vh-map02-presubmit-sink-audit/v1",
                "result":"SINK_ANALYSIS_UNVERIFIED","reason":str(exc),
                "guest_pcm_to_virtual_sink_exact_bytes_verified":False,
                "actual_physical_dac_samples_verified":False,
                "switch_speaker_audio_verified":False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps(result,sort_keys=True,indent=2))
    if result["result"]=="SINK_ANALYSIS_UNVERIFIED":return 1
    if args.require_exact and result["result"]!="EXACT_EIGHT_PAGE_VIRTUAL_SINK_MATCH":return 1
    return 0

if __name__=="__main__":
    raise SystemExit(main())
