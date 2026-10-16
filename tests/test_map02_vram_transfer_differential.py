"""Asset-free differential test: C MAP02 GPU transfers vs Python auditor.

Build the actual portable C replay implementation and independently compare
whole VRAM images against the source-pinned Python model. All inputs invented.
This is NOT an original gameplay capture or PS1 GPU pixel-accuracy proof.
"""
import ctypes
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest

from tools.verify_map02_gpu_write_ledger import VRAM_BYTES, apply_transfer

ROOT = Path(__file__).resolve().parent.parent

WRAPPER = r"""
#include <stddef.h>
#include <stdint.h>
#include "map02_vram4_transfer_ledger.h"
int apply_one(uint8_t *vram, int op, int x, int y, int w, int h,
              int dx, int dy, int red, int green, int blue,
              const uint8_t *payload, size_t payload_bytes) {
    VhMap02VramTransfer event = {0};
    if (!vram) return -1;
    event.frame=42u;
    event.before_submission=1u;
    event.operation=op;
    event.x=x; event.y=y; event.w=w; event.h=h;
    event.dest_x=dx; event.dest_y=dy;
    event.red=red; event.green=green; event.blue=blue;
    event.load_le=payload; event.load_bytes=payload_bytes;
    if (!vh_map02_vram_ledger_event_valid(&event,0u,42u,2u)) return -1;
    vh_map02_vram_ledger_apply(vram,&event);
    return 1;
}
"""


class Map02VramTransferDifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="vh-map02-vram-diff-")
        cls.root = Path(cls.tmp.name)
        (cls.root / "replay.c").write_text(WRAPPER, encoding="utf-8")
        result = subprocess.run(
            ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
             "-fPIC", "-shared", "-I", str(ROOT / "source"),
             str(cls.root / "replay.c"), "-o", str(cls.root / "replay.so")],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.native = ctypes.CDLL(str(cls.root / "replay.so")).apply_one
        cls.native.argtypes = [
            ctypes.POINTER(ctypes.c_uint8),
            *([ctypes.c_int] * 10),
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
        ]
        cls.native.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def compare_one(self, baseline, event, payload=None):
        python_image = bytearray(baseline)
        native_image = bytearray(baseline)
        expected_writes = apply_transfer(python_image, event, payload)
        buffer = (ctypes.c_uint8 * VRAM_BYTES).from_buffer(native_image)
        if payload is None:
            native_payload = None
            payload_bytes = 0
        else:
            native_payload = (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
            payload_bytes = len(payload)
        mapping = {"load": 1, "move": 2, "clear": 3}
        x,y,w,h = event["rect"]
        dx,dy = event.get("dest", [0,0])
        r,g,b = event.get("rgb", [0,0,0])
        rc = self.native(
            buffer, mapping[event["op"]], x,y,w,h,dx,dy,r,g,b,
            native_payload,payload_bytes,
        )
        self.assertEqual(rc, 1, event)
        self.assertEqual(native_image,python_image,event)
        self.assertGreaterEqual(expected_writes,0)

    def test_clipped_load_images_and_random_payloads(self):
        rng = random.Random(0x4d41503032)
        start = bytearray(VRAM_BYTES)
        for i in range(36):
            if i % 3 == 0:
                x,y = -rng.randint(0,8),rng.randint(0,511)
            elif i % 3 == 1:
                x,y = rng.randint(1017,1032),rng.randint(507,520)
            else:
                x,y = rng.randint(0,1015),rng.randint(0,503)
            w,h=rng.randint(1,16),rng.randint(1,16)
            payload=bytes(rng.randrange(256) for _ in range(w*h*2))
            self.compare_one(start,{"op":"load","rect":[x,y,w,h]},payload)

    def test_original_in_place_move_overlap_and_clipping(self):
        rng = random.Random(0x105a)
        baseline=bytearray(VRAM_BYTES)
        # Deterministic non-uniform values expose in-place vs memmove errors.
        for i in range(0,VRAM_BYTES,2):
            w = ((i//2)*97 ^ ((i//2)>>3)) & 65535
            struct.pack_into("<H",baseline,i,w)
        cases = [
            (10,12,3,1,11,12), # right, forward overlap
            (10,12,3,1,9,12), # left overlap
            (10,12,2,3,10,13), # down overlap
            (10,12,2,3,10,11), # up overlap
            (1023,511,8,4,1020,509), # clipped corner
            (-2,-1,6,3,1,0), # source clipping
            (0,0,8,6,-2,-1), # destination clipping
            (1025,512,8,2,20,30), # wholly outside source
        ]
        for _ in range(32):
            x=rng.choice([-8,0,5,50,1018,1024])
            y=rng.choice([-8,0,5,50,508,512])
            w=rng.randint(1,12)
            h=rng.randint(1,8)
            dx=x+rng.randint(-5,5)
            dy=y+rng.randint(-5,5)
            cases.append((x,y,w,h,dx,dy))
        for x,y,w,h,dx,dy in cases:
            self.compare_one(
                baseline,{"op":"move","rect":[x,y,w,h],"dest":[dx,dy]},
            )

    def test_clear_color_quantization_and_frame_edges(self):
        rng=random.Random(0xceb9)
        original=bytearray(VRAM_BYTES)
        for i in range(40):
            if i % 4 == 0:
                x,y=-rng.randrange(10),-rng.randrange(10)
            elif i % 4 == 1:
                x,y=1016+rng.randrange(16),504+rng.randrange(16)
            else:
                x,y=rng.randrange(1000),rng.randrange(490)
            rect=[x,y,rng.randrange(1,16),rng.randrange(1,16)]
            rgb=[rng.randrange(256) for _ in range(3)]
            self.compare_one(original,{"op":"clear","rect":rect,"rgb":rgb})

    def test_maximum_bounded_transfer(self):
        rng=random.Random(17)
        baseline=bytearray(VRAM_BYTES)
        payload=bytes(rng.randrange(256) for _ in range(128*128*2))
        self.compare_one(
            baseline,{"op":"load","rect":[-3,490,128,128]},payload)
        self.compare_one(
            baseline,{"op":"clear","rect":[1010,510,128,128],
                      "rgb":[255,127,31]})
        self.compare_one(
            baseline,{"op":"move","rect":[1010,510,128,128],
                      "dest":[1000,500]})

    def test_repeated_chain_does_not_hide_order_effects(self):
        rng=random.Random(1024)
        py=bytearray(VRAM_BYTES)
        native=bytearray(VRAM_BYTES)
        for i in range(20):
            op=("load","move","clear")[i%3]
            x=rng.randrange(50)
            y=rng.randrange(50)
            event={"op":op,"rect":[x,y,8,6]}
            payload=None
            if op=="load":
                payload=bytes(rng.randrange(256) for _ in range(96))
            elif op=="move":
                event["dest"]=[x+1,y+1]
            else:
                event["rgb"]=[rng.randrange(256) for _ in range(3)]
            apply_transfer(py,event,payload)
            x,y,w,h=event["rect"]
            dx,dy=event.get("dest",[0,0])
            r,g,b=event.get("rgb",[0,0,0])
            pv=(ctypes.c_uint8*len(payload)).from_buffer_copy(payload) if payload else None
            rc=self.native((ctypes.c_uint8*VRAM_BYTES).from_buffer(native),
                {"load":1,"move":2,"clear":3}[op],
                x,y,w,h,dx,dy,r,g,b,pv,len(payload or b""))
            self.assertEqual(rc,1)
        self.assertEqual(native,py)


if __name__ == "__main__":
    unittest.main()
