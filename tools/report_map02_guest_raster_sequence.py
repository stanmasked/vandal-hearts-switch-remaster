#!/usr/bin/env python3
"""Read-only compare three actual NeXium GUI captures, excluding GUI chrome.

Changes in a static scene DO NOT prove guest liveness; a static late frame
does NOT prove a deadlocked audout call. The independent VHPRE001 decoder
remains the only valid eight-page guest optical proof.
"""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageStat

CANVAS=(1280,720)
# Deliberately excludes most emulator status text. This geometry is a
# calibrated diagnostics-only rectangular ROI, not the full guest image.
ROI=(250,160,1180,690)
MAX_PNG_BYTES=16*1024*1024

def open_frame(p):
    if p.stat().st_size>MAX_PNG_BYTES:
        raise ValueError("oversized captured PNG")
    with Image.open(p) as original:
        if original.format!="PNG" or original.size!=CANVAS:
            raise ValueError("expected real 1280x720 NeXium PNG")
        return original.convert("RGB")

def rgb_sha256(im):
    return hashlib.sha256(im.tobytes()).hexdigest()

def compare(a,b):
    a_roi=a.crop(ROI);b_roi=b.crop(ROI)
    diff=ImageChops.difference(a_roi,b_roi)
    # Per-pixel nonzero in ANY RGB channel, not sum of absolute values.
    changed=sum(px!=(0,0,0) for px in diff.getdata())
    return {"changed_rgb_pixels":changed,
            "total_roi_pixels":(ROI[2]-ROI[0])*(ROI[3]-ROI[1]),
            "changed_fraction":round(changed/((ROI[2]-ROI[0])*(ROI[3]-ROI[1])),8),
            "diff_bbox_within_roi":list(diff.getbbox()) if diff.getbbox() else None}

def audit(before,final,late):
    imgs=[before,final,late]
    if any(im.mode!="RGB" or im.size!=CANVAS for im in imgs):
        raise ValueError("all images must be 1280x720 RGB captures")
    return {
       "schema":"vh-map02-optin-guest-raster-observation/v1",
       "frame_dimensions":list(CANVAS),
       "game_content_roi_xyxy":list(ROI),
       "before_roi_rgb_sha256":rgb_sha256(before.crop(ROI)),
       "final_roi_rgb_sha256":rgb_sha256(final.crop(ROI)),
       "late_roi_rgb_sha256":rgb_sha256(late.crop(ROI)),
       "before_to_final":compare(before,final),
       "final_to_late":compare(final,late),
       "actual_guest_audio_thread_progress_proven":False,
       "audout_call_deadlock_proven":False,
       "neXium_guest_optical_receipt_verified":False,
       "physical_switch_audio_proven":False,
       "interpretation":"Pure screenshot difference; static frames may result from scene state, rendering or thread scheduling. See independent VHPRE001."
    }

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--before",type=Path,required=True)
    ap.add_argument("--final",type=Path,required=True)
    ap.add_argument("--late",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    opts=ap.parse_args()
    try:
        result=audit(open_frame(opts.before),open_frame(opts.final),open_frame(opts.late))
    except (OSError,ValueError) as error:
        result={"schema":"vh-map02-optin-guest-raster-observation/v1",
                "result":"GUEST_RASTER_UNVERIFIED","reason":str(error),
                "actual_guest_audio_thread_progress_proven":False,
                "audout_call_deadlock_proven":False,
                "neXium_guest_optical_receipt_verified":False}
    opts.output.parent.mkdir(parents=True,exist_ok=True)
    opts.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps(result,sort_keys=True,indent=2))
    return int(result.get("result")=="GUEST_RASTER_UNVERIFIED")

if __name__=="__main__":
    raise SystemExit(main())
