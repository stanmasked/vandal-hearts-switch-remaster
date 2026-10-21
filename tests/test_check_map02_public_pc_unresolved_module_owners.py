"""Synthetic per-module origin tests; no retail file/symbols or user paths."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.check_map02_public_pc_unresolved_module_owners import (
    SCHEMA, LINK_SCHEMA, summarize_owner_groups,
    summarize_game_only_fanout, read_link_report,
)
from tools.check_map02_public_reloc_link import _undefined_symbol_names


class ModuleOwnerTests(unittest.TestCase):
    def test_disjoint_game_backend_provenance_and_repeat_references(self):
        result = summarize_owner_groups(
            {"only_game", "only_backend", "shared"},
            [{"only_game", "shared"}, {"only_game"}],
            [{"only_backend", "shared"}])
        self.assertEqual(result["remaining_pc_total"], 3)
        self.assertEqual(result["original_game_only_imports"], 1)
        self.assertEqual(result["backend_only_imports"], 1)
        self.assertEqual(result["shared_game_backend_imports"], 1)
        self.assertEqual(result["missing_object_owner_imports"], 0)
        self.assertEqual(result["game_object_symbol_reference_pairs"], 3)
        self.assertEqual(result["backend_object_symbol_reference_pairs"], 2)
        self.assertEqual(result["game_objects_with_remaining_imports"], 2)
        self.assertEqual(result["backend_objects_with_remaining_imports"], 1)

    def test_all_four_game_only_caller_fanout_buckets_use_real_object_counts(self):
        # Variable repetition across 15 independent TUs; one symbol may be
        # referenced in many TUs, but one TU can count it only once.
        widths = {"s1": 1, "s2": 2, "s3": 3,
                  "s4": 4, "s7": 7, "s8": 8, "s15": 15}
        game = [set() for _ in range(15)]
        for symbol, width in widths.items():
            for refs in game[:width]:
                refs.add(symbol)
        game[0].add("shared")
        game[1].add("shared")
        backend = [{"shared", "backend_only"}]
        result = summarize_game_only_fanout(
            set(widths) | {"shared", "backend_only"}, game, backend)
        self.assertEqual(result["game_only_fanout_one"], 1)
        self.assertEqual(result["game_only_fanout_two_to_three"], 2)
        self.assertEqual(result["game_only_fanout_four_to_seven"], 2)
        self.assertEqual(result["game_only_fanout_eight_or_more"], 2)
        self.assertEqual(result["game_only_reference_pairs"], 40)
        self.assertEqual(result["shared_game_reference_pairs"], 2)
        self.assertEqual(result["backend_only_reference_pairs"], 1)
        self.assertEqual(result["shared_backend_reference_pairs"], 1)
        self.assertEqual(result["game_only_max_caller_objects_per_symbol"], 15)
        self.assertTrue(result["fanout_counts_distinct_source_objects_not_runtime_calls"])
        owner = summarize_owner_groups(
            set(widths) | {"shared", "backend_only"}, game, backend)
        self.assertEqual(sum(result["game_only_fanout_" + key] for key in
                             ("one", "two_to_three", "four_to_seven",
                              "eight_or_more")), owner["original_game_only_imports"])
        self.assertEqual(result["game_only_reference_pairs"] +
                         result["shared_game_reference_pairs"],
                         owner["game_object_symbol_reference_pairs"])

    def test_fanout_without_game_only_symbols_has_zero_max(self):
        result = summarize_game_only_fanout(
            {"shared", "backend_only"}, [{"shared"}],
            [{"shared", "backend_only"}])
        self.assertEqual(result["game_only_fanout_one"], 0)
        self.assertEqual(result["game_only_max_caller_objects_per_symbol"], 0)
        self.assertEqual(result["game_only_reference_pairs"], 0)
        self.assertEqual(result["shared_game_reference_pairs"], 1)

    def test_fanout_deduplicates_same_symbol_within_one_object(self):
        output = summarize_game_only_fanout(
            {"same"}, [["same", "same", "same"]], [])
        self.assertEqual(output["game_only_fanout_one"], 1)
        self.assertEqual(output["game_only_reference_pairs"], 1)
        self.assertEqual(output["game_only_max_caller_objects_per_symbol"], 1)

    def test_unattributed_name_not_silently_counted_as_owned(self):
        r = summarize_owner_groups(
            {"found_game", "found_backend", "unattributed"},
            [{"found_game"}], [{"found_backend"}])
        self.assertEqual(r["missing_object_owner_imports"], 1)
        self.assertEqual(sum(r[k] for k in (
            "original_game_only_imports", "backend_only_imports",
            "shared_game_backend_imports", "missing_object_owner_imports")), 3)

    def test_empty_import_lists_no_negative_or_implicit_owners(self):
        r = summarize_owner_groups(set(), [set()], [set()])
        self.assertEqual(r["remaining_pc_total"], 0)
        self.assertEqual(r["missing_object_owner_imports"], 0)
        self.assertEqual(r["game_object_symbol_reference_pairs"], 0)

    def test_real_gcc_objects_report_undefined_references(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for which, symbol in (("game", "synthetic_game_call"),
                                  ("backend", "synthetic_backend_call")):
                src = root / (which + ".c")
                dst = root / (which + ".o")
                src.write_text(f"extern int {symbol}(void);\n"
                               f"int {which}_entry(void){{return {symbol}();}}\n")
                subprocess.run(
                    ["cc", "-c", str(src), "-o", str(dst)], check=True,
                    capture_output=True, timeout=30)
                nm = subprocess.run(
                    ["nm", "-u", str(dst)], check=True, capture_output=True,
                    text=True, timeout=30)
                strong, weak = _undefined_symbol_names(nm.stdout)
                self.assertIn(symbol, strong)
                self.assertFalse(weak)

    def test_report_schema_refusal_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            report = root / "actual.json"
            report.write_text(json.dumps({"schema": LINK_SCHEMA}))
            self.assertEqual(read_link_report(report)["schema"], LINK_SCHEMA)
            report.write_text(json.dumps({"schema": "forged"}))
            with self.assertRaisesRegex(ValueError, "schema invalid"):
                read_link_report(report)
            report.write_text(json.dumps({"schema": LINK_SCHEMA}))
            alias = root / "alias.json"
            alias.symlink_to(report)
            with self.assertRaisesRegex(ValueError, "symlink rejected"):
                read_link_report(alias)


if __name__ == "__main__":
    unittest.main()
