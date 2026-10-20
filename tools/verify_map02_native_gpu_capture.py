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
STATUS = "gpu-native-capture-status.json"
STATUS_SCHEMA = "vh.map02.native-capture-status.v1"
MAX_RECORDS = 64
MAX_EVENT_BYTES = 128 * 1024
# Exact pinned platform/pc/include/PsyQ/libgpu.h PC_GPU_PRIM_POLY_FT4.
PRIM_POLY_FT4 = 2
VRAM_WIDTH = 1024
VRAM_HEIGHT = 512


def validate_clear_vram(before, after, rect, rgb):
    """Verify pinned pc_raster.c FillRectRaw native BGR555 overwrite.

    ClearImage calls FillRectRaw, which packs 8-bit RGB with >>3 (no
    bit15, dither, blending, mask test, or drawing-area clipping).
    Fill only the intersection with the 1024x512 native VRAM.
    """
    rx, ry, width, height = rect
    red, green, blue = rgb
    packed = ((blue >> 3) << 10) | ((green >> 3) << 5) | (red >> 3)
    pixel = packed.to_bytes(2, "little")
    x0 = max(0, rx)
    y0 = max(0, ry)
    x1 = min(VRAM_WIDTH, rx + width)
    y1 = min(VRAM_HEIGHT, ry + height)
    expected = bytearray(before)
    if x0 < x1 and y0 < y1:
        row = pixel * (x1 - x0)
        for y in range(y0, y1):
            offset = (y * VRAM_WIDTH + x0) * 2
            expected[offset:offset + len(row)] = row
    if expected != after:
        raise ValueError("ClearImage post-VRAM differs from source BGR555 raw fill")


def validate_move_vram(before, after, rect, dest):
    """Replay original PC MoveImage's forward in-place 16-bit VRAM writes.

    The source implementation iterates j then i, and each read observes
    earlier writes. A slice copy or memmove would be incorrect for overlap.
    Skipped offscreen source/destination pixels must remain untouched.
    """
    rx, ry, width, height = rect
    dx, dy = dest
    # Only the i/j values with both source and destination inside VRAM can
    # change memory. This range intersection is equivalent to the pinned
    # C per-pixel bounds guards and avoids unbounded work on wild RECTs.
    i0 = max(0, -rx, -dx)
    i1 = min(width, VRAM_WIDTH - rx, VRAM_WIDTH - dx)
    j0 = max(0, -ry, -dy)
    j1 = min(height, VRAM_HEIGHT - ry, VRAM_HEIGHT - dy)
    expected = bytearray(before)
    if i0 < i1 and j0 < j1:
        for j in range(j0, j1):
            source_row = (ry + j) * VRAM_WIDTH
            dest_row = (dy + j) * VRAM_WIDTH
            for i in range(i0, i1):
                source_offset = (source_row + rx + i) * 2
                dest_offset = (dest_row + dx + i) * 2
                # Read from current mutable memory, not the BEFORE bytes.
                expected[dest_offset:dest_offset + 2] = (
                    expected[source_offset:source_offset + 2]
                )
    if expected != after:
        raise ValueError("MoveImage post-VRAM differs from source-ordered in-place copy")


