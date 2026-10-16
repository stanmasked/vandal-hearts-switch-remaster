"""Mutation tests for source-authentic PC GPU OT ordering gate."""
import unittest
from tools.audit_map02_ot_source import verify_ot_order

SAMPLE = '''
unsigned int *ClearOTag(unsigned int *ot, int n) {
  for (i = 0; i < n - 1; i++) slots[i] = PC_OtMint(&slots[i + 1], 1);
  slots[n - 1] = 0;
}
void AddPrim(void *ot, void *p) {
  u32 head = ((P_TAG *)ot)->tag;
  ((P_TAG *)p)->tag = head;
  ((P_TAG *)ot)->tag = PC_OtMint(p, 0);
}
void DrawOTag(unsigned int *p) {
  u32 nextTok = ((P_TAG *)p)->tag;
  while (nextTok) {
    if (!isBucket) draw_primitive();
    nextTok = rawTagOfCur;
  }
}
'''

class OrderingSourceTests(unittest.TestCase):
    def test_ordering_contract(self):
        r=verify_ot_order(SAMPLE)
        self.assertEqual(r["pc_ot_bucket_order"],"0..n-1")
        self.assertIn("LIFO",r["same_bucket_primitive_order"])
        self.assertFalse(r["ps1_hardware_gpu_verified"])

    def test_mutated_chain_or_lifo_rejected(self):
        mutations=(
            ("slots[i + 1]","slots[i - 1]"),
            ("slots[n - 1] = 0;","slots[0] = 0;"),
            ("((P_TAG *)p)->tag = head;","((P_TAG *)p)->tag = 0;"),
            ("PC_OtMint(p, 0)","PC_OtMint(p, 1)"),
            ("while (nextTok)","while (0)"),
            ("nextTok = rawTagOfCur;","nextTok = 0;"),
            ("if (!isBucket)","if (isBucket)"),
        )
        for old,new in mutations:
            with self.subTest(old=old):
                with self.assertRaisesRegex(ValueError,"changed"):
                    verify_ot_order(SAMPLE.replace(old,new))
        with self.assertRaisesRegex(ValueError,"function boundaries changed"):
            verify_ot_order(SAMPLE.replace("void AddPrim", "void AddPrimRenamed"))

if __name__=="__main__":
    unittest.main()
