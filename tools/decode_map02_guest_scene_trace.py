#!/usr/bin/env python3
"""Decode post-join NeXium scene trace optical witness; no guest files."""
import argparse
import json
import struct
import zlib
from pathlib import Path

from PIL import Image

WIDTH, HEIGHT = 1280, 720
LEFT, TOP, MODULE = 250, 160, 7
COLS, ROWS = 112, 66
PACKET_BYTES = 924
KINDS = {1:"INPUT",2:"POST",3:"ACCEPT",4:"SUBMIT_CALL",
         5:"RELEASE_RETURN",6:"SUBMIT_ERROR",
         7:"PCM_PAGE_NONZERO",8:"PCM_PAGE_SILENT"}


def decode_packet_image(path):
    img = Image.open(path).convert("RGB")
    if img.size != (WIDTH, HEIGHT):
        raise ValueError("Unexpected NeXium screenshot geometry")
    # NeXium's host window may letterbox/scale the Switch framebuffer.
    # Calibrate using our full magenta border, never hard-code viewport
    # pixels or perform OCR/image guessing. The recorded packet's CRC
    # still has to match the exact decoded bits.
    magenta = []
    for index, (red, green, blue) in enumerate(img.getdata()):
        if red >= 200 and green <= 45 and blue >= 200:
            magenta.append((index % WIDTH, index // WIDTH))
    if len(magenta) < 4000:
        raise ValueError("Missing magenta trace receipt border")
    left = min(p[0] for p in magenta)
    right = max(p[0] for p in magenta)
    top = min(p[1] for p in magenta)
    bottom = max(p[1] for p in magenta)
    width = right-left+1
    height = bottom-top+1
    if not (740 <= width <= 810 and 440 <= height <= 490):
        raise ValueError("Unexpected calibrated trace viewport geometry")
    packed = bytearray(PACKET_BYTES)
    for bit in range(PACKET_BYTES * 8):
        col, row = bit % COLS, bit // COLS
        px = round(left + (col + 1.5)*width/(COLS + 2))
        py = round(top + (row + 1.5)*height/(ROWS + 2))
        color = img.getpixel((px, py))
        if max(color) <= 48:
            packed[bit//8] |= 0x80 >> (bit%8)
        elif min(color) < 208:
            raise ValueError("Invalid optical module color")
    return bytes(packed)


def decode_image(path):
    return unpack(decode_packet_image(path))


def unpack(packet):
    if len(packet) != PACKET_BYTES or packet[:8] != b"VHFBTRC1":
        raise ValueError("Corrupt trace packet signature/size")
    count = packet[8]
    dropped, = struct.unpack_from("<I",packet,9)
    if count > 64:
        raise ValueError("Overflowed optical trace row count")
    crc, = struct.unpack_from("<I",packet,909)
    if zlib.crc32(packet[:909]) != crc:
        raise ValueError("Bad optical witness CRC32")
    if any(packet[913:]) or any(packet[13+count*14:909]):
        raise ValueError("Nonzero reserved or unused optical bytes")
    rows = []
    for n in range(count):
        off=13+n*14
        kind,scene,serial,clock=struct.unpack_from("<BBIQ",packet,off)
        if kind not in KINDS or scene not in (0,1,2) or not clock:
            raise ValueError("Invalid scene trace row")
        rows.append({"index":n,"event":KINDS[kind],"scene":scene,
                     "serial":serial,"guest_monotonic_ns":clock})
    return {"rows":rows,"dropped":dropped}


def audit_receipt(decoded, mode):
    rows = decoded["rows"]
    if decoded["dropped"] or len(rows) < 5:
        raise ValueError("Incomplete guest trace / unexpected lost slots")
    if any(x["event"]=="SUBMIT_ERROR" for x in rows):
        raise ValueError("Guest audio page submission failed")
    if any(x["event"]=="PCM_PAGE_SILENT" and
           x["serial"] in (1,2) for x in rows):
        raise ValueError("First accepted guest PCM page was silent")
    details=[]
    # One real A-selection then one real B-cancel. Avoid searching by
    # mere event kind across different ticket IDs.
    for serial,scene in ((1,2),(2,1)):
        relevant=[x for x in rows if x["serial"]==serial]
        required=("INPUT","POST","ACCEPT","PCM_PAGE_NONZERO",
                  "SUBMIT_CALL","RELEASE_RETURN")
        order=[]
        prior=-1
        for kind in required:
            candidates=[x for x in relevant if x["event"]==kind and
                        x["scene"]==scene and x["index"]>prior]
            if not candidates:
                raise ValueError(f"Missing {kind} for game scene {scene} ticket {serial}")
            event=candidates[0]
            prior=event["index"]
            order.append(event)
        if any(order[i]["guest_monotonic_ns"]>order[i+1]["guest_monotonic_ns"]
               for i in range(len(order)-1)):
            raise ValueError("Nonmonotonic guest input-to-PCM time")
        details.append({"serial":serial,"scene":scene,
                        "events":[x["event"] for x in order],
                        "indices":[x["index"] for x in order],
                        "last_return_monotonic_ns":order[-1]["guest_monotonic_ns"]})
    return {"schema":"vh-map02-guest-scene-trace/v1",
            "mode":mode,"trace_rows":len(rows),"trace_dropped":0,
            "confirmed_transitions":details,
            "result":"FIRST_PCM_PAGE_NONZERO_AND_SUBMITTED",
            "first_pre_submit_pcm_page_nonzero_verified":True,
            "audout_submit_returned_for_first_page":True,
            "sample_aligned_guest_reverb_proven":False,
            "physical_speaker_tested":False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image",type=Path,required=True)
    parser.add_argument("--mode",type=int,choices=(0,1),required=True)
    parser.add_argument("--output",type=Path,required=True)
    opts=parser.parse_args()
    try:
        result=audit_receipt(decode_image(opts.image),opts.mode)
    except (OSError,ValueError,TypeError) as exc:
        result={"schema":"vh-map02-guest-scene-trace/v1","mode":opts.mode,
                "result":"GUEST_TRACE_UNVERIFIED","reason":str(exc),
                "sample_aligned_guest_reverb_proven":False,
                "physical_speaker_tested":False}
    opts.output.parent.mkdir(parents=True,exist_ok=True)
    opts.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result["result"]=="FIRST_PCM_PAGE_NONZERO_AND_SUBMITTED" else 1

if __name__=="__main__":
    raise SystemExit(main())
