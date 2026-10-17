"""Tests for exact original glyph bytes in host ELF."""
import unittest
from pathlib import Path
import subprocess
import tempfile
from tools.check_map02_linked_font_elf import check_linked_font_bytes
from tools.check_map02_linked_font_elf import FONT_BYTES

class FontLinkedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='font-elf-test-')
        cls.root = Path(cls.tmp.name)
        cls.expected = bytes((i * 19 + 3) % 251 for i in range(FONT_BYTES))
        source = cls.root / "fixture.c"
        body = ",".join(str(byte) for byte in cls.expected)
        source.write_text("const unsigned char pc_kanji_charset2[6270] = {" +
                          body + "};\nint main(void) { return 0; }\n")
        cls.binary = cls.root / "fixture"
        subprocess.run(["cc", str(source), "-o", str(cls.binary)],
                       check=True, capture_output=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_actual_loaded_font_bytes_match(self):
        result = check_linked_font_bytes(self.binary, self.expected)
        self.assertTrue(result["linked_original_us_font_bytes_match"])
        self.assertFalse(result["original_font_bytes_disclosed"])

    def test_one_byte_change_inside_same_size_font_rejected(self):
        data = bytearray(self.binary.read_bytes())
        offset = data.find(self.expected)
        self.assertGreaterEqual(offset, 0)
        data[offset + 123] ^= 1
        altered = self.root / "changed"
        altered.write_bytes(data)
        altered.chmod(0o700)
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            check_linked_font_bytes(altered, self.expected)

    def test_wrong_expected_font_does_not_validate(self):
        changed = bytes([self.expected[0] ^ 1]) + self.expected[1:]
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            check_linked_font_bytes(self.binary, changed)

    def test_bss_symbol_cannot_claim_initialized_glyphs(self):
        source = self.root / "bss.c"
        source.write_text("unsigned char pc_kanji_charset2[6270];\n"
                          "int main(void) {return 0;}\n")
        executable = self.root / "bss-exe"
        subprocess.run(["cc", str(source), "-o", str(executable)],
                       check=True, capture_output=True, timeout=30)
        with self.assertRaisesRegex(ValueError, "read-only loaded data"):
            check_linked_font_bytes(executable, self.expected)

    def test_shortened_initialized_font_is_rejected(self):
        source = self.root / "short.c"
        source.write_text("const unsigned char pc_kanji_charset2[6269] = {1};\n"
                          "int main(void) {return 0;}\n")
        executable = self.root / "short-exe"
        subprocess.run(["cc", str(source), "-o", str(executable)],
                       check=True, capture_output=True, timeout=30)
        with self.assertRaisesRegex(ValueError, "size differs"):
            check_linked_font_bytes(executable, self.expected)

    def test_stripped_symbol_table_cannot_claim_original_font(self):
        stripped = self.root / "stripped-font"
        stripped.write_bytes(self.binary.read_bytes())
        stripped.chmod(0o700)
        subprocess.run(["strip", "--strip-all", str(stripped)], check=True,
                       capture_output=True, timeout=30)
        with self.assertRaisesRegex(ValueError, "one initialized glyph"):
            check_linked_font_bytes(stripped, self.expected)

    def test_symlinked_linked_font_elf_rejected(self):
        link = self.root / "symbolic-link"
        link.symlink_to(self.binary)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            check_linked_font_bytes(link, self.expected)

    def test_writable_initialized_font_must_not_impersonate_original(self):
        source = self.root / "writable.c"
        source.write_text("unsigned char pc_kanji_charset2[6270] = {1};\n"
                          "int main(void) {return 0;}\n")
        binary = self.root / "writable-elf"
        subprocess.run(["cc", str(source), "-o", str(binary)], check=True,
                       capture_output=True, timeout=30)
        with self.assertRaisesRegex(ValueError, "read-only loaded data"):
            check_linked_font_bytes(binary, self.expected)

    def test_oversized_initialized_font_must_not_impersonate_original(self):
        source = self.root / "oversized.c"
        source.write_text("const unsigned char pc_kanji_charset2[6271] = {1};\n"
                          "int main(void) {return 0;}\n")
        binary = self.root / "oversized-elf"
        subprocess.run(["cc", str(source), "-o", str(binary)], check=True,
                       capture_output=True, timeout=30)
        with self.assertRaisesRegex(ValueError, "size differs"):
            check_linked_font_bytes(binary, self.expected)

    def test_second_hardlink_is_not_owned_unshared_elf(self):
        original_copy = self.root / "hardlink-target"
        original_copy.write_bytes(self.binary.read_bytes())
        original_copy.chmod(0o700)
        shared = self.root / "hardlinked-elf"
        shared.hardlink_to(original_copy)
        with self.assertRaisesRegex(ValueError, "not an owned executable"):
            check_linked_font_bytes(shared, self.expected)

    def test_unsupported_elf_byte_order_rejected(self):
        altered = self.root / "wrong-byte-order"
        raw = bytearray(self.binary.read_bytes())
        raw[5] = 2
        altered.write_bytes(raw)
        altered.chmod(0o700)
        with self.assertRaisesRegex(ValueError, "unsupported original font ELF encoding"):
            check_linked_font_bytes(altered, self.expected)

    def test_out_of_bounds_section_header_table_rejected(self):
        altered = self.root / "invalid-section-table"
        raw = bytearray(self.binary.read_bytes())
        if raw[4] != 2:
            self.skipTest("64-bit ELF section table bounds regression")
        raw[40:48] = ((1 << 64) - 1).to_bytes(8, "little")
        altered.write_bytes(raw)
        altered.chmod(0o700)
        with self.assertRaisesRegex(ValueError, "invalid original font ELF headers"):
            check_linked_font_bytes(altered, self.expected)

    def test_wrong_expected_font_length_rejected_before_elf_read(self):
        with self.assertRaisesRegex(ValueError, "comparison input"):
            check_linked_font_bytes(self.binary, self.expected[:-1])

    def test_length(self):
        self.assertEqual(FONT_BYTES, 6270)

    def test_missing_binary(self):
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            check_linked_font_bytes('/nonexistent/synthetic-elf', bytes(FONT_BYTES))
