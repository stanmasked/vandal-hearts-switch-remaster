"""Fail-closed tests for compiling the pinned PC OP0 source boundary."""
from pathlib import Path
import unittest

from tools.verify_map02_pc_op0_equivalence import (
    SIGNATURES, REQUIRED, extract_pc_op0, compare
)

def synthetic_source():
    return """
static int Sat16(int v, int lm) {
    if (v > 32767) return 32767;
    if (v < (lm ? 0 : -32768)) return lm ? 0 : -32768;
    return v;
}
void PC_GTE_LoadOPV1(void *v) {
    int *src = (int *)v;
    g.opvD[0] = src[0];
    g.opvD[1] = src[1];
    g.opvD[2] = src[2];
}
void PC_GTE_LoadOPV2(void *v) {
    int *src = (int *)v;
    g.ir1 = (short)src[0];
    g.ir2 = (short)src[1];
    g.ir3 = (short)src[2];
}
void PC_GTE_OP0(void) {
    int d1 = g.opvD[0], d2 = g.opvD[1], d3 = g.opvD[2];
    int ir1 = g.ir1, ir2 = g.ir2, ir3 = g.ir3;
    g.mac1 = ir3 * d2 - ir2 * d3;
    g.mac2 = ir1 * d3 - ir3 * d1;
    g.mac3 = ir2 * d1 - ir1 * d2;
    g.ir1 = (short)Sat16(g.mac1, 0);
    g.ir2 = (short)Sat16(g.mac2, 0);
    g.ir3 = (short)Sat16(g.mac3, 0);
}
void PC_GTE_StoreLVNL(void *out) {
    int *o = (int *)out;
    o[0] = g.mac1; o[1] = g.mac2; o[2] = g.mac3;
}
"""

class OP0SourceTests(unittest.TestCase):
    def test_extraction_and_native_synthetic_comparison(self):
        source = synthetic_source()
        extracted = extract_pc_op0(source)
        for signature in SIGNATURES:
            self.assertIn(signature, extracted)
        for statement in REQUIRED:
            self.assertIn(statement, extracted)
        header = (Path(__file__).parent.parent /
                  "source/map02_op0_reference.h").read_text()
        report = compare(source, header)
        self.assertEqual(report["cases"], 4106)
        self.assertTrue(report["compiled_pc_op0_mac_matches"])
        self.assertGreater(report["pc_vs_ps1_register_input_difference_cases"], 0)
        self.assertFalse(report["ps1_hardware_gte_verified"])

    def test_load_or_mac_store_mutation_fails_closed(self):
        source = synthetic_source()
        for changed, message in (
            (source.replace("g.ir2 = (short)src[1];", "g.ir2 = src[1];"),
             "PC OP0 arithmetic changed"),
            (source.replace("o[0] = g.mac1;", "o[0] = g.ir1;"),
             "PC OP0 arithmetic changed"),
            (source.replace("g.mac3 = ir2 * d1 - ir1 * d2;",
                            "g.mac3 = ir1 * d2 - ir2 * d1;"),
             "PC OP0 arithmetic changed"),
            (source.replace("void PC_GTE_OP0(void) {",
                            "void PC_GTE_OP1(void) {"),
             "PC OP0 source signature changed"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    extract_pc_op0(changed)

if __name__ == "__main__":
    unittest.main()
