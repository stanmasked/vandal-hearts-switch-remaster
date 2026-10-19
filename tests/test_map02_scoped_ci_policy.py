"""Offline checks that MAP02 synthetic CI cannot silently lose its guardrails."""
from pathlib import Path
import re
import unittest


WORKFLOW = (Path(__file__).resolve().parents[1] /
            ".github/workflows/map02-scoped-blend.yml")


class Map02ScopedCiPolicyTests(unittest.TestCase):
    def test_superseded_workflow_runs_are_cancelled_per_event_and_ref(self):
        raw = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("concurrency:\n", raw)
        self.assertIn("group: map02-scoped-", raw)
        self.assertIn("github.event_name", raw)
        self.assertIn("github.event.pull_request.number || github.ref", raw)
        self.assertRegex(raw, r"(?m)^  cancel-in-progress: true$")

    def test_scoped_job_is_time_bounded_and_executes_protection_suite(self):
        raw = WORKFLOW.read_text(encoding="utf-8")
        self.assertRegex(
            raw, r"(?m)^  scoped-blend:\n    runs-on: ubuntu-latest\n"
                 r"    timeout-minutes: 30$")
        for suite in (
            "tests.test_seal_map02_private_finalization",
            "tests.test_verify_map02_cycle_cd_gpu_join",
            "tests.test_map02_scoped_ci_policy",
        ):
            self.assertIn(suite, raw)

    def test_private_input_inventory_is_triggered_and_executed(self):
        raw = WORKFLOW.read_text(encoding="utf-8")
        # The workflow uses an explicit unittest module list. Merely
        # compiling tests does not run the new privacy/inventory tests.
        for path in (
            "tools/inspect_map02_private_inputs.py",
            "tests/test_inspect_map02_private_inputs.py",
        ):
            self.assertEqual(raw.count("      - '" + path + "'"), 2,
                             "MAP02 push and PR triggers must cover " + path)
        self.assertEqual(
            raw.count("            tests.test_inspect_map02_private_inputs \\"),
            1, "MAP02 inventory regressions must actually be executed")

    def test_no_private_evidence_artifact_upload(self):
        raw = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("actions/upload-artifact", raw)
        self.assertNotIn("gh release upload", raw)


if __name__ == "__main__":
    unittest.main()
