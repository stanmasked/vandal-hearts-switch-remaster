"""Tests for exact original glyph bytes in host ELF."""
import unittest
from tools.check_map02_linked_font_elf import FONT_BYTES

class FontLinkedTests(unittest.TestCase):
    def test_length(self):
        self.assertEqual(FONT_BYTES, 6270)
