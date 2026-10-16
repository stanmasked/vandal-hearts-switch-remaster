#!/usr/bin/env python3
"""Offline audit of bounded *native PC GPU* event/snapshot recorder files.

No authentic input files are bundled. Checks event order, before/after pairs,
frame labels, source-window metadata, upload names and all full-size VRAM
snapshots. Returns only count and hashes, not screenshots or game bytes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat

from tools.verify_map02_frame_bundle import fields, number, parse_json
from tools.verify_map02_vram_timeline import VRAM_BYTES

LOG = "gpu-native-events.jsonl"
MAX_RECORDS = 64
MAX_EVENT_BYTES = 128 * 1024


def private_file(root: Path, name: str, *, expected=None, max_bytes=None):
    path = root / name
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"{name}: missing, symlinked or non-regular file")
    size = path.stat().st_size
    if expected is not None and size != expected:
        raise ValueError(f"{name}: wrong file size")
    if max_bytes is not None and (size < 1 or size > max_bytes):
        raise ValueError(f"{name}: over size limit or empty")
    return path.read_bytes()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_meta(event, step, target_frame):
    fields(event, ("stage","step","frame","phase","operation","snapshot",
                   "rect","dest","rgb","primitive_type","semi","window",
                   "draw_mode","upload","ft4"), f"event {step}")
    if event["stage"] != "native_vram":
        raise ValueError("not a native PC GPU VRAM event")
    if number(event["step"],"event step",0,MAX_RECORDS-1) != step:
        raise ValueError("not a contiguous recorded event sequence")
    if event["phase"] != ("before" if step%2 == 0 else "after"):
        raise ValueError("missing or inverted before/after capture")
    op=event["operation"]
    if op not in ("load","move","clear","draw"):
        raise ValueError("unrecognized original GPU operation")
    expected_frame = target_frame if op=="draw" else target_frame-1
    if number(event["frame"],"DrawOTag frame",0,2**32-1) != expected_frame:
        raise ValueError("operation belongs to a different native GPU frame")
    if event["snapshot"] != f"gpu-{step:04d}-vram.bin":
        raise ValueError("VRAM snapshot name/index does not match event")
    number(event["primitive_type"],"primitive type",0,255)
    number(event["semi"],"semi",0,1)
    for name,length,lo,hi in (
        ("dest",2,-32768,32767), ("rgb",3,0,255),
        ("window",4,0,31), ("draw_mode",3,0,65535)):
        data=event[name]
        if type(data) is not list or len(data)!=length:
            raise ValueError(f"{name}: wrong field shape")
        for value in data:
            number(value,name,lo,hi)
    rect=event["rect"]
    if op=="draw":
        if rect is not None or event["upload"]:
            raise ValueError("DrawOTag primitive may not contain a transfer RECT/upload")
        q=event["ft4"]
        if q is not None:
            fields(q,("tpage","clut","xy","uv"),"FT4 packet")
            number(q["tpage"],"tpage",0,65535)
            number(q["clut"],"clut",0,65535)
            for name,size,lo,hi in (("xy",8,-32768,32767),("uv",8,0,255)):
                arr=q[name]
                if type(arr) is not list or len(arr)!=size:
                    raise ValueError("invalid FT4 GPU vertex array")
                for value in arr:
                    number(value,name,lo,hi)
    else:
        if event["ft4"] is not None or type(rect) is not list or len(rect)!=4:
            raise ValueError("transfer requires RECT, not an FT4 packet")
        for value in rect[:2]:
            number(value,"rectangle origin",-32768,32767)
        for value in rect[2:]:
            number(value,"rectangle extent",-32768,32767)
        if op!="load" and event["upload"]:
            raise ValueError("only LoadImage can contain an upload")
        if op=="load" and event["upload"] not in ("",f"gpu-{step:04d}-upload.bin"):
            raise ValueError("unexpected upload filename")


def verify_capture(directory: Path, *, target_frame: int):
    directory = Path(directory).absolute()
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("capture directory is missing or is a symlink")
    number(target_frame,"target DrawOTag frame",1,2**32-1)
    log_raw=private_file(directory,LOG,max_bytes=MAX_EVENT_BYTES)
    lines=log_raw.splitlines()
    if (len(lines)<2 or len(lines)>MAX_RECORDS or len(lines)%2 or
            any(not line.strip() for line in lines)):
        raise ValueError("incomplete, blank or oversized native GPU event stream")
    events=[parse_json(line,f"native event {i}") for i,line in enumerate(lines)]
    pairs=0;draws=loads=moves=clears=0
    assignments=0;draw_changed_words=transfer_changed_words=0
    snapshot_hashes=[]
    for i in range(0,len(events),2):
        before,after=events[i:i+2]
        validate_meta(before,i,target_frame)
        validate_meta(after,i+1,target_frame)
        for key in ("frame","operation","rect","dest","rgb","primitive_type",
                    "semi","ft4"):
            if before[key]!=after[key]:
                raise ValueError(f"GPU event {i}: before/after metadata diverges ({key})")
        a=private_file(directory,before["snapshot"],expected=VRAM_BYTES)
        b=private_file(directory,after["snapshot"],expected=VRAM_BYTES)
        snapshot_hashes.extend((sha(a),sha(b)))
        changed=sum(a[j:j+2]!=b[j:j+2] for j in range(0,VRAM_BYTES,2))
        assignments+=changed
        pairs+=1
        kind=before["operation"]
        if kind=="draw":
            draws+=1
            draw_changed_words+=changed
        else:
            transfer_changed_words+=changed
            if kind=="load":
                loads+=1
                # A bounded original upload is only present for the
                # second (post-LoadImage) record, and may be omitted by
                # the source recorder for >16384-word transfers.
                upload=after["upload"]
                if upload:
                    rect=after["rect"]
                    area=rect[2]*rect[3]
                    if not 0<area<=16384:
                        raise ValueError("LoadImage payload exists for invalid/oversized rectangle")
                    private_file(directory,upload,expected=area*2)
            elif kind=="move":
                moves+=1
            elif kind=="clear":
                clears+=1
    return {
        "native_gpu_events_sha256":sha(log_raw),
        "vram_snapshot_sha256_list_sha256":sha("".join(snapshot_hashes).encode("ascii")),
        "frame":target_frame,
        "native_gpu_pairs_verified":pairs,
        "draw_otag_primitive_pairs":draws,
        "load_image_pairs":loads,
        "move_image_pairs":moves,
        "clear_image_pairs":clears,
        "changed_vram_words_across_event_pairs":assignments,
        "changed_native_draw_vram_words":draw_changed_words,
        "changed_transfer_vram_words":transfer_changed_words,
        "record_cap_reached":len(events)==MAX_RECORDS,
        "real_gameplay_authenticated":False,
        "gpu_write_stream_complete":False,
        "source_keyed_map02_faces_matched":False,
        "ps1_hardware_pixels_verified":False,
        "game_bytes_in_report":False,
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_directory",type=Path)
    p.add_argument("--frame",type=int,required=True)
    args=p.parse_args()
    try:
        report=verify_capture(args.private_directory,target_frame=args.frame)
    except (ValueError,OSError) as exc:
        p.error(str(exc))
    print(json.dumps(report,sort_keys=True,indent=2))

if __name__=="__main__":
    main()
