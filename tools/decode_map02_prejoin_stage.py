#!/usr/bin/env python3
"""Decode opt-in atomic pre-join guest stage panel; not a service stall proof."""
import argparse
import json
from pathlib import Path

from PIL import Image

SIZE=(1280,720)
BORDER=(244,154,92,112)
LEFT,TOP,STEP=250,160,10

def decode_image(path):
    with Image.open(path) as fp:
        if fp.format!="PNG" or fp.size!=SIZE:
            raise ValueError("Expected real 1280x720 NeXium PNG")
        im=fp.convert("RGB")
    pixels=im.load()
    for x,y in ((244,154),(334,154),(244,264),(334,264)):
        color=pixels[x,y]
        if not (color[0]>=200 and color[1]<=45 and color[2]>=200):
            raise ValueError("Missing pre-join magenta stage panel")
    values=[]
    for row in range(10):
        value=0
        for bit in range(8):
            r,g,b=pixels[LEFT+10*bit+4,TOP+10*row+4]
            if max(r,g,b)<=48:
                continue
            if min(r,g,b)>=208:
                value|=1<<bit
            else:
                raise ValueError("Invalid stage panel bit module")
        values.append(value)
    if values[:2]!=[0xa5,0x5a] or (values[8]^0xc3)!=values[9]:
        raise ValueError("Invalid pre-join panel signature or checksum")
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
