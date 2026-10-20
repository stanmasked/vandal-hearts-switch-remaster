"""Fail-closed generation checks; synthetic test text is NOT original MAP02."""
import unittest
from unittest.mock import patch

from tools.verify_map02_pc_vram4_ft4_binding import (
    CALLS, EXPECTED, make_harness,
)

TEMPLATE = (
    '#include "../source/map02_vram4_frame.h"\n'
    "static uint8_t vram[VH_MAP02_VRAM_BYTES];\n"
    "static void fixture(void) {}\n"
    "int main(void) {return 0;}\n"
)


class Ft4BindingHarnessTests(unittest.TestCase):
    @patch(
        "tools.verify_map02_pc_vram4_ft4_binding.extract_sample_functions",
        return_value="/* pinned function test stub */",
    )
    def test_one_source_insert_and_mutation_probes(self, _extract):
        generated = make_harness("synthetic", TEMPLATE)
        self.assertIn('source/map02_vram4_frame.h', generated)
        self.assertIn("verify_pinned_pc_face_bindings(0)", generated)
        self.assertIn("verify_pinned_pc_face_bindings(1)", generated)
        self.assertIn("verify_pinned_pc_face_bindings(2)", generated)
        self.assertIn("SampleTexture(", generated)
        self.assertIn(EXPECTED, generated)
        self.assertNotIn('#include "../source/map02_vram4_frame.h"', generated)

    @patch(
        "tools.verify_map02_pc_vram4_ft4_binding.extract_sample_functions",
        return_value="/* test */",
    )
    def test_wrong_or_duplicate_boundaries_refused(self, _extract):
        for altered in (
            TEMPLATE.replace("static void fixture(void)", "void fake(void)"),
            TEMPLATE + TEMPLATE,
            TEMPLATE.replace("#include", "// include"),
            TEMPLATE.replace("static uint8_t vram", "static char vram"),
            TEMPLATE.replace("int main(void)", "int start(void)"),
        ):
            with self.subTest(altered=altered[:55]):
                with self.assertRaisesRegex(ValueError, "not unique"):
                    make_harness("synthetic", altered)


if __name__ == "__main__":
    unittest.main()
