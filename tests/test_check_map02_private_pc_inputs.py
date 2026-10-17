"""Local-only, entirely synthetic original PC resource readiness tests.

No real Vandal Hearts EXE, game asset or BIOS is bundled or accessed.
Real known original hashes are deliberately mocked ONLY inside this file.
"""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.check_map02_private_pc_inputs import (
    ASSETS, BIOS_SIZE, EXE, FONT_BIOS_OFFSET, FONT_LENGTH,
    verify_private_pc_inputs,
)


class PrivateOriginalRetailBuildInputsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-map02-original-preflight-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "upstream"
        self.root.mkdir()
        self.exe = self.root / EXE
        header = bytearray(0x800)
        header[:8] = b"PS-X EXE"
        header[0x1c:0x20] = (2048).to_bytes(4, "little")
        self.exe.write_bytes(header + b"x" * 2048)
        elf = bytearray(128)
        elf[:6] = b"\x7fELF\x01\x01"
        elf[18:20] = (8).to_bytes(2, "little")
        self.elf = self.root / "build" / (EXE + ".elf")
        self.elf.parent.mkdir()
        self.elf.write_bytes(elf)
        folder = self.root / "assets"
        folder.mkdir()
        for i, name in enumerate(ASSETS):
            (folder / name).write_bytes(b"synthetic asset " + bytes([i]))
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

    def test_one_asset_byte_changes_combined_private_digest(self):
        first = verify_private_pc_inputs(self.root)
        asset = self.root / "assets" / ASSETS[-1]
        asset.write_bytes(asset.read_bytes() + b"changed")
        again = verify_private_pc_inputs(self.root)
        self.assertNotEqual(first["private_build_inputs_binding_sha256"],
                            again["private_build_inputs_binding_sha256"])

    def test_no_private_paths_or_bytes_in_error_messages(self):
        self.elf.unlink()
        with self.assertRaises(ValueError) as ex:
            verify_private_pc_inputs(self.root)
        self.assertNotIn(str(self.root), str(ex.exception))
        self.assertNotIn("synthetic asset", str(ex.exception))


if __name__ == "__main__":
    unittest.main()
