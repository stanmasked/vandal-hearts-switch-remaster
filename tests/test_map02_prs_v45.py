#!/usr/bin/env python3
"""v45 bounded PRS inspection: adversarial cases and real v24 coverage."""
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from preflight_map02_prs_v45 import (
    EXPECTED, InvalidPrs, MAX_COMPRESSED, STRIDE, WIDTH, read_prs,
    unpack_bounded, load_v24, inspect_file, inspect_models,
)

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "tests/fixtures/vh_map02_hd_lookup_v24.h"


def literal_encode(raw):
    blocks = []
    for off in range(0, len(raw), 8):
        blocks.append(b"\x00" + raw[off:off + 8])
    return b"".join(blocks)


def synth_models():
    buf = bytearray(EXPECTED)
    for x, slot in ((19, 241), (20, 243)):
        o = (8 * WIDTH + x) * STRIDE
        for i, (vx, vy, vz) in enumerate(
                ((0, 0, 1000), (64, 0, 1000),
                 (64, 64, 1000), (0, 64, 1000))):
            struct.pack_into("<hhhh", buf, o + i*8, vx, vy, vz, 0)
        struct.pack_into("<h", buf, o + 176, slot + 400)
        buf[o + 212:o + 216] = b"\x00\x01\x02\x03"
        buf[o + 284] = 0
        buf[o + 302] = 1
    return bytes(buf)


class TestSafeUnpack(unittest.TestCase):
    def test_literal_roundtrip_synthetic_336_tiles(self):
        original = synth_models()
        self.assertEqual(unpack_bounded(literal_encode(original)), original)

    def test_absolute_dictionary_token(self):
        self.assertEqual(unpack_bounded(b"\x01\x00\x00", 3), b"\x00"*3)

    def test_relative_dictionary_token(self):
        self.assertEqual(unpack_bounded(b"\x01\x80", 2), b"\x00"*2)

    def test_literal_run_c0_exactly_8(self):
        b = b"abcdefgh"
        self.assertEqual(unpack_bounded(b"\x01\xc0"+b, 8), b)

    def test_literal_run_ff_exactly_71(self):
        b = bytes(range(71))
        self.assertEqual(unpack_bounded(b"\x01\xff"+b, 71), b)

    def test_relative_overlap_uses_live_ring(self):
        self.assertEqual(unpack_bounded(b"\x02A\x81", 3), b"AAA")

    def test_absolute_overlap_uses_live_ring(self):
        self.assertEqual(unpack_bounded(bytes((2, ord("X"), 3, 990 & 255)), 4), b"XXXX")

    def test_decompression_bomb_rejected(self):
        with self.assertRaisesRegex(InvalidPrs, "exceeds"):
            unpack_bounded(b"\x01\xff" + bytes(range(71)), 8)

    def test_truncated_literal_group_rejected(self):
        with self.assertRaisesRegex(InvalidPrs, "truncated"):
            unpack_bounded(b"\x00A", 2)

    def test_truncated_absolute_token_rejected(self):
        with self.assertRaisesRegex(InvalidPrs, "truncated"):
            unpack_bounded(b"\x01\x00", 3)

    def test_truncated_literal_run_rejected(self):
        with self.assertRaisesRegex(InvalidPrs, "truncated"):
            unpack_bounded(b"\x01\xc0hello", 8)

    def test_wrong_expected_output_length_rejected(self):
        with self.assertRaises(InvalidPrs):
            unpack_bounded(b"\x00A", 2)

    def test_invalid_output_caps_rejected(self):
        for cap in (0, -1, EXPECTED + 1):
            with self.subTest(cap=cap):
                with self.assertRaises(InvalidPrs):
                    unpack_bounded(b"\x00A", cap)

    def test_empty_compressed_payload_rejected(self):
        with self.assertRaises(InvalidPrs):
            unpack_bounded(b"", 1)

    def test_excessive_compressed_payload_rejected(self):
        with self.assertRaises(InvalidPrs):
            unpack_bounded(b"\x00"*(MAX_COMPRESSED+1), 1)

    def test_fuzz_random_inputs_do_not_escape_error_contract(self):
        # Fast deterministic adversarial corpus, no unbounded CPU or memory.
        import random
        rng = random.Random(0x4502)
        for _ in range(100):
            raw = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 60)))
            try:
                result = unpack_bounded(raw, 256)
                self.assertEqual(len(result), 256)
            except InvalidPrs:
                pass


