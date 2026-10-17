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

    def test_length(self):
        self.assertEqual(FONT_BYTES, 6270)

    def test_missing_binary(self):
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            check_linked_font_bytes('/nonexistent/synthetic-elf', bytes(FONT_BYTES))
