"""Fully synthetic source-byte provenance checks for original US KROM C.

No game executable, licensed KROM, ROM, BIOS or original generated C is used.
"""
import hashlib
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

import tools.check_map02_original_font_c as font


class PrivateOriginalFontCProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-original-font-audit-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.upstream = self.root / "upstream"
        self.bundle = self.root / "bundle"
        self.bundle.mkdir(mode=0o700)
        self.generated = (self.upstream / "platform/pc" / font.BUILD /
                          font.NAME)
        self.generated.parent.mkdir(parents=True)
        self.source = self.root / "owned-synthetic-krom.bin"
        self.glyphs = bytes(i % 251 for i in range(font.FONT_LENGTH))
        self.source.write_bytes(self.glyphs)
        self.generated.write_bytes(font._expected_us_font_c(self.glyphs))
        self.generated.chmod(0o600)
        self.original_hash = patch.object(
            font, "US_FONT_SHA256",
            hashlib.sha256(self.glyphs).hexdigest())
        self.original_hash.start()
        self.addCleanup(self.original_hash.stop)
        self.preflight = patch.object(font, "preflight", return_value=self.bundle)
        self.preflight.start()
        self.addCleanup(self.preflight.stop)

    def check(self, *, krom_source=None):
        return font.verify_generated_original_font(
            self.upstream, self.bundle,
            krom_source=self.source if krom_source is None else krom_source)

    def test_synthetic_original_font_bytes_identical(self):
        report = self.check()
        self.assertTrue(report["pinned_original_krom_font_c_identical"])
        self.assertFalse(report["original_map02_rendering_proven"])
        self.assertFalse(report["original_font_bytes_disclosed"])

    def test_generated_font_data_byte_corruption_is_rejected(self):
        value = bytearray(self.generated.read_bytes())
        value[value.index(b"0x00") + 3] = ord("f")
        self.generated.write_bytes(value)
        self.generated.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "differs from original US KROM"):
            self.check()

    def test_wrong_generated_source_permissions_rejected(self):
        self.generated.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "metadata invalid"):
            self.check()

    def test_generated_font_symlink_rejected(self):
        renamed = self.root / "foreign-generated-source"
        renamed.write_bytes(self.generated.read_bytes())
        self.generated.unlink()
        self.generated.symlink_to(renamed)
        with self.assertRaisesRegex(ValueError, "linked private original input"):
            self.check()

    def test_missing_font_c_does_not_attest_game_link(self):
        self.generated.unlink()
        with self.assertRaisesRegex(ValueError, "input unavailable"):
            self.check()

    def test_wrong_owned_krom_bytes_rejected(self):
        changed = bytearray(self.glyphs)
        changed[0] ^= 1
        self.source.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "charset differs"):
            self.check()

    def test_identical_generated_file_replacement_mid_audit_rejected(self):
        actual_renderer = font._expected_us_font_c

        def swap(value):
            original = self.generated.read_bytes()
            self.generated.unlink()
            self.generated.write_bytes(original)
            self.generated.chmod(0o600)
            return actual_renderer(value)

        with patch.object(font, "_expected_us_font_c", side_effect=swap):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.check()

    def test_identical_krom_file_replacement_mid_audit_rejected(self):
        actual_renderer = font._expected_us_font_c

        def swap(value):
            original = self.source.read_bytes()
            self.source.unlink()
            self.source.write_bytes(original)
            return actual_renderer(value)

        with patch.object(font, "_expected_us_font_c", side_effect=swap):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.check()

    def test_second_read_rejects_same_metadata_but_modified_source_bytes(self):
        real_read = font._read_owned
        count = [0]

        def mutate_second_read(path, category, **kwargs):
            data, identity = real_read(path, category, **kwargs)
            count[0] += 1
            if count[0] == 3:
                data = bytes([data[0] ^ 1]) + data[1:]
            return data, identity

        with patch.object(font, "_read_owned", side_effect=mutate_second_read):
            with self.assertRaisesRegex(ValueError, "private original input changed"):
                self.check()
        self.assertEqual(count[0], 3)

    def test_second_read_rejects_same_metadata_but_modified_generated_bytes(self):
        real_read = font._read_owned
        count = [0]

        def mutate_second_read(path, category, **kwargs):
            data, identity = real_read(path, category, **kwargs)
            count[0] += 1
            if count[0] == 4:
                data = data[:-1] + b"X"
            return data, identity

        with patch.object(font, "_read_owned", side_effect=mutate_second_read):
            with self.assertRaisesRegex(ValueError, "private original input changed"):
                self.check()
        self.assertEqual(count[0], 4)

    def test_owned_full_bios_charset_offset(self):
        bios = self.root / "synthetic-bios.bin"
        raw = bytearray(font.BIOS_SIZE)
        raw[font.FONT_BIOS_OFFSET:font.FONT_BIOS_OFFSET + len(self.glyphs)] = (
            self.glyphs)
        bios.write_bytes(raw)
        self.assertTrue(self.check(krom_source=bios)[
            "pinned_original_krom_font_c_identical"])

    def test_owned_krom_generated_c_and_real_native_elf_are_bound_together(self):
        c_file = self.root / "linked-synthetic.c"
        c_file.write_text(
            "const unsigned char pc_kanji_charset2[6270] = {"
            + ",".join(str(value) for value in self.glyphs)
            + "};\\nint main(void) {return 0;}\\n")
        binary = self.root / "linked-synthetic-elf"
        subprocess.run(["cc", str(c_file), "-o", str(binary)],
                       check=True, capture_output=True, timeout=30)
        report = font.verify_linked_original_font(
            self.upstream, self.bundle, binary, krom_source=self.source)
        self.assertTrue(report["linked_original_us_font_bytes_match"])
        self.assertFalse(report["actual_gameplay_executed"])

        altered = self.root / "linked-altered-elf"
        raw = bytearray(binary.read_bytes())
        position = raw.find(self.glyphs)
        self.assertGreaterEqual(position, 0)
        raw[position + 75] ^= 1
        altered.write_bytes(raw)
        altered.chmod(0o700)
        with self.assertRaisesRegex(ValueError, "linked original US font bytes differ"):
            font.verify_linked_original_font(
                self.upstream, self.bundle, altered, krom_source=self.source)

    def test_generated_serializer_exact_original_public_format(self):
        text = font._expected_us_font_c(self.glyphs)
        self.assertTrue(text.startswith(
            b"/* GENERATED by platform/pc/tools/gen_kanji_font.py"))
        self.assertIn(b"const unsigned char pc_kanji_charset2[6270] = {", text)
        self.assertTrue(text.endswith(b"};\n"))
        self.assertEqual(text.count(b"0x"), font.FONT_LENGTH)


if __name__ == "__main__":
    unittest.main()
