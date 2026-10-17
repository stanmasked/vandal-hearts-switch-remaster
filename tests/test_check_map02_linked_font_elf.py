"""Tests for exact original glyph bytes in host ELF."""
import unittest
from pathlib import Path
import subprocess
import tempfile
from tools.check_map02_linked_font_elf import check_linked_font_bytes
from tools.check_map02_linked_font_elf import FONT_BYTES

class FontLinkedTests(unittest.TestCase):
    def test_length(self):
        self.assertEqual(FONT_BYTES, 6270)
