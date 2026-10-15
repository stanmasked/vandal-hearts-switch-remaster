"""Test standalone differential harness and fail-closed source identity checks."""
import shutil
import unittest

from tools.audit_map02_disc_prs import unpack_prs
from tools.compare_map02_variants import EXPECTED_LENGTH, FACE_GFX_OFFSET, RECORD_SIZE, TARGET_RECORDS
from tools.verify_map02_unpack_equivalence import (
    START, END, REQUIRED, compare_with_upstream,
    extract_upstream_decoder, make_corpus,
)


def fake_decoder() -> str:
    # Markers are only syntactic: intentionally incorrect stub decoder.
    anchors = "\n".join(REQUIRED)
    return (START + "\n/*\n" + anchors + "\n*/\n"
            "   return 0;\n}\n" + END + "\n}\n")


class UnpackEquivalenceTests(unittest.TestCase):
    def test_synthetic_corpus_covers_prs_token_types_and_full_map(self):
        corpus = make_corpus()
        self.assertEqual(len(corpus), 7)
        self.assertEqual(len({label for label, _ in corpus}), len(corpus))
        expected = {"literal", "cache_absolute", "cache_relative",
                    "long_literals", "mixed_tokens", "random_literals",
                    "synthetic_full_map"}
        self.assertEqual(set(label for label, _ in corpus), expected)
        for label, sample in corpus:
            with self.subTest(name=label):
                result = unpack_prs(sample)
                self.assertTrue(result)
                if label == "synthetic_full_map":
                    self.assertEqual(len(result), EXPECTED_LENGTH)
                    self.assertEqual(
                        [result[record * RECORD_SIZE + FACE_GFX_OFFSET]
                         for record in TARGET_RECORDS],
                        [241, 243],
                    )

    def test_extract_pinned_function_is_fail_closed(self):
        f = fake_decoder()
        self.assertTrue(extract_upstream_decoder(f).startswith(START))
        with self.assertRaisesRegex(ValueError, "anchors changed"):
            extract_upstream_decoder(f.replace(END, "\nvoid SomethingElse(u8 *input) {"))
        with self.assertRaisesRegex(ValueError, "decompressor anchor changed"):
            extract_upstream_decoder(f.replace("cacheOfs = 990;", "cacheOfs = 10;"))
        with self.assertRaisesRegex(ValueError, "anchors changed"):
            extract_upstream_decoder(f + "\n" + START)

    @unittest.skipUnless(shutil.which("gcc"), "GCC not installed")
    def test_differential_rejects_compiled_c_function_that_loses_data(self):
        with self.assertRaisesRegex(ValueError, "mismatch for literal"):
            compare_with_upstream(fake_decoder())

    def test_corpus_generation_is_deterministic(self):
        self.assertEqual(make_corpus(), make_corpus())


if __name__ == "__main__":
    unittest.main()
