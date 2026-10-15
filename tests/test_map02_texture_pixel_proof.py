"""Synthetic tests of read-only MAP02 PRS-vs-DAT texture pixel proof."""
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

from test_audit_map02_disc_prs import (
    encoded_test_map, write_fake_image, write_fake_dat_sectors,
)
from tools.audit_map02_disc_prs import (
    PRIOR_DAT_LENGTH, USER_BYTES, RAW_BYTES, SYNC, unpack_prs, xa_edc,
)
from tools.compare_map02_variants import (
    FACE_GFX_OFFSET, RECORD_SIZE, TARGET_RECORDS,
)
from tools.map02_texture_pixel_proof import (
    ATLAS_LBA, ATLAS_SECTORS, ATLAS_LENGTH,
    LAND_LBA, LAND_SECTORS, LAND_LENGTH,
    LAND_BLOCK_INDEX, LAND_BLOCK_SIZE, SLOT_REFERENCES,
    build_evidence, encode_png, make_contact_sheet, sample_slot, swatch_rgb,
)


def fake_atlas_and_land():
    atlas = bytearray(ATLAS_LENGTH)
    land = bytearray(LAND_LENGTH)
    at = LAND_BLOCK_INDEX * LAND_BLOCK_SIZE
    for slot, (uvwh, clut, _) in SLOT_REFERENCES.items():
        land[at + slot * 4:at + slot * 4 + 4] = bytes(uvwh)
        land[at + 1028 + slot] = clut
    for clut, color in ((35, 0x001F), (33, 0x03E0)):
        palette = at + 1285 + (clut - 32) * 32
        struct.pack_into("<H", land, palette, color)
    # Demonstrate low and high nibble ordering for the PRS 241 swatch.
    u, v = SLOT_REFERENCES[241][0][:2]
    atlas[v * 128 + u // 2] = 0x10
    return bytes(atlas), bytes(land)


def write_sectors(image, layout, start, count, content):
    payload = content.ljust(count * USER_BYTES, b"\x00")
    size = RAW_BYTES if layout == "mode2-2352" else USER_BYTES
    with image.open("r+b") as handle:
        handle.seek(start * size)
        for i in range(count):
            sector = payload[i * USER_BYTES:(i + 1) * USER_BYTES]
            if layout == "mode2-2352":
                prefix = SYNC + bytes(3) + b"\x02" + bytes(8) + sector
                sector = (prefix + xa_edc(prefix[16:2072]).to_bytes(4, "little")
                          + bytes(276))
            handle.write(sector)


def make_fake_image(path: Path, layout="iso-2048"):
    prs = encoded_test_map()
    write_fake_image(path, prs, layout)
    raw = bytearray(unpack_prs(prs))
    for record, dat_value in zip(TARGET_RECORDS, (98, 150)):
        raw[record * RECORD_SIZE + FACE_GFX_OFFSET] = dat_value
    dat = bytes(raw).ljust(PRIOR_DAT_LENGTH, b"\x00")
    write_fake_dat_sectors(path, dat, layout)
    atlas, land = fake_atlas_and_land()
    write_sectors(path, layout, ATLAS_LBA, ATLAS_SECTORS, atlas)
    write_sectors(path, layout, LAND_LBA, LAND_SECTORS, land)


def parse_rgb_png(png: bytes):
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    offset = 8
    chunks = []
    width = height = 0
    while offset < len(png):
        length = struct.unpack_from(">I", png, offset)[0]
        kind = png[offset + 4:offset + 8]
        payload = png[offset + 8:offset + 8 + length]
        checksum = struct.unpack_from(">I", png, offset + 8 + length)[0]
        assert checksum == zlib.crc32(kind + payload) & 0xffffffff
        chunks.append((kind, payload))
        offset += length + 12
        if kind == b"IHDR":
            width, height = struct.unpack_from(">II", payload)
        if kind == b"IEND":
            break
    raw = zlib.decompress(b"".join(p for k, p in chunks if k == b"IDAT"))
    return width, height, raw


class Map02TexturePixelProofTests(unittest.TestCase):
    def test_slot_has_correct_clut_and_nibble_order(self):
        atlas, land = fake_atlas_and_land()
        block = land[LAND_BLOCK_INDEX * LAND_BLOCK_SIZE:
                     (LAND_BLOCK_INDEX + 1) * LAND_BLOCK_SIZE]
        sample = sample_slot(atlas, block, 241)
        self.assertEqual(sample["uvwh"], [240, 192, 15, 15])
        self.assertEqual(sample["clut_index"], 35)
        self.assertEqual(sample["width"], 16)
        self.assertEqual(sample["height"], 16)
        self.assertEqual(sample["palette_indices"][:2], [0, 1])
        self.assertEqual(sample["raw_color_words"][:2], [0x001f, 0])
        self.assertEqual(swatch_rgb(sample["raw_color_words"][:2], 2, 1),
                         b"\xff\x00\x00\x00\x00\x00")
        self.assertFalse(sample["matches_archived_pixels"])
        self.assertEqual(sample["raw_zero_pixels"], 1)
        self.assertEqual(sample["stp_flag_pixels"], 0)

    def test_all_four_slots_are_independent_and_verifiable(self):
        atlas, land = fake_atlas_and_land()
        block = land[LAND_BLOCK_INDEX * LAND_BLOCK_SIZE:
                     (LAND_BLOCK_INDEX + 1) * LAND_BLOCK_SIZE]
        slots = [241, 98, 243, 150]
        samples = [sample_slot(atlas, block, s) for s in slots]
        self.assertEqual([p["slot"] for p in samples], slots)
        self.assertEqual([p["clut_index"] for p in samples], [35, 35, 33, 33])
        self.assertTrue(all(len(p["raw_color_words"]) == 256 for p in samples))
        self.assertTrue(all(not p["matches_archived_pixels"] for p in samples))
        for sample in samples:
            key = (struct.pack("<HH", 16, 16)
                   + struct.pack("<256H", *sample["raw_color_words"]))
            self.assertEqual(hashlib.sha256(key).hexdigest(),
                             sample["decoded_pixels_sha256"])

    def test_invalid_uv_clut_and_wrong_sizes_are_rejected(self):
        atlas, land = fake_atlas_and_land()
        record = bytearray(land[LAND_BLOCK_INDEX * LAND_BLOCK_SIZE:
                                (LAND_BLOCK_INDEX + 1) * LAND_BLOCK_SIZE])
        for offset, bad in ((241 * 4 + 2, 0),
                            (241 * 4, 250), (1028 + 241, 0)):
            with self.subTest(offset=offset):
                original = record[offset]
                record[offset] = bad
                with self.assertRaisesRegex(ValueError, "UV|CLUT"):
                    sample_slot(atlas, bytes(record), 241)
                record[offset] = original
        with self.assertRaisesRegex(ValueError, "length"):
            sample_slot(atlas[:100], bytes(record), 241)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            sample_slot(atlas, bytes(record), 99)

    def test_rgb_png_is_losslessly_decodable_and_panel_ordered(self):
        atlas, land = fake_atlas_and_land()
        rec = land[LAND_BLOCK_INDEX * LAND_BLOCK_SIZE:
                   (LAND_BLOCK_INDEX + 1) * LAND_BLOCK_SIZE]
        samples = [sample_slot(atlas, rec, s) for s in (241, 98, 243, 150)]
        w, h, rgb, panels = make_contact_sheet(samples)
        self.assertEqual((w, h), (292, 292))
        self.assertEqual([p["slot"] for p in panels], [241, 98, 243, 150])
        png = encode_png(w, h, rgb)
        pw, ph, raw = parse_rgb_png(png)
        self.assertEqual((pw, ph), (w, h))
        self.assertEqual(len(raw), h * (1 + w * 3))
        for panel in panels:
            row_start = panel["y"] * (1 + w * 3)
            pos = row_start + 1 + panel["x"] * 3
            pixel = raw[pos:pos + 3]
            expected = b"\xff\x00\x00" if panel["slot"] in (241, 98) else b"\x00\xff\x00"
            self.assertEqual(pixel, expected)

    def test_end_to_end_iso_image_is_noncanonical_but_creates_no_assets_in_repo(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            image = base / "synthetic.iso"
            make_fake_image(image)
            report, png = build_evidence(image, "iso-2048")
            self.assertFalse(report["all_archived_evidence_matches"])
            self.assertTrue(report["verification"]["two_byte_prs_dat_difference"])
            self.assertFalse(report["verification"]["all_four_pixel_sha256"])
            self.assertEqual([s["slot"] for s in report["swatches"]], [241, 98, 243, 150])
            self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual([p["column"] for p in report["png_panels"]], [0, 1, 0, 1])
            before = set(base.iterdir())
            cmd = [sys.executable, "-m", "tools.map02_texture_pixel_proof",
                   "--disc-image", str(image), "--layout", "iso-2048",
                   "--output-prefix", str(base / "comparison")]
            bad = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("source data differs from archived", bad.stderr)
            self.assertEqual(set(base.iterdir()), before)
            good = subprocess.run(cmd + ["--allow-unverified-source"],
                                  capture_output=True, text=True)
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertTrue((base / "comparison.png").is_file())
            j = json.loads((base / "comparison.json").read_text())
            self.assertFalse(j["all_archived_evidence_matches"])
            self.assertFalse(j["verification"]["all_four_pixel_sha256"])
            self.assertEqual(j["png_panels"][2]["slot"], 243)
            repeat = subprocess.run(cmd + ["--allow-unverified-source"],
                                    capture_output=True, text=True)
            self.assertNotEqual(repeat.returncode, 0)
            self.assertIn("output already exists", repeat.stderr)

    def test_corrupt_mode2_atlas_sector_refuses_visual_result(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            image = base / "synthetic.bin"
            make_fake_image(image, "mode2-2352")
            report, _ = build_evidence(image, "mode2-2352")
            self.assertFalse(report["all_archived_evidence_matches"])
            with image.open("r+b") as handle:
                handle.seek(ATLAS_LBA * RAW_BYTES + 24)
                old = handle.read(1)
                handle.seek(ATLAS_LBA * RAW_BYTES + 24)
                handle.write(bytes((old[0] ^ 1,)))
            with self.assertRaisesRegex(ValueError, "EDC mismatch"):
                build_evidence(image, "mode2-2352")


if __name__ == "__main__":
    unittest.main()
