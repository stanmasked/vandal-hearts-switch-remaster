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

    def test_abs64_counts_are_compared_as_numbers_not_booleans(self):
        """Guard against: assert 222 == (222 == 222), which always fails."""
        import ast

        raw = WORKFLOW.read_text(encoding="utf-8")
        step = raw.split(
            "      - name: Attribute 380 surviving original PC imports to exact compiled game versus backend objects\n", 1)[1].split("\n      - name:", 1)[0]
        code = step.split("          python3 - <<'PY'\n", 1)[1]
        code = code.split("\n          PY", 1)[0]
        parsed = ast.parse("\n".join(
            line[10:] if line.startswith("          ") else line
            for line in code.splitlines()))

        def report_key(node):
            if (isinstance(node, ast.Subscript)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "r"
                    and isinstance(node.slice, ast.Constant)
                    and isinstance(node.slice.value, str)):
                return node.slice.value
            return None

        checks = [
            node.test for node in ast.walk(parsed)
            if isinstance(node, ast.Assert)
            and isinstance(node.test, ast.Compare)
            and report_key(node.test.left) == "high_fanout_abs64_data_records"
            and len(node.test.comparators) == 2
        ]
        self.assertEqual(len(checks), 1)
        self.assertEqual(
            [report_key(node) for node in
             (checks[0].left, *checks[0].comparators)],
            ["high_fanout_abs64_data_records",
             "high_fanout_provenance_abs64_records",
             "high_fanout_provenance_section_data_records"])
        self.assertEqual(len(checks[0].ops), 2)
        self.assertTrue(all(isinstance(op, ast.Eq) for op in checks[0].ops))

    def test_abs64_addend_object_split_reports_only_aggregate_counts(self):
        raw = WORKFLOW.read_text(encoding="utf-8")
        for metric in (
            "nonzero_records", "distinct_nonzero_values",
            "objects_with_nonzero_values", "objects_with_zero_only_values",
            "min_zero_records_per_source_object",
            "max_zero_records_per_source_object",
            "min_nonzero_records_per_source_object",
            "max_nonzero_records_per_source_object",
            "nonzero_values_shared_across_source_objects",
            "records_with_cross_object_shared_nonzero_values",
            "min_distinct_nonzero_values_per_source_object",
            "max_distinct_nonzero_values_per_source_object",
        ):
            self.assertIn(
                f'assert r["high_fanout_abs64_addend_{metric}"]' if metric in (
                    "nonzero_records", "distinct_nonzero_values",
                    "objects_with_nonzero_values", "objects_with_zero_only_values",
                    "nonzero_values_shared_across_source_objects",
                    "records_with_cross_object_shared_nonzero_values")
                else f'"high_fanout_abs64_addend_{metric}"',
                raw)
        output = raw.split(
            'print("ABS64 target-addend private values reduced to counts:",', 1
        )[1].split('\n          print("Per-source names', 1)[0]
        self.assertIn('r["high_fanout_abs64_addend_" + name]', output)
        self.assertNotIn("game_addends", output)
        self.assertNotIn("game_patch_offsets", output)
        self.assertNotIn("parse_readelf_abs64_data_patch_addends", output)

    def test_no_private_evidence_artifact_upload(self):
        raw = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("actions/upload-artifact", raw)
        self.assertNotIn("gh release upload", raw)


if __name__ == "__main__":
    unittest.main()