def validate_bounded_load_vram(before, after, payload, rect):
    """Mirror the pinned original PC LoadImage rectangle clip + BGR555 copy.

    Source: platform/pc/src/libgpu.c at upstream 14552fff. This checker
    uses the post-LanguagePatch raw source words saved by the C recorder,
    not a recreated texture or a projected/HD framebuffer.
    """
    rx, ry, width, height = rect
    if not (1 <= width <= 128 and 1 <= height <= 128):
        raise ValueError("bounded LoadImage validation requires source hook dimensions")
    if len(payload) != 2 * width * height:
        raise ValueError("bounded LoadImage payload size disagrees with RECT")
    # Exact original loop: x0=max(-rect.x,0), x1=min(w,VRAM_W-rect.x)
    # and the analogous y limits. Entire outside-VRAM copy is a no-op.
    x0 = max(-rx, 0)
    y0 = max(-ry, 0)
    x1 = min(width, VRAM_WIDTH - rx)
    y1 = min(height, VRAM_HEIGHT - ry)
    expected = bytearray(before)
    if x0 < x1 and y0 < y1:
        row_size = (x1 - x0) * 2
        for y in range(y0, y1):
            source_offset = (y * width + x0) * 2
            dest_offset = ((ry + y) * VRAM_WIDTH + (rx + x0)) * 2
            expected[dest_offset:dest_offset + row_size] = (
                payload[source_offset:source_offset + row_size]
            )
    if expected != after:
        raise ValueError("bounded LoadImage post-VRAM differs from native source pixel copy")



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
    if op!="draw" and event["primitive_type"] != 0:
        raise ValueError("native transfer cannot claim a DrawOTag primitive type")
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
        # VH_CaptureEvent receives a POLY_FT4 pointer iff the packet
        # type equals the source-pinned PC_GPU_PRIM_POLY_FT4 constant.
        if (q is None) == (event["primitive_type"] == PRIM_POLY_FT4):
            raise ValueError("FT4 payload presence disagrees with native primitive type")
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
    log_raw=private_file(directory,LOG,max_bytes=MAX_EVENT_BYTES)
    # This binary-mode original observer always ends each JSON record in
    # one LF. Do not normalize CRLF or accept an interrupted final line.
    if not log_raw.endswith(b"\n") or b"\r" in log_raw or b"\x00" in log_raw:
        raise ValueError("noncanonical native GPU JSONL line boundaries")
    lines=log_raw.split(b"\n")[:-1]
    if (len(lines)<2 or len(lines)>MAX_RECORDS or len(lines)%2 or
            any(not line.strip() for line in lines)):
        raise ValueError("incomplete, blank or oversized native GPU event stream")
    events=[parse_json(line,f"native event {i}") for i,line in enumerate(lines)]
    pairs=0;draws=loads=moves=clears=0
    assignments=0;draw_changed_words=transfer_changed_words=0
    snapshot_hashes=[]
    upload_hashes=[]
    load_pairs_without_payload=0
    move_pairs_with_verified_vram_effect=0
    clear_pairs_with_verified_vram_effect=0
    draw_boundary_vram_checks=0
    draw_boundary_gpu_state_checks=0
    previous_draw_post=None
    previous_draw_gpu_state=None
    previous_draw_env=None
    entered_target_draw_frame=False
    for i in range(0,len(events),2):
        before,after=events[i:i+2]
        validate_meta(before,i,target_frame)
        validate_meta(after,i+1,target_frame)
        for key in ("frame","operation","rect","dest","rgb","primitive_type",
                    "semi","ft4"):
            if before[key]!=after[key]:
                raise ValueError(f"GPU event {i}: before/after metadata diverges ({key})")
        # DRAWENV is optional in old original-PC native journals. Its
        # presence and six-number bounds were checked by validate_meta;
        # a one-sided capture must still fail, but absent on both sides
        # must not trigger KeyError or falsely assert clip provenance.
        if before.get("draw_env") != after.get("draw_env"):
            raise ValueError(f"GPU event {i}: before/after metadata diverges (draw_env)")
        a=private_file(directory,before["snapshot"],expected=VRAM_BYTES)
        b=private_file(directory,after["snapshot"],expected=VRAM_BYTES)
        snapshot_hashes.extend((sha(a),sha(b)))
        changed=sum(a[j:j+2]!=b[j:j+2] for j in range(0,VRAM_BYTES,2))
        assignments+=changed
        pairs+=1
        kind=before["operation"]
        # The actual C capture predicate records GPU transfers only while
        # s_drawFrame + 1 == target_frame, and primitives only once
        # s_drawFrame == target_frame. A transfer after a captured DrawOTag
        # primitive would reverse those mutually exclusive frame phases.
        if kind=="draw":
            entered_target_draw_frame=True
        elif entered_target_draw_frame:
            raise ValueError("native GPU transfer appears after target DrawOTag began")
        if kind=="draw":
            # A single source-pinned DrawOTag walk visits each primitive in
            # sequence, without an unobserved native GPU command between
            # its registered callbacks. The recorder samples its before/
            # after VRAM immediately around each primitive's switch.
            # Do NOT apply this across preframe transfers: an uncaptured
            # earlier DrawOTag may modify VRAM between those calls.
            if previous_draw_post is not None:
                if a != previous_draw_post:
                    raise ValueError("adjacent DrawOTag primitives have discontinuous VRAM")
                draw_boundary_vram_checks+=1
                state=(before["window"],before["draw_mode"])
                if state != previous_draw_gpu_state:
                    raise ValueError("adjacent DrawOTag primitives have discontinuous GPU state")
                draw_boundary_gpu_state_checks+=1
                # DRAWENV is optional in legacy recordings; compare both
                # presence and content so a later draw cannot silently
                # acquire, drop or change clip/offset metadata.
                if before.get("draw_env") != previous_draw_env:
                    raise ValueError("adjacent DrawOTag primitives have discontinuous DRAWENV")
            # Only DR_MODE (source-pinned primitive type 5) can change
            # the captured draw mode or texture-window globals during
            # the native primitive dispatch. Ordinary FT4/TILE/etc must
            # preserve them across the before/after snapshots.
            if before["primitive_type"] != 5 and (
                    before["window"] != after["window"]
                    or before["draw_mode"] != after["draw_mode"]):
                raise ValueError("non-DR_MODE DrawOTag primitive modified GPU state")
            # Pinned PC libgpu.c dispatches DR_MODE solely to update the
            # persistent draw mode/texture window. It makes no raster or
            # VRAM writes. A forged transition must not be counted as a
            # pixel operation, even when the following FT4 starts with
            # exactly that forged POST snapshot.
            if before["primitive_type"] == 5 and changed:
                raise ValueError("DR_MODE DrawOTag primitive modified VRAM")
            previous_draw_post=b
            previous_draw_gpu_state=(after["window"],after["draw_mode"])
            previous_draw_env=after.get("draw_env")
            draws+=1
            draw_changed_words+=changed
        else:
            transfer_changed_words+=changed
            if kind=="load":
                loads+=1
                # The pinned C hook passes src and rect->w*rect->h only
                # when both dimensions are in 1..128 (not merely when
                # area <= 16384). The recorder must persist the AFTER
                # payload for each such positive bounded rectangle.
                if before["upload"]:
                    raise ValueError("LoadImage before event must not claim an upload payload")
                rect=after["rect"]
                expected_payload=(1 <= rect[2] <= 128 and 1 <= rect[3] <= 128)
                upload=after["upload"]
                if expected_payload:
                    if not upload:
                        raise ValueError("bounded LoadImage missing mandatory upload payload")
                    payload = private_file(directory,upload,expected=rect[2]*rect[3]*2)
                    validate_bounded_load_vram(a, b, payload, rect)
                    upload_hashes.append(sha(payload))
                else:
                    if upload:
                        raise ValueError("out-of-range LoadImage cannot have recorded upload payload")
                    load_pairs_without_payload+=1
            elif kind=="move":
                validate_move_vram(a,b,after["rect"],after["dest"])
                moves+=1
                move_pairs_with_verified_vram_effect+=1
            elif kind=="clear":
                validate_clear_vram(a,b,after["rect"],after["rgb"])
                clears+=1
                clear_pairs_with_verified_vram_effect+=1
    # Preserve PR#55 full VRAM/transfer verifications AND main's terminal
    # recorder completeness receipt. No receipt means diagnostic only.
    status_path = directory / STATUS
    if status_path.exists() or status_path.is_symlink():
        status_report = verify_capture_receipt(
            directory, target_frame=target_frame, events=events)
    else:
        status_report = {
            "capture_receipt_supplied": False,
            "capture_window_closed_without_detected_loss": False,
            "full_original_gameplay_frame_proven": False,
        }
    return {
        **status_report,
        "native_gpu_events_sha256":sha(log_raw),
        "vram_snapshot_sha256_list_sha256":sha("".join(snapshot_hashes).encode("ascii")),
        "upload_payload_sha256_list_sha256":(
            sha("".join(upload_hashes).encode("ascii")) if upload_hashes else None
        ),
        "load_pairs_with_verified_payload":len(upload_hashes),
        "load_pairs_with_verified_vram_effect":len(upload_hashes),
        "load_pairs_without_payload":load_pairs_without_payload,
        "frame":target_frame,
        "native_gpu_pairs_verified":pairs,
        "draw_otag_primitive_pairs":draws,
        "draw_boundary_vram_checks":draw_boundary_vram_checks,
        "draw_boundary_gpu_state_checks":draw_boundary_gpu_state_checks,
        "load_image_pairs":loads,
        "move_image_pairs":moves,
        "move_pairs_with_verified_vram_effect":move_pairs_with_verified_vram_effect,
        "clear_image_pairs":clears,
        "clear_pairs_with_verified_vram_effect":clear_pairs_with_verified_vram_effect,
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