class TestV24Models(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.slots = load_v24(HEADER)

    def test_metadata_120_entries_96_masters(self):
        self.assertEqual(len(self.slots), 120)
        self.assertEqual(len({row[1] for row in self.slots.values()}), 96)

    def test_special_rows_not_conflated(self):
        self.assertEqual(self.slots[241][1], 241)
        self.assertEqual(self.slots[243][1], 243)
        self.assertEqual(self.slots[241][8:10], (5, 31978))
        self.assertEqual(self.slots[243][8:10], (5, 31850))
        self.assertNotIn(242, self.slots)

    def test_decoded_grid_and_coverage(self):
        report = inspect_models(synth_models(), self.slots)
        self.assertEqual(report["tiles_with_faces"], 2)
        self.assertEqual(report["empty_tiles"], 334)
        self.assertEqual(report["v24_candidate_faces"], 2)
        self.assertEqual(report["v24_matched_faces"], 2)
        self.assertEqual(report["v24_unmatched_faces"], 0)
        self.assertEqual(report["v24_distinct_masters_observed"], 2)
        self.assertEqual(set(report["v24_matched_local_slot_counts"]), {"241","243"})

    def test_unknown_candidate_reports_gap_not_false_match(self):
        b = bytearray(synth_models())
        struct.pack_into("<h", b, (8 * WIDTH + 19)*STRIDE+176, 642)
        r = inspect_models(b, self.slots)
        self.assertEqual(r["v24_unmatched_local_slot_counts"], {"242":1})
        self.assertEqual(r["v24_matched_faces"], 1)

    def test_other_global_gfx_is_reported_separately(self):
        b = bytearray(synth_models())
        struct.pack_into("<h", b, (8 * WIDTH + 19)*STRIDE+176, 127)
        r = inspect_models(b, self.slots)
        self.assertEqual(r["non_candidate_gfx_counts"], {"127":1})

    def test_reject_bad_face_count(self):
        b = bytearray(synth_models())
        b[(8 * WIDTH + 19)*STRIDE+302] = 19
        with self.assertRaisesRegex(InvalidPrs, "faceCt"):
            inspect_models(b, self.slots)

    def test_reject_invalid_negative_and_oob_gfx(self):
        for gfx in (-1, 870):
            with self.subTest(gfx=gfx):
                b = bytearray(synth_models())
                struct.pack_into("<h", b, (8 * WIDTH+19)*STRIDE+176, gfx)
                with self.assertRaisesRegex(InvalidPrs, "GFX"):
                    inspect_models(b, self.slots)

    def test_reject_bad_face_vertex(self):
        b = bytearray(synth_models())
        b[(8 * WIDTH+19)*STRIDE+212] = 22
        with self.assertRaisesRegex(InvalidPrs, "vertex index"):
            inspect_models(b, self.slots)

    def test_reject_bad_shade(self):
        b = bytearray(synth_models())
        b[(8 * WIDTH+19)*STRIDE+284] = 26
        with self.assertRaisesRegex(InvalidPrs, "shade index"):
            inspect_models(b, self.slots)

    def test_reject_bad_decoded_size(self):
        with self.assertRaisesRegex(InvalidPrs, "size"):
            inspect_models(synth_models()[:-1], self.slots)

    def test_reject_corrupted_lookup_header(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"wrong.h"
            src = HEADER.read_text()
            path.write_text(src.replace("VH_MAP02_HD_SLOT_COUNT 120",
                                        "VH_MAP02_HD_SLOT_COUNT 119"))
            with self.assertRaisesRegex(InvalidPrs, "120-row"):
                load_v24(path)


class TestFilePreflight(unittest.TestCase):
    def with_file(self, data, callback):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"SYNTHETIC_M_MAP02.PRS"
            path.write_bytes(data)
            return callback(path)

    def fixture_bytes(self):
        compressed = literal_encode(synth_models())
        return struct.pack("<I", len(compressed)) + compressed

    def test_full_valid_synthetic_file(self):
        r = self.with_file(self.fixture_bytes(),
                           lambda p: inspect_file(p, HEADER, synthetic=True))
        self.assertEqual(r["status"], "structurally_valid_unverified_source")
        self.assertEqual(r["input_provenance"], "caller_declared_synthetic")
        self.assertFalse(r["retail_map_authenticity_proven"])
        self.assertFalse(r["runtime_tpage_clut_uv_proven"])
        self.assertFalse(r["HD_replacement_approved"])
        self.assertEqual(r["v24_matched_faces"], 2)

    def test_reject_nonzero_trailer(self):
        with self.assertRaisesRegex(InvalidPrs, "trailing"):
            self.with_file(self.fixture_bytes()+b"\xff",
                           lambda p: read_prs(p))

    def test_accept_explicit_zero_sector_padding(self):
        self.assertEqual(self.with_file(self.fixture_bytes()+b"\x00"*2048,
                         lambda p: read_prs(p, True)[2]["zero_padding_bytes"]), 2048)

    def test_reject_nonzero_tail_even_in_padding_mode(self):
        with self.assertRaisesRegex(InvalidPrs, "nonzero"):
            self.with_file(self.fixture_bytes()+b"\x00"*10+b"\x01",
                           lambda p: read_prs(p, True))

    def test_reject_truncated_declared_length(self):
        data = bytearray(self.fixture_bytes())
        struct.pack_into("<I", data, 0, len(data)+100)
        with self.assertRaisesRegex(InvalidPrs, "truncated"):
            self.with_file(data, lambda p: read_prs(p))

    def test_reject_oversize_declared_length(self):
        with self.assertRaisesRegex(InvalidPrs, "length"):
            self.with_file(struct.pack("<I", MAX_COMPRESSED+1)+b"X",
                           lambda p: read_prs(p))

    def test_reject_empty_prs_file(self):
        with self.assertRaisesRegex(InvalidPrs, "size"):
            self.with_file(b"", lambda p: read_prs(p))


if __name__ == "__main__":
    unittest.main()
