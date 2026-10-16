"""Independent multi-boundary Python -> real C packet/VRAM replay parity.

Four entirely synthetic full-size VRAM snapshots and three GPU submission
boundaries, including overlapping MoveImage and clipped LoadImage. This
exercises the existing production C packet decoder and transfer semantics,
and checks every snapshot against Python's source-pinned transfer auditor.
A passing test is NOT evidence of a genuine MAP02 capture.
"""
import ctypes
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from tools.export_map02_verified_vram_ledger import pack_verified_events
from tools.verify_map02_gpu_write_ledger import VRAM_BYTES, apply_transfer

SOURCE = Path(__file__).resolve().parent.parent / "source"
FRAME = 42

C_WRAPPER = r"""
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "map02_vram4_transfer_import.h"

/* C packet importer and the production GPU transfer primitive are both
 * used directly. Geometry/OT and camera checks are separately exercised
 * in tests/test_map02_captured_vram4_bridge.c. */
int verify_four_snapshots(const uint8_t *packet, size_t packet_bytes,
                          const uint8_t *first, const uint8_t *second,
                          const uint8_t *third, const uint8_t *fourth,
                          uint8_t *scratch, size_t scratch_bytes) {
    const uint8_t *images[4] = {first,second,third,fourth};
    VhMap02VramTransfer events[16];
    size_t n=0u, next=0u, boundary, i;
    if (!packet || !scratch || scratch_bytes < VH_MAP02_VRAM_BYTES)
        return 0;
    if (!vh_map02_vram_ledger_import_packet(
            packet,packet_bytes,42u,4u,events,16u,&n))
        return 0;
    if (vh_map02_vram_ledger_ranges_overlap(
            packet,packet_bytes,scratch,scratch_bytes))
        return 0;
    for (i=0u;i<4u;++i) {
        if (!images[i] || vh_map02_vram_ledger_ranges_overlap(
                images[i],VH_MAP02_VRAM_BYTES,scratch,scratch_bytes))
            return 0;
    }
    memcpy(scratch,first,VH_MAP02_VRAM_BYTES);
    for (boundary=1u;boundary<4u;++boundary) {
        while (next<n && events[next].before_submission==boundary) {
            vh_map02_vram_ledger_apply(scratch,&events[next]);
            ++next;
        }
        if (memcmp(scratch,images[boundary],VH_MAP02_VRAM_BYTES)!=0)
            return 0;
    }
    return next==n;
}
"""


def word(image, x, y, value):
    struct.pack_into("<H", image, 2 * (y * 1024 + x), value)


def as_array(raw):
    return (ctypes.c_uint8 * len(raw)).from_buffer_copy(raw)


