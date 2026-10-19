"""Local-only, entirely synthetic original PC resource readiness tests.

No real Vandal Hearts EXE, game asset or BIOS is bundled or accessed.
Real known original hashes are deliberately mocked ONLY inside this file.
"""
import hashlib
import io
from contextlib import redirect_stderr
import os
import struct
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import tools.check_map02_original_extraction_anchors as anchor_inputs
import tools.check_map02_private_pc_inputs as private_inputs

from tools.check_map02_private_pc_inputs import (
    ASSETS, BIOS_SIZE, EXE, FONT_BIOS_OFFSET, FONT_LENGTH,
    verify_private_pc_inputs,
)
from tools.check_map02_original_extraction_anchors import (
    ANCHORS, LOAD_VRAM, PSX_HEADER, compare_data_ranges,
    compare_loaded_sections,
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
        elf[:7] = b"\x7fELF\x01\x01\x01"
        struct.pack_into("<H", elf, 18, 8)   # ELF32 MIPS
        struct.pack_into("<I", elf, 20, 1)   # current ELF header version
        struct.pack_into("<H", elf, 40, 52)  # ELF32 file header size
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
        # The production check pins the real, public upstream KROM-to-C
        # generator. The fixture uses a synthetic source and test-only hash.
        self.font_generator = self.root / private_inputs.FONT_GENERATOR
        self.font_generator.write_text(
            "#!/usr/bin/env python3\\n# synthetic font fixture\\n",
            encoding="utf-8")
        self.font_generator_hash = patch(
            "tools.check_map02_private_pc_inputs.FONT_GENERATOR_BLOB_SHA1",
            _original_blob_sha1(self.font_generator.read_bytes()))
        self.font_generator_hash.start()
        self.addCleanup(self.font_generator_hash.stop)
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

    def add_synthetic_loaded_section(self, address=None, *, size=16):
        """Append one initialized section without relying on copyrighted data."""
        if address is None:
            address = LOAD_VRAM + 0x100
        original = bytearray(self.elf.read_bytes())
        old_shoff = struct.unpack_from("<I", original, 32)[0]
        old_count = struct.unpack_from("<H", original, 48)[0]
        headers = bytearray(original[old_shoff:old_shoff + old_count * 40])
        data_offset = len(original)
        exe_offset = PSX_HEADER + address - LOAD_VRAM
        data = self.exe.read_bytes()[exe_offset:exe_offset + size]
        if len(data) != size:
            data = bytes(size)
        original.extend(data)
        new_shoff = len(original)
        headers.extend(bytes(40))
        struct.pack_into("<IIIIIIIIII", headers, old_count * 40,
                         0, 1, 2, address, data_offset, size, 0, 0, 1, 0)
        original.extend(headers)
        struct.pack_into("<I", original, 32, new_shoff)
        struct.pack_into("<H", original, 48, old_count + 1)
        self.elf.write_bytes(original)
        return data_offset

    def test_all_mapped_initialized_sections_checked_beyond_three_anchors(self):
        default = compare_loaded_sections(self.exe, self.elf)
        self.assertEqual(default["original_allocated_sections_compared"], 3)
        self.assertEqual(default["original_allocated_section_bytes_compared"], 1216)
        self.assertEqual(default["unmapped_allocated_sections_not_authenticated"], 0)
        extra = self.add_synthetic_loaded_section()
        report = verify_private_pc_inputs(self.root)
        self.assertTrue(report["original_exe_and_mips_elf_loaded_sections_match"])
        self.assertEqual(report["original_allocated_sections_compared"], 4)
        self.assertEqual(report["original_allocated_section_bytes_compared"], 1232)
        self.assertFalse(report["original_map02_rendering_proven"])
        tampered = bytearray(self.elf.read_bytes())
        tampered[extra] ^= 0x80
        self.elf.write_bytes(tampered)
        # The three original named anchors still match, but a fourth
        # ordinary loaded section must block the full private preflight.
        self.assertTrue(compare_data_ranges(self.exe, self.elf)[
            "original_exe_and_mips_elf_data_anchors_match"])
        with self.assertRaisesRegex(ValueError, "loaded section differs"):
            verify_private_pc_inputs(self.root)

    def test_large_loaded_section_checks_every_64k_chunk(self):
        offset = self.add_synthetic_loaded_section(size=70000)
        result = compare_loaded_sections(self.exe, self.elf)
        self.assertEqual(result["original_allocated_sections_compared"], 4)
        self.assertEqual(result["original_allocated_section_bytes_compared"], 71216)
        bad = bytearray(self.elf.read_bytes())
        bad[offset + 66000] ^= 1
        self.elf.write_bytes(bad)
        with self.assertRaisesRegex(ValueError, "loaded section differs"):
            compare_loaded_sections(self.exe, self.elf)

    def test_no_mapped_original_elf_sections_fails_closed(self):
        changed = bytearray(self.elf.read_bytes())
        for index in range(1, 4):
            struct.pack_into("<I", changed, 64 + index * 40 + 8, 0)
        self.elf.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "no mapped initialized"):
            compare_loaded_sections(self.exe, self.elf)

    def test_coverage_counters_do_not_inflate_sparse_extraction(self):
        payload_size = len(self.exe.read_bytes()) - PSX_HEADER
        summary = compare_loaded_sections(self.exe, self.elf)
        self.assertEqual(summary["original_psx_loaded_payload_bytes"], payload_size)
        self.assertEqual(
            summary["original_psx_loaded_bytes_not_covered_by_elf_sections"],
            payload_size - 1216)
        self.assertFalse(summary["original_psx_loaded_payload_fully_covered"])
        self.assertEqual(summary["original_psx_uncovered_contiguous_spans"], 4)
        self.assertGreater(summary["original_psx_largest_uncovered_span_bytes"], 0)
        ready = verify_private_pc_inputs(self.root)
        for key in ("original_psx_loaded_payload_bytes",
                    "original_psx_loaded_bytes_not_covered_by_elf_sections",
                    "original_psx_loaded_payload_fully_covered",
                    "original_psx_uncovered_contiguous_spans",
                    "original_psx_largest_uncovered_span_bytes"):
            self.assertEqual(ready[key], summary[key])
        self.assertFalse(ready["original_map02_rendering_proven"])

    def test_full_payload_coverage_requires_one_nonoverlapping_section(self):
        size = len(self.exe.read_bytes()) - PSX_HEADER
        self.add_synthetic_loaded_section(LOAD_VRAM, size=size)
        elf = bytearray(self.elf.read_bytes())
        table = struct.unpack_from("<I", elf, 32)[0]
        # Remove the three tiny sections: the new ELF contains only one
        # contiguous initialized runtime section covering the whole image.
        for index in (1, 2, 3):
            struct.pack_into("<I", elf, table + index * 40 + 4, 0)
        self.elf.write_bytes(elf)
        report = compare_loaded_sections(self.exe, self.elf)
        self.assertEqual(report["original_allocated_sections_compared"], 1)
        self.assertEqual(report["original_allocated_section_bytes_compared"], size)
        self.assertEqual(
            report["original_psx_loaded_bytes_not_covered_by_elf_sections"], 0)
        self.assertTrue(report["original_psx_loaded_payload_fully_covered"])
        self.assertEqual(report["original_psx_uncovered_contiguous_spans"], 0)
        self.assertEqual(report["original_psx_largest_uncovered_span_bytes"], 0)
        self.assertFalse(report["complete_matching_decomp_proven"])

    def test_uncovered_span_counts_only_real_address_gaps(self):
        baseline = compare_loaded_sections(self.exe, self.elf)
        self.assertEqual(baseline["original_psx_uncovered_contiguous_spans"], 4)
        # Add a section directly after MAP32: contiguous coverage must
        # not manufacture a new uncovered address gap.
        self.add_synthetic_loaded_section(ANCHORS[0][1] + ANCHORS[0][2])
        adjacent = compare_loaded_sections(self.exe, self.elf)
        self.assertEqual(adjacent["original_psx_uncovered_contiguous_spans"], 4)
        self.assertEqual(
            adjacent["original_psx_loaded_bytes_not_covered_by_elf_sections"],
            baseline["original_psx_loaded_bytes_not_covered_by_elf_sections"] - 16)

    def test_disjoint_extra_section_splits_one_uncovered_span(self):
        initial = compare_loaded_sections(self.exe, self.elf)
        self.add_synthetic_loaded_section(ANCHORS[0][1] + ANCHORS[0][2] + 16)
        split = compare_loaded_sections(self.exe, self.elf)
        self.assertEqual(split["original_psx_uncovered_contiguous_spans"],
                         initial["original_psx_uncovered_contiguous_spans"] + 1)
        self.assertFalse(split["original_psx_loaded_payload_fully_covered"])

    def test_loaded_section_cannot_alias_elf_header_or_section_table(self):
        source = self.elf.read_bytes()
        # Exercise a syntactically valid allocated PROGBITS entry whose
        # contents point into ELF metadata rather than runtime bytes.
        first_section_offset_field = 64 + 40 + 16
        for name, alias_offset in (
            ("ELF file header", 0),
            ("ELF section table", 64),
            ("crossing section table boundary", 208),
        ):
            with self.subTest(case=name):
                forged = bytearray(source)
                struct.pack_into(
                    "<I", forged, first_section_offset_field, alias_offset)
                self.elf.write_bytes(forged)
                with self.assertRaisesRegex(ValueError, "aliases ELF metadata"):
                    compare_loaded_sections(self.exe, self.elf)
        self.elf.write_bytes(source)
        self.assertTrue(compare_loaded_sections(self.exe, self.elf)[
            "original_exe_and_mips_elf_loaded_sections_match"])

    def test_elf_program_header_table_cannot_impersonate_runtime_bytes(self):
        # The fixture has unused padding immediately before its first
        # initialized section. Declare that padding a 32-byte ELF32
        # program-header table: the ordinary sections must still pass.
        valid = bytearray(self.elf.read_bytes())
        struct.pack_into("<I", valid, 28, 224)  # e_phoff
        struct.pack_into("<HH", valid, 42, 32, 1)  # e_phentsize, e_phnum
        self.elf.write_bytes(valid)
        self.assertTrue(compare_loaded_sections(self.exe, self.elf)[
            "original_exe_and_mips_elf_loaded_sections_match"])

        # Keep all three pinned original anchor sections intact. Forge
        # a fourth, otherwise source-matching section in the same PS-X
        # load image, but redirect its bytes into the program-header table.
        self.add_synthetic_loaded_section()
        forged = bytearray(self.elf.read_bytes())
        table = struct.unpack_from("<I", forged, 32)[0]
        struct.pack_into("<I", forged, table + 4 * 40 + 16, 240)
        self.elf.write_bytes(forged)
        self.assertTrue(compare_data_ranges(self.exe, self.elf)[
            "original_exe_and_mips_elf_data_anchors_match"])
        with self.assertRaisesRegex(ValueError, "aliases ELF metadata"):
            compare_loaded_sections(self.exe, self.elf)
        with self.assertRaisesRegex(ValueError, "aliases ELF metadata"):
            verify_private_pc_inputs(self.root)

    def test_corrupt_elf32_header_version_or_size_blocks_full_input_preflight(self):
        source = self.elf.read_bytes()
        for description, offset, width, changed in (
            ("e_ident version", 6, 1, 0),
            ("e_version", 20, 4, 2),
            ("e_ehsize", 40, 2, 51),
        ):
            with self.subTest(description=description):
                forged = bytearray(source)
                forged[offset:offset + width] = changed.to_bytes(width, "little")
                self.elf.write_bytes(forged)
                self.assertTrue(compare_data_ranges(self.exe, self.elf)[
                    "original_exe_and_mips_elf_data_anchors_match"])
                with self.assertRaisesRegex(
                    ValueError, "invalid header version or size"
                ):
                    compare_loaded_sections(self.exe, self.elf)
                with self.assertRaisesRegex(
                    ValueError, "invalid header version or size"
                ):
                    verify_private_pc_inputs(self.root)
        self.elf.write_bytes(source)

    def test_overlapping_elf_program_and_section_tables_rejected(self):
        source = self.elf.read_bytes()
        forged = bytearray(source)
        # Section header table occupies [64, 224). A 32-byte program
        # header table beginning at 208 overlaps its final 16 bytes.
        struct.pack_into("<I", forged, 28, 208)
        struct.pack_into("<HH", forged, 42, 32, 1)
        self.elf.write_bytes(forged)
        with self.assertRaisesRegex(ValueError, "header tables overlap"):
            compare_loaded_sections(self.exe, self.elf)
        self.elf.write_bytes(source)
        self.assertTrue(compare_loaded_sections(self.exe, self.elf)[
            "original_exe_and_mips_elf_loaded_sections_match"])

    def test_malformed_elf_program_header_table_fails_closed(self):
        original = self.elf.read_bytes()
        for name, phoff, entsize, count in (
            ("table inside ELF file header", 32, 32, 1),
            ("undersized program header entry", 224, 31, 1),
            ("table beyond end of file", len(original) - 16, 32, 1),
        ):
            with self.subTest(name=name):
                forged = bytearray(original)
                struct.pack_into("<I", forged, 28, phoff)
                struct.pack_into("<HH", forged, 42, entsize, count)
                self.elf.write_bytes(forged)
                with self.assertRaisesRegex(
                    ValueError, "program header table is invalid"
                ):
                    compare_loaded_sections(self.exe, self.elf)

    def test_private_preflight_rejects_metadata_alias_even_with_correct_anchors(self):
        original = bytearray(self.elf.read_bytes())
        # Preserve the three pinned data ranges but inject a fourth section
        # mapped at a distinct PS-X address with an offset into the ELF
        # section-header table. A separately valid anchor report is not
        # enough to allow the complete private input preflight.
        self.add_synthetic_loaded_section()
        forged = bytearray(self.elf.read_bytes())
        table = struct.unpack_from("<I", forged, 32)[0]
        struct.pack_into("<I", forged, table + 4 * 40 + 16, table)
        self.elf.write_bytes(forged)
        self.assertTrue(compare_data_ranges(self.exe, self.elf)[
            "original_exe_and_mips_elf_data_anchors_match"])
        with self.assertRaisesRegex(ValueError, "aliases ELF metadata"):
            verify_private_pc_inputs(self.root)

    def test_distinct_runtime_sections_cannot_reuse_same_elf_file_bytes(self):
        # The fixture bytes repeat every 256 addresses. Two distinct PS-X
        # ranges can match identically without proving that the extracted
        # ELF contains two independent file-backed sections.
        first_address = ANCHORS[0][1]
        first_file_offset = struct.unpack_from(
            "<I", self.elf.read_bytes(), 64 + 40 + 16)[0]
        original = self.exe.read_bytes()
        base = self.elf.read_bytes()
        for shift, alias_offset in (
            (0, first_file_offset), (8, first_file_offset + 8),
        ):
            with self.subTest(shift=shift):
                # Restore the original synthetic ELF before each case, so
                # the fourth section is the only intentional modification.
                self.elf.write_bytes(base)
                other_address = first_address + 256 + shift
                old_start = PSX_HEADER + first_address - LOAD_VRAM + shift
                new_start = PSX_HEADER + other_address - LOAD_VRAM
                self.assertEqual(
                    original[old_start:old_start + 16],
                    original[new_start:new_start + 16])
                self.add_synthetic_loaded_section(
                    other_address, size=16)
                fresh = compare_loaded_sections(self.exe, self.elf)
                self.assertEqual(fresh["original_allocated_sections_compared"], 4)
                forged = bytearray(self.elf.read_bytes())
                table = struct.unpack_from("<I", forged, 32)[0]
                struct.pack_into(
                    "<I", forged, table + 4 * 40 + 16, alias_offset)
                self.elf.write_bytes(forged)
                # Original three anchors have not changed. Only the
                # expanded verifier sees the disk-payload alias.
                self.assertTrue(compare_data_ranges(self.exe, self.elf)[
                    "original_exe_and_mips_elf_data_anchors_match"])
                with self.assertRaisesRegex(
                    ValueError, "overlap file payload"
                ):
                    compare_loaded_sections(self.exe, self.elf)
                with self.assertRaisesRegex(
                    ValueError, "overlap file payload"
                ):
                    verify_private_pc_inputs(self.root)

    def test_mapped_section_overlap_and_boundary_rejected(self):
        self.add_synthetic_loaded_section(ANCHORS[0][1], size=16)
        with self.assertRaisesRegex(ValueError, "overlapping allocated"):
            compare_loaded_sections(self.exe, self.elf)
        # Reset to the original synthetic ELF structure by removing the
        # newly appended duplicate section header from the index.
        elf = bytearray(self.elf.read_bytes())
        shoff = struct.unpack_from("<I", elf, 32)[0]
        struct.pack_into("<I", elf, shoff + 4 * 40 + 12,
                         LOAD_VRAM + len(self.exe.read_bytes()) - PSX_HEADER - 4)
        self.elf.write_bytes(elf)
        with self.assertRaisesRegex(ValueError, "crosses PS-X extent"):
            compare_loaded_sections(self.exe, self.elf)

    def test_unmapped_allocated_section_is_not_claimed_authenticated(self):
        self.add_synthetic_loaded_section(LOAD_VRAM + 0x02000000, size=16)
        report = compare_loaded_sections(self.exe, self.elf)
        self.assertEqual(report["original_allocated_sections_compared"], 3)
        self.assertEqual(report["original_allocated_section_bytes_compared"], 1216)
        self.assertEqual(report["unmapped_allocated_sections_not_authenticated"], 1)
        self.assertFalse(report["complete_matching_decomp_proven"])

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

    def test_anchor_rejects_bytes_past_declared_psx_load_even_if_file_contains_them(self):
        # The file still carries all original synthetic anchor bytes, but
        # the PS-X header explicitly stops one byte before the last anchor.
        original = bytearray(self.exe.read_bytes())
        last_address, last_length = ANCHORS[-1][1:]
        truncated_load = last_address - LOAD_VRAM + last_length - 1
        struct.pack_into("<I", original, 0x1c, truncated_load)
        self.exe.write_bytes(original)
        with self.assertRaisesRegex(ValueError, "past declared load image"):
            compare_data_ranges(self.exe, self.elf)
        # Even a test-only updated retail digest cannot bypass that
        # independent structural comparison in the full local preflight.
        with patch.object(private_inputs, "US_EXE_MD5",
                          hashlib.md5(self.exe.read_bytes()).hexdigest()):
            with self.assertRaisesRegex(ValueError, "past declared load image"):
                verify_private_pc_inputs(self.root)

    def test_both_private_extractors_reject_zero_or_truncated_psx_load_extent(self):
        original = self.exe.read_bytes()
        for declared in (0, len(original) - PSX_HEADER + 1):
            with self.subTest(declared_payload=declared):
                edited = bytearray(original)
                struct.pack_into("<I", edited, 0x1c, declared)
                self.exe.write_bytes(edited)
                for verifier in (compare_data_ranges, compare_loaded_sections):
                    with self.assertRaisesRegex(ValueError, "invalid load extent"):
                        verifier(self.exe, self.elf)
        self.exe.write_bytes(original)

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

    def test_original_elf_rejects_nonallocated_data_anchor(self):
        changed = bytearray(self.elf.read_bytes())
        # ELF32 sh_flags for the MAP32 section (section index 1).
        struct.pack_into("<I", changed, 64 + 40 + 8, 0)
        self.elf.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "missing unique data section"):
            compare_data_ranges(self.exe, self.elf)

    def test_nonallocated_shadow_section_cannot_impersonate_original_data(self):
        # Reuse the null section-header slot to introduce a byte-identical
        # but non-allocated PROGBITS section at an original MIPS data address.
        # A debug section is not a valid retail-runtime source mapping.
        original = self.elf.read_bytes()
        shadow = bytearray(original)
        _, address, length = ANCHORS[0]
        struct.pack_into("<IIIIIIIIII", shadow, 64, 0, 1, 0,
                         address, 256, length, 0, 0, 1, 0)
        self.elf.write_bytes(shadow)
        self.assertTrue(compare_data_ranges(self.exe, self.elf)[
            "original_exe_and_mips_elf_data_anchors_match"])
        # Making the same section allocated makes the mapping ambiguous.
        struct.pack_into("<I", shadow, 64 + 8, 2)
        self.elf.write_bytes(shadow)
        with self.assertRaisesRegex(ValueError, "missing unique data section"):
            compare_data_ranges(self.exe, self.elf)

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

    def test_include_generator_executes_verified_private_source_and_exe_snapshots(self):
        real_run = subprocess.run

        def inspect_snapshots(argv, **kwargs):
            self.assertEqual(argv[1], "-I")
            script, exe_copy, output = map(Path, argv[2:5])
            self.assertNotEqual(script, self.generator)
            self.assertNotEqual(exe_copy, self.exe)
            self.assertEqual(script.read_bytes(), self.generator.read_bytes())
            self.assertEqual(exe_copy.read_bytes(), self.exe.read_bytes())
            self.assertEqual(script.stat().st_mode & 0o777, 0o600)
            self.assertEqual(exe_copy.stat().st_mode & 0o777, 0o600)
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            self.assertTrue(all(str(p).startswith(str(script.parent))
                                for p in (exe_copy, output)))
            return real_run(argv, **kwargs)

        with patch("tools.check_map02_original_inc_provenance.subprocess.run",
                   side_effect=inspect_snapshots):
            self.assertEqual(check_original_includes(self.root)[
                "asset_includes_regenerated_and_identical"], 3)

    def test_executable_replaced_during_generation_fails_even_if_include_bytes_match(self):
        real_run = subprocess.run

        def replace_exe(argv, **kwargs):
            original = self.exe.read_bytes()
            self.exe.unlink()
            self.exe.write_bytes(original)
            return real_run(argv, **kwargs)

        with patch("tools.check_map02_original_inc_provenance.subprocess.run",
                   side_effect=replace_exe):
            with self.assertRaisesRegex(ValueError, "executable changed"):
                check_original_includes(self.root)

    def test_includes_replaced_with_identical_bytes_during_generation_fail(self):
        real_run = subprocess.run
        asset = self.root / "assets" / ASSETS[0]

        def replace_asset(argv, **kwargs):
            original = asset.read_bytes()
            asset.unlink()
            asset.write_bytes(original)
            return real_run(argv, **kwargs)

        with patch("tools.check_map02_original_inc_provenance.subprocess.run",
                   side_effect=replace_asset):
            with self.assertRaisesRegex(ValueError, "include changed"):
                check_original_includes(self.root)

    def test_generator_changed_during_generation_cannot_be_executed(self):
        real_run = subprocess.run
        verified_source = self.generator.read_bytes()

        def replace_generator(argv, **kwargs):
            self.generator.write_bytes(b"raise SystemExit('replaced')\\n")
            # Child sees only the earlier SHA-verified script copy.
            self.assertEqual(Path(argv[2]).read_bytes(), verified_source)
            result = real_run(argv, **kwargs)
            self.assertEqual(result.returncode, 0)
            return result

        with patch("tools.check_map02_original_inc_provenance.subprocess.run",
                   side_effect=replace_generator):
            with self.assertRaisesRegex(ValueError, "generator changed"):
                check_original_includes(self.root)

    def test_elf_replaced_during_anchored_descriptor_read_is_rejected(self):
        real_pread = os.pread
        swapped = [False]

        def swap_after_elf_header(fd, size, offset):
            contents = real_pread(fd, size, offset)
            if size == 52 and offset == 0 and not swapped[0]:
                swapped[0] = True
                original = self.elf.read_bytes()
                self.elf.unlink()
                self.elf.write_bytes(original)
            return contents

        with patch("tools.check_map02_original_extraction_anchors.os.pread",
                   side_effect=swap_after_elf_header):
            with self.assertRaisesRegex(ValueError, "extraction input changed"):
                compare_data_ranges(self.exe, self.elf)
        self.assertTrue(swapped[0])

    def test_original_exe_in_place_change_during_anchor_read_is_rejected(self):
        real_pread = os.pread
        mutated = [False]

        def modify_after_first_data_anchor(fd, size, offset):
            contents = real_pread(fd, size, offset)
            if size == 32 and not mutated[0]:
                mutated[0] = True
                data = bytearray(self.exe.read_bytes())
                data[0x100] ^= 1  # outside the anchored image bytes
                self.exe.write_bytes(data)
            return contents

        with patch("tools.check_map02_original_extraction_anchors.os.pread",
                   side_effect=modify_after_first_data_anchor):
            with self.assertRaisesRegex(ValueError, "extraction input changed"):
                compare_data_ranges(self.exe, self.elf)
        self.assertTrue(mutated[0])

    def test_original_extraction_rejects_symlinked_elf_directly(self):
        original = self.elf.read_bytes()
        target = self.elf.with_name("original-private-elf")
        target.write_bytes(original)
        self.elf.unlink()
        self.elf.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "linked original extraction"):
            compare_data_ranges(self.exe, self.elf)

    def test_extracted_elf_changed_after_anchor_pass_is_rejected(self):
        original_font = private_inputs._krom_font

        def mutate_elf_during_font(path):
            data = bytearray(self.elf.read_bytes())
            # A padding byte outside all 1216 anchored bytes: the three
            # anchor comparisons still pass but this ELF is NOT the one
            # whose original SHA-256 was placed in the token set.
            data[56] ^= 1
            self.elf.write_bytes(data)
            return original_font(path)

        with patch.object(private_inputs, "_krom_font",
                          side_effect=mutate_elf_during_font):
            with self.assertRaisesRegex(ValueError, "private original input changed"):
                verify_private_pc_inputs(self.root)

    def test_identical_elf_inode_swap_after_anchor_pass_is_rejected(self):
        original_font = private_inputs._krom_font

        def swap_elf_during_font(path):
            data = self.elf.read_bytes()
            self.elf.unlink()
            self.elf.write_bytes(data)
            return original_font(path)

        with patch.object(private_inputs, "_krom_font",
                          side_effect=swap_elf_during_font):
            with self.assertRaisesRegex(ValueError, "private original input changed"):
                verify_private_pc_inputs(self.root)

    def test_identical_include_inode_swap_after_regeneration_is_rejected(self):
        original_font = private_inputs._krom_font
        asset = self.root / "assets" / ASSETS[0]

        def swap_include_during_font(path):
            data = asset.read_bytes()
            asset.unlink()
            asset.write_bytes(data)
            return original_font(path)

        with patch.object(private_inputs, "_krom_font",
                          side_effect=swap_include_during_font):
            with self.assertRaisesRegex(ValueError, "private original input changed"):
                verify_private_pc_inputs(self.root)

    def test_identical_retail_exe_swap_after_regeneration_is_rejected(self):
        original_font = private_inputs._krom_font

        def swap_owned_exe_during_font(path):
            data = self.exe.read_bytes()
            self.exe.unlink()
            self.exe.write_bytes(data)
            return original_font(path)

        with patch.object(private_inputs, "_krom_font",
                          side_effect=swap_owned_exe_during_font):
            with self.assertRaisesRegex(ValueError, "private original input changed"):
                verify_private_pc_inputs(self.root)

    def test_original_checkout_symlinked_parent_fails_before_regeneration(self):
        # No retail image, BIOS or original resource is used here; these
        # test fixtures are generated in setUp from arbitrary synthetic bytes.
        for relative in (
            "assets", "build", "platform/pc/tools",
            "external/psy-q/3.6/PSYQ/BIN",
        ):
            with self.subTest(relative=relative):
                parent = self.root / relative
                archived = self.root.parent / (
                    "moved-original-" + relative.replace("/", "-"))
                parent.rename(archived)
                parent.symlink_to(archived, target_is_directory=True)
                try:
                    with patch.object(private_inputs, "check_original_includes") as regenerate:
                        with self.assertRaisesRegex(
                                ValueError, "directory linked or inaccessible"):
                            verify_private_pc_inputs(self.root)
                    regenerate.assert_not_called()
                finally:
                    parent.unlink()
                    archived.rename(parent)
        self.assertTrue(
            verify_private_pc_inputs(self.root)["us_ps1_font_charset_verified"])

    def test_default_krom_checkout_symlink_differs_from_explicit_owned_override(self):
        overridden = self.root.parent / "owned-synthetic-krom.bin"
        overridden.write_bytes(self.glyph)
        folder = self.root / "external/psy-q"
        saved = self.root.parent / "redirected-default-krom-parent"
        folder.rename(saved)
        folder.symlink_to(saved, target_is_directory=True)
        try:
            with self.assertRaisesRegex(
                    ValueError, "directory linked or inaccessible"):
                verify_private_pc_inputs(self.root)
            # User-provided --krom-source does not have to live in the
            # checkout. Its bytes are independently validated by _krom_font.
            result = verify_private_pc_inputs(
                self.root, krom_source=overridden)
            self.assertTrue(result["us_ps1_font_charset_verified"])
        finally:
            folder.unlink()
            saved.rename(folder)

    def test_original_source_parent_requires_owner_search_permission(self):
        folder = self.root / "assets"
        old_mode = folder.stat().st_mode & 0o777
        folder.chmod(0o600)
        try:
            with patch.object(private_inputs, "check_original_includes") as regenerate:
                with self.assertRaisesRegex(
                        ValueError, "directory linked or inaccessible"):
                    verify_private_pc_inputs(self.root)
            regenerate.assert_not_called()
        finally:
            folder.chmod(old_mode)

    def test_private_input_cli_valueerror_redacts_owned_path(self):
        output = io.StringIO()
        for problem in (
            ValueError("source root rejected " + str(self.root)),
            ValueError("private owned executable rejected " + str(self.exe)),
        ):
            with self.subTest(problem=type(problem).__name__):
                output = io.StringIO()
                with patch("sys.argv", ["private-inputs", str(self.root)]), \
                        patch.object(private_inputs, "verify_private_pc_inputs",
                                     side_effect=problem), \
                        redirect_stderr(output):
                    with self.assertRaises(SystemExit) as caught:
                        private_inputs.main()
                self.assertEqual(caught.exception.code, 2)
                self.assertIn(
                    "private original input verification failed",
                    output.getvalue())
                self.assertNotIn(str(self.root), output.getvalue())

    def test_private_input_cli_oserror_redacts_owned_path(self):
        output = io.StringIO()
        with patch("sys.argv", ["private-inputs", str(self.root)]), \
                patch.object(private_inputs, "verify_private_pc_inputs",
                             side_effect=OSError("private: " + str(self.exe))), \
                redirect_stderr(output):
            with self.assertRaises(SystemExit) as ex:
                private_inputs.main()
        self.assertEqual(ex.exception.code, 2)
        self.assertIn("private original input verification failed", output.getvalue())
        self.assertNotIn(str(self.root), output.getvalue())

    def test_original_anchor_cli_oserror_redacts_owned_path(self):
        output = io.StringIO()
        with patch("sys.argv", ["extract-anchors", str(self.exe), str(self.elf)]), \
                patch.object(anchor_inputs, "compare_data_ranges",
                             side_effect=OSError("private: " + str(self.elf))), \
                redirect_stderr(output):
            with self.assertRaises(SystemExit) as ex:
                anchor_inputs.main()
        self.assertEqual(ex.exception.code, 2)
        self.assertIn("filesystem verification failed", output.getvalue())
        self.assertNotIn(str(self.root), output.getvalue())

    def test_font_generator_is_bound_to_pinned_public_source(self):
        result = verify_private_pc_inputs(self.root)
        self.assertTrue(result["pinned_original_font_generator_verified"])
        self.font_generator.write_text(
            self.font_generator.read_text() + "# altered\\n",
            encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "font generator differs from pinned source"):
            verify_private_pc_inputs(self.root)

    def test_symlinked_original_font_generator_rejected(self):
        original = self.font_generator.read_bytes()
        backup = self.font_generator.with_name("synthetic-font-generator-source")
        backup.write_bytes(original)
        self.font_generator.unlink()
        self.font_generator.symlink_to(backup)
        with self.assertRaisesRegex(ValueError, "missing or linked"):
            verify_private_pc_inputs(self.root)

    def test_identical_font_generator_inode_swap_during_font_audit_rejected(self):
        original_font = private_inputs._krom_font

        def replace_source_during_font_read(path):
            original = self.font_generator.read_bytes()
            self.font_generator.unlink()
            self.font_generator.write_bytes(original)
            return original_font(path)

        with patch.object(private_inputs, "_krom_font",
                          side_effect=replace_source_during_font_read):
            with self.assertRaisesRegex(ValueError, "original-font-generator"):
                verify_private_pc_inputs(self.root)

    def test_generator_timeout_never_leaks_private_arguments(self):
        secret_path = str(self.exe)
        with patch("tools.check_map02_original_inc_provenance.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(
                       ["python", secret_path], 0.01)):
            with self.assertRaisesRegex(ValueError, "generation timed out") as ex:
                check_original_includes(self.root)
        self.assertNotIn(secret_path, str(ex.exception))
        self.assertNotIn(str(self.root), str(ex.exception))

    def test_generator_launch_error_never_leaks_private_path(self):
        with patch("tools.check_map02_original_inc_provenance.subprocess.run",
                   side_effect=OSError("unavailable: " + str(self.exe))):
            with self.assertRaisesRegex(ValueError, "could not launch") as ex:
                check_original_includes(self.root)
        self.assertNotIn(str(self.root), str(ex.exception))

    def test_no_private_paths_or_bytes_in_error_messages(self):
        self.elf.unlink()
        with self.assertRaises(ValueError) as ex:
            verify_private_pc_inputs(self.root)
        self.assertNotIn(str(self.root), str(ex.exception))
        self.assertNotIn("synthetic asset", str(ex.exception))


if __name__ == "__main__":
    unittest.main()
