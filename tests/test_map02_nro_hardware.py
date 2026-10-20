"""Synthetic NRO loader-format regression tests; no retail or private data."""
from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import audit_map02_nro_hardware as fmt


def fixture():
    declared = 0x3000
    image = bytearray(declared + 0x38 + 0x4000)
    image[0x10:0x14] = b"NRO0"
    struct.pack_into("<I", image, 0x04, 0x100)
    struct.pack_into("<I", image, 0x18, declared)
    struct.pack_into("<II", image, 0x20, 0, 0x1000)
    struct.pack_into("<II", image, 0x28, 0x1000, 0x1000)
    struct.pack_into("<II", image, 0x30, 0x2000, 0x1000)
    struct.pack_into("<I", image, 0x38, 0x1000)
    image[0x100:0x104] = b"MOD0"
    image[declared:declared + 4] = b"ASET"
    struct.pack_into("<QQ", image, declared + 0x18, 0x38, 0x4000)
    start = declared + 0x38
    title = fmt.EXPECTED_TITLE.encode("utf-8")
    author = fmt.EXPECTED_AUTHOR.encode("utf-8")
    image[start:start + len(title)] = title
    image[start + 0x200:start + 0x200 + len(author)] = author
    return image


def edit32(data, index, value):
    struct.pack_into("<I", data, index, value)


class SwitchNroHardwareFormatTests(unittest.TestCase):
    def test_synthetic_candidate_passes_and_reports_actual_structure(self):
        data = fixture()
        doc = fmt.parse_nro(bytes(data))
        self.assertEqual(doc["format"], "NRO0")
        self.assertEqual(doc["declared_executable_size"], 0x3000)
        self.assertEqual(doc["assets"]["nacp"]["size"], 0x4000)
        self.assertFalse(doc["physical_switch_boot_verified"])

    def reject(self, operation, expected):
        data = fixture()
        operation(data)
        with self.assertRaisesRegex(fmt.NroError, expected):
            fmt.parse_nro(bytes(data))

    def test_corrupt_header_and_short_file(self):
        self.reject(lambda x: x.__setitem__(slice(0x10, 0x14), b"ELF!"),
                    "NRO0")
        with self.assertRaisesRegex(fmt.NroError, "truncated"):
            fmt.parse_nro(b"too short")

    def test_missing_mod0_and_bad_start_pointer(self):
        self.reject(lambda x: x.__setitem__(slice(0x100, 0x104), b"NOPE"),
                    "MOD0")
        self.reject(lambda x: edit32(x, 0x04, 0x5000), "MOD0 offset")

    def test_segment_overlap_or_gap_or_zero_length(self):
        self.reject(lambda x: edit32(x, 0x28, 0), "contiguous")
        self.reject(lambda x: edit32(x, 0x28, 0x2000), "contiguous")
        self.reject(lambda x: edit32(x, 0x24, 0), "nonzero")
        self.reject(lambda x: edit32(x, 0x24, 0xFFF), "aligned")

    def test_declared_executable_out_of_bounds(self):
        self.reject(lambda x: edit32(x, 0x18, 0x60000), "declared")
        self.reject(lambda x: edit32(x, 0x18, 0x3100), "page aligned")

    def test_non_page_aligned_bss(self):
        self.reject(lambda x: edit32(x, 0x38, 0x37), "bss")

    def test_missing_wrong_asset_magic_or_version(self):
        self.reject(lambda x: x.__setitem__(slice(0x3000, 0x3004), b"NOPE"),
                    "ASET")
        self.reject(lambda x: edit32(x, 0x3004, 2), "ASET version")

    def test_missing_nacp_or_oob_metadata(self):
        self.reject(lambda x: struct.pack_into(
            "<QQ", x, 0x3000 + 0x18, 0, 0), "NACP")
        self.reject(lambda x: struct.pack_into(
            "<QQ", x, 0x3000 + 0x18, 0x1000, 0x4000), "outside")

    def test_forged_name_and_author(self):
        self.reject(lambda x: x.__setitem__(
            slice(0x3038, 0x3038 + 8), b"RETAIL!!"), "title")
        self.reject(lambda x: x.__setitem__(
            slice(0x3038 + 0x200, 0x3038 + 0x208), b"RETAIL!!"),
            "author")

    def test_reject_unexpected_romfs_and_icon(self):
        self.reject(lambda x: struct.pack_into(
            "<QQ", x, 0x3000 + 0x08, 0x38, 4), "asset|overlap|icon")
        self.reject(lambda x: struct.pack_into(
            "<QQ", x, 0x3000 + 0x28, 0x38, 4), "asset|overlap|ROMFS")

    def test_nonzero_dangling_asset_pointer(self):
        self.reject(lambda x: struct.pack_into(
            "<QQ", x, 0x3000 + 0x08, 0x38, 0), "nonzero offset")

    def test_synthetic_report_writes_no_game_images(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            nro = root / "candidate.nro"
            report = root / "format.json"
            nro.write_bytes(fixture())
            import subprocess
            p = subprocess.run([
                sys.executable, str(Path(fmt.__file__)),
                "--nro", str(nro), "--report", str(report)
            ], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("VH_MAP02_HARDWARE_FORMAT_PASS", p.stdout)
            parsed = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(parsed["physical_switch_boot_verified"])
            self.assertNotIn("retail", parsed["title"].lower())

    def test_symlink_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            nro = root / "candidate.nro"
            alias = root / "alias.nro"
            nro.write_bytes(fixture())
            alias.symlink_to(nro)
            import subprocess
            p = subprocess.run([
                sys.executable, str(Path(fmt.__file__)),
                "--nro", str(alias), "--report", str(root / "result.json")
            ], capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("symlink", p.stderr)


if __name__ == "__main__":
    unittest.main()
