#!/usr/bin/env python3
"""Verify privately captured MAP02 GTE-camera records against portable projection.

Input: strict JSONL events from the opt-in pinned PC renderer instrumenter.
Only aggregate counters and SHA-256 are printed; source vertices, camera
positions, screenshots and original assets are NEVER emitted or uploaded.
This proves PC projection-model agreement for captured data, NOT PS1 GPU
hardware correctness or on-screen display.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

HEADER = Path(__file__).resolve().parent.parent / "source/map02_projection.h"
MAX_BYTES = 2 * 1024 * 1024
TARGETS = {(8, 19), (11, 11)}

WRAPPER = r"""
#include <stdint.h>
#include "map02_projection.h"
/* Return zero for equality. Internal, host-only C boundary. */
int vh_map02_verify_snapshot(const int32_t cam[16],
                             const int32_t vertex[12], int32_t observed_nclip,
                             const int32_t screen[8], int observed_otz,
                             int observed_visible) {
    VhMap02ProjectCamera c = {0};
    VhMap02ProjectVertex points[4];
    VhMap02ProjectFace result;
    int i,j;
    if (!cam || !vertex || !screen) return 99;
    for (i=0;i<3;++i) {
        for(j=0;j<3;++j) c.rt[i][j]=(int16_t)cam[i*3+j];
        c.tr[i]=cam[9+i];
    }
    c.ofx=cam[12]; c.ofy=cam[13];
    c.h=(int16_t)cam[14]; c.zsf4=(int16_t)cam[15];
    for(i=0;i<4;++i) {
        points[i].x=(int16_t)vertex[3*i];
        points[i].y=(int16_t)vertex[3*i+1];
        points[i].z=(int16_t)vertex[3*i+2];
    }
    if(!vh_map02_project_face(&c,points,1024,&result)) return 98;
    if(result.nclip_mac0 != observed_nclip) return 1;
    if((int)result.visible != observed_visible) return 2;
    if(!observed_visible) return observed_otz == -1 ? 0 : 3;
    if((int)result.otz != observed_otz) return 4;
    for(i=0;i<4;++i) {
        if(result.gpu[i].x != screen[2*i] ||
           result.gpu[i].y != screen[2*i+1]) return 5 + i;
    }
    return 0;
}
"""
MISMATCH = {
    1: "NCLIP signed MAC0",
    2: "NCLIP visibility",
    3: "culled polygon OTZ must be null",
    4: "AVSZ4 raw OTZ",
    5: "FT4 corner 0",
    6: "FT4 corner 1",
    7: "FT4 corner 2",
    8: "FT4 corner 3",
}


def require_int(n, label, lo, hi):
    if type(n) is not int or not lo <= n <= hi:
        raise ValueError(f"{label}: expected integer in {lo}..{hi}")
    return n


def require_vector(value, name, count, lo, hi):
    if type(value) is not list or len(value) != count:
        raise ValueError(f"{name} must contain exactly {count} entries")
    return [require_int(v, name, lo, hi) for v in value]


def parse_event(obj):
    if type(obj) is not dict or obj.get("stage") != "camera_projection":
        raise ValueError("expected camera_projection JSON object")
    z = require_int(obj.get("z"), "z", 0, 11)
    x = require_int(obj.get("x"), "x", 0, 23)
    if (z,x) not in TARGETS:
        raise ValueError("unexpected MAP02 target face")
    if obj.get("path") != "normal" or obj.get("face") != 0 or type(obj.get("face")) is not int:
        raise ValueError("only normal terrain face 0 is verified")
    frame = require_int(obj.get("frame"), "frame", 0, 2**32-1)
    gfx = require_int(obj.get("gfx"), "gfx", -2**31, 2**31-1)
    cam = require_vector(obj.get("camera"), "camera", 16, -2**31, 2**31-1)
    vertices = require_vector(obj.get("vertices"), "vertices", 12, -32768, 32767)
    for n in range(9):
        require_int(cam[n], "RT matrix", -32768, 32767)
    for n in (14,15):
        require_int(cam[n], "H / ZSF4", -32768, 32767)
    visible = obj.get("visible")
    if type(visible) is not bool:
        raise ValueError("visible must be a boolean")
    nclip = require_int(obj.get("nclip"), "nclip", -2**31, 2**31-1)
    if visible != (nclip > 0):
        raise ValueError("visible contradicts original NCLIP sign")
    if visible:
        screen = require_vector(obj.get("screen"), "screen", 8, -1024, 1023)
        raw_otz = require_int(obj.get("otz"), "raw OTZ", 0, 65535)
    else:
        if obj.get("screen") is not None or obj.get("otz") is not None:
            raise ValueError("culled polygon must have null screen/OTZ")
        screen = [0]*8
        raw_otz = -1
    return (z,x,frame,gfx,cam,vertices,nclip,visible,screen,raw_otz)


def verify_capture(raw: bytes, compiler="gcc", header: Path = HEADER) -> dict:
    if not raw or len(raw)>MAX_BYTES:
        raise ValueError("capture evidence is empty or over 2MiB limit")
    events=[]
    seen=set()
    for lineno, line in enumerate(raw.splitlines(),1):
        if not line.strip():
            raise ValueError(f"line {lineno}: blank event")
        try:
            obj=json.loads(line)
            row=parse_event(obj)
        except (ValueError,UnicodeError) as exc:
            raise ValueError(f"line {lineno}: {exc}") from exc
        key=(row[0],row[1])
        if key in seen:
            raise ValueError(f"line {lineno}: duplicate target face (first-only trace)")
        seen.add(key)
        events.append((lineno,row))
        if len(events)>2:
            raise ValueError("camera evidence contains more than two target faces")
    with tempfile.TemporaryDirectory(prefix="vh-map02-camera-compare-") as folder:
        root=Path(folder)
        (root / "map02_projection.h").write_bytes(header.read_bytes())
        (root / "verify.c").write_text(WRAPPER,encoding="utf-8")
        out=root / "libverify.so"
        run=subprocess.run([compiler,"-std=c11","-O2","-Wall","-Wextra",
                            "-Werror","-fPIC","-shared",str(root/"verify.c"),
                            "-o",str(out)],capture_output=True,text=True,timeout=30)
        if run.returncode:
            raise ValueError(f"portable projection C verifier failed to compile: {run.stderr[-1500:]}")
        library=ctypes.CDLL(str(out))
        arg_ints=ctypes.POINTER(ctypes.c_int32)
        library.vh_map02_verify_snapshot.argtypes=[
            arg_ints,arg_ints,ctypes.c_int32,arg_ints,ctypes.c_int32,ctypes.c_int32]
        library.vh_map02_verify_snapshot.restype=ctypes.c_int
        visible_count=0
        for lineno,row in events:
            _,_,_,_,camera,vertices,nclip,visible,screen,otz=row
            rc=library.vh_map02_verify_snapshot(
                (ctypes.c_int32*16)(*camera),(ctypes.c_int32*12)(*vertices),
                nclip,(ctypes.c_int32*8)(*screen),otz,int(visible))
            if rc:
                raise ValueError(f"line {lineno}: portable projection mismatch: "
                                 f"{MISMATCH.get(rc,'C verifier error '+str(rc))}")
            visible_count+=int(visible)
    return {
        "source_sha256":hashlib.sha256(raw).hexdigest(),
        "camera_projection_events":len(events),
        "faces_observed":sorted([{"z":r[0],"x":r[1],"face":0} for _,r in events],
                                key=lambda r:(r["z"],r["x"])),
        "visible_faces":visible_count,
        "culled_faces":len(events)-visible_count,
        "pc_projection_matches_captured_gte":True,
        "source_vertices_or_camera_emitted":False,
        "original_game_pixels_verified":False,
        "ps1_hardware_gte_verified":False,
    }


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_jsonl",type=Path,help="local camera_projection JSONL")
    parser.add_argument("--compiler",default="gcc")
    args=parser.parse_args()
    try:
        size=args.capture_jsonl.stat().st_size
        if not 0 < size <= MAX_BYTES:
            raise ValueError("capture evidence is empty or over 2MiB limit")
        report=verify_capture(args.capture_jsonl.read_bytes(),compiler=args.compiler)
    except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