class Map02CrossLanguageTransferTimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="vh-gpu-timeline-cross-")
        root = Path(cls.build.name)
        (root / "verify.c").write_text(C_WRAPPER, encoding="utf-8")
        cmd = [
            "gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
            "-fPIC", "-shared", "-I", str(SOURCE), str(root / "verify.c"),
            "-o", str(root / "verify.so"),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise AssertionError(result.stderr)
        cls.native = ctypes.CDLL(str(root / "verify.so")).verify_four_snapshots
        ptr = ctypes.POINTER(ctypes.c_uint8)
        cls.native.argtypes = [ptr, ctypes.c_size_t, ptr, ptr, ptr, ptr,
                               ptr, ctypes.c_size_t]
        cls.native.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def make_case(self):
        baseline = bytearray(VRAM_BYTES)
        word(baseline, 690, 499, 0x001f)
        word(baseline, 691, 499, 0x7c00)
        for x, value in zip((10, 11, 12, 13), (1, 2, 3, 4)):
            word(baseline, x, 12, value)

        payload_green = struct.pack("<H", 0x03e0)
        payload_clipped = struct.pack("<6H", 0x1111, 0x2222, 0x3333,
                                      0x4444, 0x5555, 0x6666)
        # Two LOAD operations, overlapping MOVE, and CLEAR at unrelated VRAM
        # all in one source-matched submission sequence.
        events = [
            ({"step": 0, "before_submission": 1, "op": "load",
              "rect": [690, 499, 1, 1]}, payload_green),
            ({"step": 1, "before_submission": 2, "op": "move",
              "rect": [691, 499, 1, 1], "dest": [690, 499]}, None),
            ({"step": 2, "before_submission": 2, "op": "clear",
              "rect": [20, 20, 2, 2], "rgb": [160, 136, 32]}, None),
            ({"step": 3, "before_submission": 3, "op": "load",
              "rect": [-1, 511, 3, 2]}, payload_clipped),
            ({"step": 4, "before_submission": 3, "op": "move",
              "rect": [10, 12, 3, 1], "dest": [11, 12]}, None),
        ]
        images = [bytes(baseline)]
        current = baseline
        for boundary in range(1, 4):
            for event, payload in events:
                if event["before_submission"] == boundary:
                    apply_transfer(current, event, payload)
            images.append(bytes(current))
        self.assertEqual(len(images), 4)
        self.assertEqual(struct.unpack_from("<H", images[1],
                          2 * (499 * 1024 + 690))[0], 0x03e0)
        self.assertEqual(struct.unpack_from("<H", images[2],
                          2 * (499 * 1024 + 690))[0], 0x7c00)
        self.assertEqual(struct.unpack_from("<H", images[3],
                          2 * (511 * 1024))[0], 0x2222)
        self.assertEqual(struct.unpack_from("<4H", images[3],
                          2 * (12 * 1024 + 10)), (1, 1, 1, 1))
        return events, images

    def check(self, packet, images, *, scratch=None):
        payload = as_array(packet)
        snapshots = [as_array(raw) for raw in images]
        target = scratch if scratch is not None else bytearray(VRAM_BYTES)
        target_view = (ctypes.c_uint8 * len(target)).from_buffer(target)
        return self.native(payload, len(packet), *snapshots,
                           target_view, len(target))

    def test_python_packet_matches_every_c_snapshot_transition(self):
        events, images = self.make_case()
        packet = pack_verified_events(FRAME, 4, events)
        self.assertEqual(self.check(packet, images), 1)

        # Existing hashes from Python evidence would prevent such a change,
        # but independent C replay must also reject wrong supplied bytes.
        altered = list(images)
        last = bytearray(altered[3])
        last[-1] ^= 1  # unrelated final-byte mutation
        altered[3] = bytes(last)
        self.assertEqual(self.check(packet, altered), 0)

        altered = list(images)
        first_change = bytearray(altered[1])
        word(first_change, 690, 499, 0x001f)
        altered[1] = bytes(first_change)
        self.assertEqual(self.check(packet, altered), 0)

        swapped = list(images)
        swapped[1], swapped[2] = swapped[2], swapped[1]
        self.assertEqual(self.check(packet, swapped), 0)

    def test_event_order_and_payload_mutations_fail(self):
        events, images = self.make_case()
        base = pack_verified_events(FRAME, 4, events)
        self.assertEqual(self.check(base, images), 1)

        wrong = [({**event, "before_submission":
                  3 if event["step"] == 1 else event["before_submission"]},
                  payload) for event, payload in events]
        # Reorder the changed boundary's events into a canonical nondecreasing
        # stream to expose semantic mismatch rather than only schema failure.
        wrong = [wrong[0], wrong[2], wrong[1], *wrong[3:]]
        wrong = [({**event, "step": i}, payload)
                 for i, (event, payload) in enumerate(wrong)]
        modified = pack_verified_events(FRAME, 4, wrong)
        self.assertEqual(self.check(modified, images), 0)

        altered = bytearray(base)
        altered[-1] ^= 1  # last MOVE rectangle field, not a payload
        self.assertEqual(self.check(altered, images), 0)
        altered = bytearray(base)
        altered[0] ^= 1
        self.assertEqual(self.check(altered, images), 0)

    def test_invalid_scratch_rejected(self):
        events, images = self.make_case()
        packet = pack_verified_events(FRAME, 4, events)
        self.assertEqual(self.check(packet, images,
                                   scratch=bytearray(VRAM_BYTES - 1)), 0)


if __name__ == "__main__":
    unittest.main()
