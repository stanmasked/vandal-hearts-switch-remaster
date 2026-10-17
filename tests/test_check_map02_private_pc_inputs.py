"""Local-only, entirely synthetic original PC resource readiness tests.

No real Vandal Hearts EXE, game asset or BIOS is bundled or accessed.
Real known original hashes are deliberately mocked ONLY inside this file.
"""
import hashlib
import struct
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.check_map02_private_pc_inputs import (
    ASSETS, BIOS_SIZE, EXE, FONT_BIOS_OFFSET, FONT_LENGTH,
    verify_private_pc_inputs,
)
from tools.check_map02_original_extraction_anchors import (
    ANCHORS, LOAD_VRAM, PSX_HEADER, compare_data_ranges,
)
from tools.check_map02_original_inc_provenance import (
    _original_blob_sha1, check_original_includes,
)


class PrivateOriginalRetailBuildInputsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-map02-original-preflight-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "upstream"
        self.root.mkdir()
        self.exe = self.root / EXE
        # Explicit synthetic data at the three locations from the pinned
        # original YAML. Checks use only an independent fake ELF fixture.
        exe_size = max(PSX_HEADER + address - LOAD_VRAM + length
                       for _, address, length in ANCHORS) + 16
        executable = bytearray(exe_size)
        executable[:8] = b"PS-X EXE"
        struct.pack_into("<I", executable, 0x18, LOAD_VRAM)
        struct.pack_into("<I", executable, 0x1c, exe_size - PSX_HEADER)
        for j in range(PSX_HEADER, exe_size):
            executable[j] = (j * 31 + 13) % 256
        self.exe.write_bytes(executable)
        elf = bytearray(256 + sum(length for _, _, length in ANCHORS))
        elf[:6] = b"\x7fELF\x01\x01"
        struct.pack_into("<H", elf, 18, 8)   # ELF32 MIPS
        struct.pack_into("<I", elf, 32, 64)  # section headers
        struct.pack_into("<HH", elf, 46, 40, len(ANCHORS) + 1)
        offset = 256
        for i, (_, address, length) in enumerate(ANCHORS, 1):
            section = 64 + i * 40
            struct.pack_into("<IIIIIIIIII", elf, section,
                             0, 1, 2, address, offset, length, 0, 0, 1, 0)
            exe_off = PSX_HEADER + address - LOAD_VRAM
            elf[offset:offset + length] = executable[exe_off:exe_off + length]
            offset += length
        self.elf = self.root / "build" / (EXE + ".elf")
        self.elf.parent.mkdir()
        self.elf.write_bytes(elf)
        folder = self.root / "assets"
        folder.mkdir()
        # Synthetic generator shares the same CLI contract as the pinned
        # public original tool. Only its fixture hash is mocked, NEVER in
        # production: the real tool requires the pinned source Git blob.
        generator = self.root / "platform/pc/tools/gen_psx_includes.py"
        generator.parent.mkdir(parents=True)
        source = """#!/usr/bin/env python3
import pathlib, sys
source = pathlib.Path(sys.argv[1]).read_bytes()
dest = pathlib.Path(sys.argv[2])
dest.mkdir(parents=True, exist_ok=True)
for name, offset, size in [
    ("801009bc.inc", 0x0f11bc, 304 * 4),
    ("80100e9c.inc", 0x0f169c, 304),
    ("801012e4.inc", 0x0f1ae4, 128 * 9)]:
    raw = source[offset:offset+size]
    (dest / name).write_text(raw.hex() + "\\n", encoding="utf-8")
"""
        generator.write_text(source, encoding="utf-8")
        self.generator_hash = patch(
            "tools.check_map02_original_inc_provenance.GENERATOR_BLOB_SHA1",
            _original_blob_sha1(generator.read_bytes()))
        self.generator_hash.start()
        self.addCleanup(self.generator_hash.stop)
        import subprocess
        subprocess.run(
            [__import__("sys").executable, "-I",
             str(generator), str(self.exe), str(folder)],
            check=True, capture_output=True, timeout=15)
        self.generator = generator
        self.krom = self.root / "external/psy-q/3.6/PSYQ/BIN/KROMDAT.BIN"
        self.krom.parent.mkdir(parents=True)
        self.glyph = bytes([i % 251 for i in range(FONT_LENGTH)])
        self.krom.write_bytes(self.glyph)
        self.exehash = patch(
            "tools.check_map02_private_pc_inputs.US_EXE_MD5",
            hashlib.md5(self.exe.read_bytes()).hexdigest())
        self.fonthash = patch(
            "tools.check_map02_private_pc_inputs.US_FONT_SHA256",
            hashlib.sha256(self.glyph).hexdigest())
        self.exehash.start()
        self.fonthash.start()
        self.addCleanup(self.exehash.stop)
        self.addCleanup(self.fonthash.stop)

    def test_synthetic_US_input_bundle_passes_structure_only(self):
        report = verify_private_pc_inputs(self.root)
        self.assertEqual(report["private_original_input_categories_checked"], 6)
        self.assertEqual(report["original_resource_includes_present"], 3)
        self.assertEqual(len(report["private_build_inputs_binding_sha256"]), 64)
        self.assertFalse(report["full_pc_game_executable_linked"])
        self.assertFalse(report["original_map02_rendering_proven"])

    def test_wrong_executable_md5_blocks_faked_region(self):
        self.exe.write_bytes(self.exe.read_bytes() + b"altered")
        with self.assertRaisesRegex(ValueError, "pinned retail identity"):
            verify_private_pc_inputs(self.root)

    def test_psx_exe_truncation_and_invalid_header(self):
        original = self.exe.read_bytes()
        self.exe.write_bytes(original[:0x800])
        with self.assertRaisesRegex(ValueError, "truncated"):
            verify_private_pc_inputs(self.root)
        self.exe.write_bytes(b"invalid-exe" + original[11:])
        with self.assertRaisesRegex(ValueError, "not a PS-X EXE"):
            verify_private_pc_inputs(self.root)

    def test_three_original_map_and_font_ranges_are_byte_identical(self):
        detail = compare_data_ranges(self.exe, self.elf)
        self.assertEqual(detail["original_private_data_bytes_compared"], 1216)
        self.assertTrue(detail["original_exe_and_mips_elf_data_anchors_match"])
        self.assertFalse(detail["complete_matching_decomp_proven"])
        report = verify_private_pc_inputs(self.root)
        self.assertEqual(report["original_private_data_bytes_compared"], 1216)

    def test_modified_extracted_map35_bytes_rejected_even_with_valid_elf_header(self):
        changed = bytearray(self.elf.read_bytes())
        # Section 2 is the MAP35 data range; its file offset is fixed by
        # this synthetic fixture and independent of the original retail file.
        section2_offset = struct.unpack_from("<I", changed, 64 + 2 * 40 + 16)[0]
        changed[section2_offset] ^= 1
        self.elf.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "differs from original PS-X data"):
            verify_private_pc_inputs(self.root)

    def test_missing_or_duplicate_elf_data_section_fail_closed(self):
        original = self.elf.read_bytes()
        for section_id in (1, 2, 3):
            with self.subTest(section_id=section_id):
                modified = bytearray(original)
                struct.pack_into("<I", modified, 64 + section_id * 40 + 4, 0)
                self.elf.write_bytes(modified)
                with self.assertRaisesRegex(ValueError, "missing unique data section"):
                    verify_private_pc_inputs(self.root)
        self.elf.write_bytes(original)

    def test_extracted_elf_wrong_machine_fails_closed(self):
        wrong = bytearray(self.elf.read_bytes())
        wrong[18:20] = (62).to_bytes(2, "little")
        self.elf.write_bytes(wrong)
        with self.assertRaisesRegex(ValueError, "not a MIPS"):
            verify_private_pc_inputs(self.root)

    def test_deleted_or_symlinked_extracted_asset_rejected(self):
        missing = self.root / "assets" / ASSETS[0]
        original = missing.read_bytes()
        missing.unlink()
        with self.assertRaisesRegex(ValueError, "missing or linked"):
            verify_private_pc_inputs(self.root)
        missing.symlink_to(self.root / "assets" / ASSETS[1])
        with self.assertRaisesRegex(ValueError, "missing or linked"):
            verify_private_pc_inputs(self.root)
        missing.unlink()
        missing.write_bytes(original)
        self.assertTrue(verify_private_pc_inputs(self.root)["us_ps1_font_charset_verified"])

    def test_wrong_or_short_ps1_krom_font_rejected(self):
        self.krom.write_bytes(self.glyph[:-1])
        with self.assertRaisesRegex(ValueError, "font charset"):
            verify_private_pc_inputs(self.root)
        self.krom.write_bytes(b"?" * FONT_LENGTH)
        with self.assertRaisesRegex(ValueError, "font charset"):
            verify_private_pc_inputs(self.root)

    def test_user_owned_full_bios_source_supported(self):
        owned = self.root / "owned-bios.bin"
        bios = bytearray(BIOS_SIZE)
        bios[FONT_BIOS_OFFSET:FONT_BIOS_OFFSET + len(self.glyph)] = self.glyph
        owned.write_bytes(bios)
        result = verify_private_pc_inputs(self.root, krom_source=owned)
        self.assertTrue(result["us_ps1_font_charset_verified"])
        self.assertNotEqual(
            result["private_build_inputs_binding_sha256"],
            verify_private_pc_inputs(self.root)["private_build_inputs_binding_sha256"])

    def test_asset_file_changed_in_place_is_rejected_not_merely_rehashed(self):
        first = verify_private_pc_inputs(self.root)
        self.assertTrue(first["original_resource_includes_match_owned_us_exe"])
        asset = self.root / "assets" / ASSETS[-1]
        asset.write_bytes(asset.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "include differs"):
            verify_private_pc_inputs(self.root)

    def test_exact_original_generator_byte_identity_required(self):
        self.assertEqual(check_original_includes(self.root)[
            "asset_includes_regenerated_and_identical"], 3)
        self.generator.write_text(self.generator.read_text() + "# tamper\\n")
        with self.assertRaisesRegex(ValueError, "differs from pinned source"):
            verify_private_pc_inputs(self.root)

    def test_rejects_altered_map32_include_with_same_length(self):
        path = self.root / "assets" / ASSETS[1]
        old = path.read_bytes()
        path.write_bytes(bytes([old[0] ^ 1]) + old[1:])
        with self.assertRaisesRegex(ValueError, "include differs"):
            verify_private_pc_inputs(self.root)

    def test_no_private_paths_or_bytes_in_error_messages(self):
        self.elf.unlink()
        with self.assertRaises(ValueError) as ex:
            verify_private_pc_inputs(self.root)
        self.assertNotIn(str(self.root), str(ex.exception))
        self.assertNotIn("synthetic asset", str(ex.exception))


if __name__ == "__main__":
    unittest.main()
