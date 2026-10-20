#!/usr/bin/env python3
"""Decode opt-in atomic pre-join guest stage panel; not a service stall proof."""
import argparse
import json
from pathlib import Path

from PIL import Image

SIZE=(1280,720)
BORDER=(244,154,92,112)
LEFT,TOP,STEP=250,160,10

def crc8_atm(data):
    """CRC-8/ATM: polynomial 0x07, init 0, no reflection or final XOR."""
    value=0
    for byte in data:
        value^=byte
        for _ in range(8):
            value=((value<<1)^0x07)&0xff if value&0x80 else (value<<1)&0xff
    return value

def decode_image(path):
    with Image.open(path) as fp:
        if fp.format!="PNG" or fp.size!=SIZE:
            raise ValueError("Expected real 1280x720 NeXium PNG")
        im=fp.convert("RGB")
    # NeXium can letterbox or scale the guest framebuffer. Calibrate
    # from the magenta border actually rendered in this screenshot,
    # then sample module centers relative to those real pixel bounds.
    magenta=[]
    for i,(red,green,blue) in enumerate(im.getdata()):
        if red>=200 and green<=45 and blue>=200:
            magenta.append((i%SIZE[0],i//SIZE[0]))
    if len(magenta)<200:
        raise ValueError("Missing pre-join magenta stage panel")
    left=min(x for x,_ in magenta)
    right=max(x for x,_ in magenta)
    top=min(y for _,y in magenta)
    bottom=max(y for _,y in magenta)
    width=right-left+1
    height=bottom-top+1
    if not (68<=width<=118 and 88<=height<=145):
        raise ValueError("Unexpected calibrated pre-join panel geometry")
    pixels=im.load()
    values=[]
    for row in range(10):
        value=0
        for bit in range(8):
            px=round(left+(10+10*bit)*width/BORDER[2])
            py=round(top+(10+10*row)*height/BORDER[3])
            r,g,b=pixels[px,py]
            if max(r,g,b)<=48:
                continue
            if min(r,g,b)>=208:
                value|=1<<bit
            else:
                raise ValueError("Invalid stage panel bit module")
        values.append(value)
    if values[:2]!=[0xa5,0x5a]:
        raise ValueError("Invalid pre-join panel signature")
    if values[9]!=crc8_atm(values[:8]):
        raise ValueError("Pre-join panel CRC-8 checksum mismatch")
    calc=0
    for v in values[:8]:calc^=v
    if calc!=values[8]:
        raise ValueError("Pre-join panel checksum mismatch")
    stage,entered,returned,stop=values[2],values[3]|(values[4]<<8),values[5]|(values[6]<<8),values[7]
    if stage>6 or returned>entered or stop not in (0,1):
        raise ValueError("Invalid atomic guest phase or counters")
    return {"schema":"vh-map02-audout-prejoin-stage/v1",
            "result":"PREJOIN_STAGE_SNAPSHOT_CAPTURED",
            "stage":stage,
            "stage_name":("NOT_STARTED","WORKER_ENTERED","AUDOUT_INITIALIZED",
                          "ENTERED_PLAYBUFFER","RETURNED_FROM_PLAYBUFFER",
                          "CLEANUP_STARTED","CLEANUP_COMPLETED")[stage],
            "audout_playbuffer_call_entries":entered,
            "audout_playbuffer_call_returns":returned,
            "cooperative_stop_requested":bool(stop),
            "snapshot_before_blocking_thread_join":True,
            "audout_service_stall_proven":False,
            "audio_worker_deadlock_proven":False,
            "physical_switch_speaker_output_verified":False}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    try:
        result=decode_image(a.image)
    except (OSError,ValueError,TypeError) as exc:
        result={"schema":"vh-map02-audout-prejoin-stage/v1",
                "result":"PREJOIN_STAGE_UNVERIFIED","reason":str(exc),
                "audout_service_stall_proven":False,
                "audio_worker_deadlock_proven":False}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result["result"]=="PREJOIN_STAGE_SNAPSHOT_CAPTURED" else 1

if __name__=="__main__":
    raise SystemExit(main())
