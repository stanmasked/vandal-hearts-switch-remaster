#!/usr/bin/env python3
"""Offline audit of bounded *native PC GPU* event/snapshot recorder files.

No authentic input files are bundled. Checks event order, before/after pairs,
frame labels, source-window metadata, upload names and all full-size VRAM
snapshots. Returns only count and hashes, not screenshots or game bytes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from tools.verify_map02_frame_bundle import fields, number, parse_json
from tools.verify_map02_vram_timeline import VRAM_BYTES

LOG = "gpu-native-events.jsonl"
STATUS = "gpu-native-capture-status.json"
STATUS_SCHEMA = "vh.map02.native-capture-status.v1"
MAX_RECORDS = 64
MAX_EVENT_BYTES = 128 * 1024


def private_file(root: Path, name: str, *, expected=None, max_bytes=None,
                 _with_identity=False):
    """Double-read a bounded native GPU input from a pinned regular inode.

    The recorder may be audited after a private process exits; refuse links,
    FIFOs, inode replacement and mid-read changes before using any bytes.
    """
    if (type(name) is not str or not name or
            name in (".", "..") or "/" in name or "\\" in name):
        raise ValueError("invalid native GPU input name")
    path = root / name
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) |
             getattr(os, "O_NOFOLLOW", 0) |
             getattr(os, "O_NONBLOCK", 0))
    try:
        fd = os.open(path, flags)
    except OSError:
        raise ValueError(f"{name}: missing, symlinked or non-regular file") from None
    try:
        def identity(st):
            return (st.st_dev, st.st_ino, st.st_uid, st.st_mode,
                    st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns)

        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or
                before.st_uid != os.geteuid() or before.st_nlink != 1):
            raise ValueError(f"{name}: missing, symlinked or non-regular file")
        size = before.st_size
        if expected is not None and size != expected:
            raise ValueError(f"{name}: wrong file size")
        if max_bytes is not None and (size < 1 or size > max_bytes):
            raise ValueError(f"{name}: over size limit or empty")
        first = os.pread(fd, size, 0)
        second = os.pread(fd, size, 0)
        if (len(first) != size or first != second or
                identity(os.fstat(fd)) != identity(before) or
                identity(os.stat(path, follow_symlinks=False)) !=
                identity(before)):
            raise ValueError(f"{name}: input changed during private read")
        return (first, identity(before)) if _with_identity else first
    except OSError:
        raise ValueError(f"{name}: private input verification unavailable") from None
    finally:
        os.close(fd)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_meta(event, step, target_frame):
    fields(event, ("stage","step","frame","phase","operation","snapshot",
                   "rect","dest","rgb","primitive_type","semi","window",
                   "draw_mode","upload","ft4"), f"event {step}",
           optional=("draw_env",))
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
    # The optional DRAWENV snapshot is written by the opt-in native probe.
    # Older captures stay readable but cannot prove drawing-area clipping.
    # clip is [x,y,width,height], with 16-bit signed offsets [ofsX,ofsY].
    if "draw_env" in event:
        draw_env=event["draw_env"]
        if type(draw_env) is not list or len(draw_env)!=6:
            raise ValueError("DRAWENV: expected six integers")
        for i,value in enumerate(draw_env):
            number(value, "DRAWENV", -32768 if i in (0,1,4,5) else 0,
                   65535 if i in (2,3) else 32767)
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



def verify_capture_receipt(directory: Path, *, target_frame: int, events):
    """Require an exclusive recorder terminal receipt; old captures are not
    automatically treated as complete. This is a consistency check only."""
    directory = Path(directory).absolute()
    raw = private_file(directory, STATUS, max_bytes=4096)
    status = parse_json(raw, STATUS)
    fields(status, (
        "schema", "gpu_draw_frame", "observed_hooks",
        "before_hooks", "after_hooks", "draw_before_hooks",
        "transfer_before_hooks", "indexed_hooks", "written_hooks",
        "limit_reached", "walk_finished", "hooks_balanced",
        "observed_window_closed_without_detected_loss",
    ), STATUS)
    if status["schema"] != STATUS_SCHEMA:
        raise ValueError("unsupported native GPU capture status schema")
    if number(status["gpu_draw_frame"], "receipt frame", 1, 2**32-1) != target_frame:
        raise ValueError("native GPU receipt frame mismatch")
    counts = {}
    for name in ("observed_hooks", "before_hooks", "after_hooks",
                 "draw_before_hooks", "transfer_before_hooks",
                 "indexed_hooks", "written_hooks"):
        counts[name] = number(status[name], "receipt " + name, 0, 2**32-1)
    for key in ("limit_reached", "walk_finished", "hooks_balanced",
                "observed_window_closed_without_detected_loss"):
        if type(status[key]) is not bool:
            raise ValueError("native GPU receipt flag must be boolean")
    if type(events) is not list or len(events) % 2:
        raise ValueError("invalid native GPU event list for receipt")
    pairs = len(events) // 2
    draws = sum(e["operation"] == "draw" for e in events[::2])
    transfers = pairs - draws
    if (counts["observed_hooks"] !=
            counts["before_hooks"] + counts["after_hooks"] or
            counts["draw_before_hooks"] +
            counts["transfer_before_hooks"] != counts["before_hooks"] or
            counts["draw_before_hooks"] != draws or
            counts["transfer_before_hooks"] != transfers or
            counts["before_hooks"] != pairs or
            counts["after_hooks"] != pairs or
            counts["indexed_hooks"] != len(events) or
            counts["written_hooks"] != len(events)):
        raise ValueError("native GPU receipt count/log divergence")
    if (len(events) >= MAX_RECORDS or status["limit_reached"] or
            not status["walk_finished"] or not status["hooks_balanced"] or
            not status["observed_window_closed_without_detected_loss"]):
        raise ValueError("native GPU capture incomplete: cap, failed hooks or OT walk")
    return {
        "capture_receipt_supplied": True,
        "native_gpu_event_hooks_accounted": counts["observed_hooks"],
        "native_gpu_draw_pairs_accounted": draws,
        "capture_window_closed_without_detected_loss": True,
        "full_original_gameplay_frame_proven": False,
    }

def verify_capture(directory: Path, *, target_frame: int):
    directory = Path(directory).absolute()
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("capture directory is missing or is a symlink")
    number(target_frame,"target DrawOTag frame",1,2**32-1)
    # Track both complete bytes and the precise inode used by the audit.
    # Checks inside private_file alone cannot detect replacement after
    # one capture file was audited but before the final positive report.
    evidence={}

    def read_evidence(name, *, expected=None, max_bytes=None):
        raw, identity = private_file(
            directory, name, expected=expected, max_bytes=max_bytes,
            _with_identity=True)
        token=(sha(raw), identity, expected, max_bytes)
        if name in evidence and evidence[name] != token:
            raise ValueError("native GPU evidence changed between audit passes")
        evidence[name]=token
        return raw

    log_raw=read_evidence(LOG,max_bytes=MAX_EVENT_BYTES)
    # Recorder events are newline-terminated JSONL. splitlines() silently
    # accepted a missing final LF and alternative line separators, making
    # a truncated event log appear complete when its JSON remained valid.
    if not log_raw.endswith(b"\n") or b"\r" in log_raw:
        raise ValueError("incomplete or noncanonical native GPU event stream")
    lines=log_raw.split(b"\n")[:-1]
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
                    "semi","ft4","draw_env"):
            if before.get(key)!=after.get(key):
                raise ValueError(f"GPU event {i}: before/after metadata diverges ({key})")
        a=read_evidence(before["snapshot"],expected=VRAM_BYTES)
        b=read_evidence(after["snapshot"],expected=VRAM_BYTES)
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
                    read_evidence(upload,expected=area*2)
            elif kind=="move":
                moves+=1
            elif kind=="clear":
                clears+=1
    # Legacy captures may lack the new terminal receipt. They remain
    # analyzable but are NEVER treated as proven complete. If a receipt is
    # supplied, it must agree with every observed native GPU event and cap.
    status_path = directory / STATUS
    if status_path.exists() or status_path.is_symlink():
        read_evidence(STATUS,max_bytes=4096)
        status_report = verify_capture_receipt(
            directory, target_frame=target_frame, events=events)
    else:
        status_report = {
            "capture_receipt_supplied": False,
            "capture_window_closed_without_detected_loss": False,
            "full_original_gameplay_frame_proven": False,
        }
    # Re-open every manifest, event stream, VRAM snapshot and upload. Hashes
    # and inode/metadata must match the exact files used for the result.
    for name,(digest,identity,expected,max_bytes) in evidence.items():
        rechecked,latest = private_file(
            directory,name,expected=expected,max_bytes=max_bytes,
            _with_identity=True)
        if sha(rechecked)!=digest or latest!=identity:
            raise ValueError("native GPU evidence changed during full audit")
    return {
        **status_report,
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
