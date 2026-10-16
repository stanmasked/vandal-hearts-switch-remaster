"""Guard the native source-pinned span build against workflow regressions."""
from pathlib import Path
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/map02-upstream-trace.yml"

class SpanWorkflowGateTests(unittest.TestCase):
    def test_original_gpu_and_span_objects_link_in_both_modes(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("for mode in diagnostic baseline; do", text)
        self.assertIn("prepare_span(", text)
        self.assertIn('span_extra=(-DVH_MAP02_DDA_SPAN_TRACE)', text)
        self.assertIn('/tmp/vh-map02-native-span-overlay/pc_raster.span.c', text)
        self.assertIn('"build/map02-vertical-dda/span.${mode}.o"', text)
        self.assertIn('"build/map02-vertical-dda/span-linked.${mode}.o"', text)
        self.assertIn('nm -a build/map02-vertical-dda/span-linked.diagnostic.o', text)
        self.assertIn('nm -a build/map02-vertical-dda/span-linked.baseline.o', text)

    def test_trigger_includes_observer_and_test(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count("'tools/instrument_map02_dda_span.py'"), 2)
        self.assertGreaterEqual(text.count("'tests/test_instrument_map02_dda_span.py'"), 2)

if __name__ == "__main__":
    unittest.main()
