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
        self.assertIn('pc_raster.candidate.c', text)
        self.assertIn('candidate-linked.${mode}.o', text)
        self.assertIn('VH_Map02RejectedEdges', text)
        self.assertIn('candidate-clang.${mode}.o', text)
        self.assertIn('gpu-clang.${mode}.o', text)
        self.assertIn('candidate-linked-clang.${mode}.o', text)
        self.assertIn('Candidate observer leaked into Clang baseline', text)

    def test_trigger_includes_observer_and_test(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  push:\n    branches:\n      - 'work/map02-dda-coverage-independent-audit'", text)
        pr_paths = text.split("  pull_request:\n    paths:", 1)[1].split("\njobs:", 1)[0]
        self.assertIn("'tools/instrument_map02_dda_span.py'", pr_paths)
        self.assertIn("'tests/test_instrument_map02_dda_span.py'", pr_paths)
        for observed in ("tools/instrument_map02_dda_rejected_edges.py",
                         "tests/test_map02_dda_candidate_c11.py",
                         "tools/verify_map02_dda_rejected_edges.py"):
            self.assertIn(repr(observed), pr_paths)

if __name__ == "__main__":
    unittest.main()
