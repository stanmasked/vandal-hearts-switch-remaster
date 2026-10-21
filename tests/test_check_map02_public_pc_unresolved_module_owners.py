"""Synthetic per-module origin tests; no retail file/symbols or user paths."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.check_map02_public_pc_unresolved_module_owners import (
    SCHEMA, LINK_SCHEMA, summarize_owner_groups,
    summarize_game_only_fanout, read_link_report,
    parse_readelf_global_undefined_types, summarize_high_fanout_elf_types,
    parse_readelf_relocation_types, summarize_high_fanout_relocations,
    summarize_high_fanout_relocation_provenance,
    parse_readelf_abs64_data_patch_offsets,
    summarize_high_fanout_abs64_patch_layout,
    summarize_high_fanout_abs64_patch_gaps,
    parse_readelf_abs64_data_patch_addends,
    summarize_high_fanout_abs64_target_addends,
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

    def test_strict_readelf_global_undefined_types_from_real_nm_style_rows(self):
        example = (
            "Symbol table '.symtab' contains 8 entries:\n"
            "  Num:    Value          Size Type    Bind   Vis      Ndx Name\n"
            "    1: 0000000000000000     0 FUNC    GLOBAL DEFAULT  UND method\n"
            "    2: 0000000000000000     0 OBJECT  GLOBAL DEFAULT  UND buffer\n"
            "    3: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND unknown\n"
            "    4: 0000000000000000     0 FUNC    WEAK   DEFAULT  UND weak_only\n"
            "    5: 0000000000000000    11 FUNC    GLOBAL DEFAULT    1 defined\n"
        )
        classes = parse_readelf_global_undefined_types(example)
        self.assertEqual(classes, {
            "method": {"FUNC"}, "buffer": {"OBJECT"},
            "unknown": {"NOTYPE"},
        })

    def test_high_fanout_native_type_marker_partition_and_shared_exclusion(self):
        game = [{"fun", "obj", "mixed", "unknown", "other", "shared"}
                for _ in range(8)]
        game[0].add("rare")
        table = [{
            "fun": {"FUNC"}, "obj": {"OBJECT"},
            "mixed": {"FUNC"} if i == 0 else {"OBJECT"},
            "unknown": {"NOTYPE"}, "other": {"TLS"},
            "shared": {"FUNC"}, "rare": {"NOTYPE"},
        } for i in range(8)]
        report = summarize_high_fanout_elf_types(
            {"fun", "obj", "mixed", "unknown", "other", "shared", "rare"},
            game, [{"shared"}], table, minimum_callers=8)
        self.assertEqual(report["high_fanout_game_only_imports"], 5)
        for key in ("function_marker", "object_marker",
                    "mixed_function_object", "notype_only",
                    "other_or_unknown"):
            self.assertEqual(report["high_fanout_elf_" + key], 1)
        self.assertEqual(report["high_fanout_with_any_notype_declaration"], 1)
        self.assertTrue(report["elf_symbol_type_is_not_proof_of_abi_or_runtime_calls"])

    def test_high_fanout_missing_elf_type_evidence_fails_closed(self):
        games = [{"wide"} for _ in range(8)]
        witnesses = [{"wide": {"FUNC"}} for _ in range(7)] + [{}]
        with self.assertRaisesRegex(ValueError, "witness"):
            summarize_high_fanout_elf_types(
                {"wide"}, games, [], witnesses)

    def test_real_compiler_produces_parseable_undefined_global_elf_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "caller.c"
            obj = root / "caller.o"
            source.write_text(
                "extern int external_global;\n"
                "extern int external_function(void);\n"
                "int call(void) { return external_global + external_function(); }\n"
            )
            subprocess.run(
                ["cc", "-c", str(source), "-o", str(obj)],
                check=True, capture_output=True, timeout=30)
            nm = subprocess.run(
                ["nm", "-u", str(obj)], check=True,
                capture_output=True, text=True, timeout=30)
            readelf = subprocess.run(
                ["readelf", "-Ws", str(obj)], check=True,
                capture_output=True, text=True, timeout=30)
            strong, _ = _undefined_symbol_names(nm.stdout)
            types = parse_readelf_global_undefined_types(readelf.stdout)
            self.assertIn("external_global", strong)
            self.assertIn("external_function", strong)
            self.assertTrue(set(strong).issubset(types))

    def test_high_fanout_relocation_kind_presence_is_disjoint(self):
        game = [{"plt", "pc", "both", "other", "none", "shared"}
                for _ in range(8)]
        game[0].add("rare")
        kinds = [{
            "plt": [("R_X86_64_PLT32", ".rela.text")],
            "pc": [("R_X86_64_PC32", ".rela.text")],
            "both": ([("R_X86_64_PLT32", ".rela.text")] if i < 4
                     else [("R_X86_64_PC32", ".rela.text")]),
            "other": [("R_X86_64_GOTPCREL", ".rela.data")],
            "shared": [("R_X86_64_PLT32", ".rela.text")],
        } for i in range(8)]
        result = summarize_high_fanout_relocations(
            {"plt", "pc", "both", "other", "none", "shared", "rare"},
            game, [{"shared"}], kinds)
        self.assertEqual(result["high_fanout_game_only_imports_with_relocation_check"], 5)
        self.assertEqual(result["high_fanout_reloc_plt32_only"], 1)
        self.assertEqual(result["high_fanout_reloc_pc32_only"], 1)
        self.assertEqual(result["high_fanout_reloc_plt32_and_pc32"], 1)
        self.assertEqual(result["high_fanout_reloc_other_or_mixed"], 1)
        self.assertEqual(result["high_fanout_reloc_no_relocation_record"], 1)
        self.assertEqual(result["high_fanout_only_nontext_relocation_names"], 1)
        self.assertEqual(result["high_fanout_reloc_plt32_records"], 12)
        self.assertEqual(result["high_fanout_reloc_pc32_records"], 12)
        self.assertEqual(result["high_fanout_reloc_other_records"], 8)
        self.assertTrue(result["relocation_types_do_not_prove_function_or_data_semantics"])

    def test_parse_readelf_relocation_rows_with_addend(self):
        table = (
            "Relocation section '.rela.text' at offset 0x1a0 contains 2 entries:\n"
            "    Offset             Info             Type               Symbol's Value  Symbol's Name + Addend\n"
            "000000000000001b  0000000500000004 R_X86_64_PLT32         0000000000000000 ext_func - 4\n"
            "0000000000000021  0000000400000002 R_X86_64_PC32          0000000000000000 ext_data - 4\n"
            "Relocation section '.rela.eh_frame' at offset 0x230 contains 1 entry:\n"
            "0000000000000020  0000000200000002 R_X86_64_PC32          0000000000000000 .text + 0\n"
        )
        output = parse_readelf_relocation_types(table)
        self.assertEqual(output["ext_func"], [("R_X86_64_PLT32", ".rela.text")])
        self.assertEqual(output["ext_data"], [("R_X86_64_PC32", ".rela.text")])
        self.assertEqual(output[".text"], [("R_X86_64_PC32", ".rela.eh_frame")])

    def test_native_cc_readelf_relocation_rows_for_function_and_data(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            src, obj = root / "reloc.c", root / "reloc.o"
            src.write_text(
                "extern int ext_func(int);\n"
                "extern int ext_var;\n"
                "int use(int x){return ext_func(x) + ext_var;}\n")
            subprocess.run(["cc", "-c", "-O0", "-fno-pie", "-o",
                            str(obj), str(src)],
                           capture_output=True, check=True, timeout=30)
            report = subprocess.run(
                ["readelf", "-rW", str(obj)], capture_output=True,
                text=True, check=True, timeout=30)
            kinds = parse_readelf_relocation_types(report.stdout)
            self.assertTrue(any(t == "R_X86_64_PLT32"
                                for t, _ in kinds["ext_func"]))
            self.assertTrue(any(t == "R_X86_64_PC32"
                                for t, _ in kinds["ext_var"]))

    def test_relocation_evidence_disallows_forged_source_inventory(self):
        with self.assertRaisesRegex(ValueError, "inventory invalid"):
            summarize_high_fanout_relocations(
                {"a"}, [{"a"} for _ in range(8)], [],
                [{} for _ in range(7)])

    def test_native_relocation_class_and_section_provenance_buckets(self):
        symbols = {"pc", "abs", "got", "misc", "wide", "shared"}
        game = [set(symbols) for _ in range(8)]
        backend = [{"shared"}]
        relocation_maps = [{
            "pc": [("R_X86_64_PC32", ".rela.text")],
            "abs": [("R_X86_64_32", ".rela.rodata")],
            "got": [("R_X86_64_REX_GOTPCRELX", ".rela.data.rel.ro")],
            "misc": [("R_X86_64_UNKNOWN_TEST", ".rela.eh_frame")],
            "wide": ([
                ("R_X86_64_64", ".rela.text"),
                ("R_X86_64_32S", ".rela.other"),
                ("R_X86_64_PLT32", ".rela.text"),
            ] if i == 0 else [("R_X86_64_PC32", ".rela.text")]),
            "shared": [("R_X86_64_32S", ".rela.text")],
        } for i in range(8)]
        result = summarize_high_fanout_relocation_provenance(
            symbols, game, backend, relocation_maps)
        self.assertEqual(result["high_fanout_provenance_imports"], 5)
        self.assertEqual(result["high_fanout_provenance_pc32_records"], 15)
        self.assertEqual(result["high_fanout_provenance_plt32_records"], 1)
        self.assertEqual(result["high_fanout_provenance_abs32_records"], 8)
        self.assertEqual(result["high_fanout_provenance_abs32s_records"], 1)
        self.assertEqual(result["high_fanout_provenance_abs64_records"], 1)
        self.assertEqual(result["high_fanout_provenance_gotpcrel_records"], 8)
        self.assertEqual(result["high_fanout_provenance_other_records"], 8)
        self.assertEqual(result["high_fanout_provenance_total_records"], 42)
        self.assertEqual(result["high_fanout_provenance_section_text_records"], 17)
        self.assertEqual(result["high_fanout_provenance_section_rodata_records"], 8)
        self.assertEqual(result["high_fanout_provenance_section_data_records"], 8)
        self.assertEqual(result["high_fanout_provenance_section_unwind_records"], 8)
        self.assertEqual(result["high_fanout_provenance_section_other_records"], 1)
        self.assertEqual(result["high_fanout_provenance_any_non_pc32_plt32_imports"], 4)
        self.assertEqual(result["high_fanout_provenance_both_text_nontext_imports"], 1)
        self.assertEqual(result["high_fanout_provenance_nontext_only_imports"], 3)
        self.assertTrue(result["source_section_and_relocation_type_do_not_prove_runtime_abi"])

    def test_provenance_no_records_do_not_invent_calls(self):
        refs = [{"unresolved"} for _ in range(8)]
        got = summarize_high_fanout_relocation_provenance(
            {"unresolved"}, refs, [], [{} for _ in range(8)])
        self.assertEqual(got["high_fanout_provenance_imports"], 1)
        self.assertEqual(got["high_fanout_provenance_without_relocation_records"], 1)
        self.assertEqual(got["high_fanout_provenance_total_records"], 0)

    def test_provenance_source_object_count_mismatch_fails(self):
        with self.assertRaisesRegex(ValueError, "inventory invalid"):
            summarize_high_fanout_relocation_provenance(
                {"a"}, [{"a"} for _ in range(8)], [], [{}])

    def test_abs64_patch_offsets_from_real_readelf_format(self):
        report = (
            "Relocation section '.rela.text' at offset 0x110 contains 1 entry:\n"
            "0000000000000007  0000000400000001 R_X86_64_64 0000000000000000 source - 0\n"
            "Relocation section '.rela.data' at offset 0x150 contains 3 entries:\n"
            "0000000000000000  0000000400000001 R_X86_64_64 0000000000000000 target + 0\n"
            "0000000000000008  0000000400000001 R_X86_64_64 0000000000000000 target + 0\n"
            "0000000000000010  0000000400000002 R_X86_64_PC32 0000000000000000 other - 4\n"
            "Relocation section '.rela.data.rel.ro' at offset 0x230 contains 1 entry:\n"
            "0000000000000000  0000000400000001 R_X86_64_64 0000000000000000 target + 0\n"
        )
        got = parse_readelf_abs64_data_patch_offsets(report)
        self.assertEqual(got["target"], [
            (".rela.data", 0), (".rela.data", 8),
            (".rela.data.rel.ro", 0),
        ])
        self.assertNotIn("source", got)
        self.assertNotIn("other", got)

    def test_native_rela_addend_decodes_hex_and_signed_values(self):
        elf = (
            "Relocation section '.rela.data' at offset 0xf0 contains 4 entries:\n"
            "0000000000000000  0000000300000001 R_X86_64_64 0000000000000000 ext + 0\n"
            "0000000000000008  0000000300000001 R_X86_64_64 0000000000000000 ext + 18\n"
            "0000000000000010  0000000300000001 R_X86_64_64 0000000000000000 ext + 18\n"
            "0000000000000018  0000000300000001 R_X86_64_64 0000000000000000 ext - 8\n"
        )
        self.assertEqual(parse_readelf_abs64_data_patch_addends(elf)["ext"], [
            (".rela.data", 0, 0), (".rela.data", 8, 24),
            (".rela.data", 16, 24), (".rela.data", 24, -8)])
        broken = elf.replace("ext + 18", "ext + nothex")
        with self.assertRaisesRegex(ValueError, "encoding invalid"):
            parse_readelf_abs64_data_patch_addends(broken)

    def test_addend_repeats_reconciled_across_distinct_source_objects(self):
        game = [{"target", "shared"} for _ in range(8)]
        first = {"target": [(".rela.data", 0, 0),
                            (".rela.data", 8, 24),
                            (".rela.data", 16, 24),
                            (".rela.data", 24, -8)],
                 "shared": [(".rela.data", 32, 1)]}
        second = {"target": [(".rela.data", 0, 0),
                             (".rela.data", 8, 40)]}
        addends = [first, second] + [{} for _ in range(6)]
        patches = [
            {"target": [(".rela.data", 0), (".rela.data", 8),
                        (".rela.data", 16), (".rela.data", 24)]},
            {"target": [(".rela.data", 0), (".rela.data", 8)]},
        ] + [{} for _ in range(6)]
        summary = summarize_high_fanout_abs64_target_addends(
            {"target", "shared"}, game, [{"shared"}], addends, patches)
        self.assertEqual(summary["high_fanout_abs64_addend_total_records"], 6)
        self.assertEqual(summary["high_fanout_abs64_addend_source_objects"], 2)
        self.assertEqual(summary["high_fanout_abs64_addend_symbol_names"], 1)
        self.assertEqual(summary["high_fanout_abs64_addend_distinct_values"], 4)
        self.assertEqual(summary["high_fanout_abs64_addend_zero_records"], 2)
        self.assertEqual(summary["high_fanout_abs64_addend_negative_records"], 1)
        self.assertEqual(summary["high_fanout_abs64_addend_eight_aligned_records"], 6)
        self.assertEqual(
            summary["high_fanout_abs64_addend_distinct_repeated_values"], 2)
        self.assertEqual(
            summary["high_fanout_abs64_addend_records_with_reused_values"], 4)
        self.assertEqual(
            summary["high_fanout_abs64_addend_max_records_sharing_one_value"], 2)
        self.assertEqual(
            summary["high_fanout_abs64_addend_values_repeated_within_source_object"], 1)
        self.assertEqual(
            summary["high_fanout_abs64_addend_records_reused_within_source_object"], 2)
        self.assertEqual(
            summary["high_fanout_abs64_addend_values_shared_across_source_objects"], 1)
        self.assertEqual(
            summary["high_fanout_abs64_addend_records_with_cross_object_shared_values"], 2)
        self.assertEqual(
            summary["high_fanout_abs64_addend_max_records_same_value_in_one_object"], 2)
        self.assertEqual(
            summary["high_fanout_abs64_addend_min_distinct_values_per_source_object"], 2)
        self.assertEqual(
            summary["high_fanout_abs64_addend_max_distinct_values_per_source_object"], 3)

    def test_addend_missing_original_relocation_witness_is_rejected(self):
        game = [{"one"} for _ in range(8)]
        patches = [{"one": [(".rela.data", 8)]}] + [{} for _ in range(7)]
        addends = [{} for _ in range(8)]
        with self.assertRaisesRegex(ValueError, "missing ABS64 addend witness"):
            summarize_high_fanout_abs64_target_addends(
                {"one"}, game, [], addends, patches)

    def test_real_gcc_rela_addends_can_differ_from_patch_offsets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            src, obj = root / "addends.c", root / "addends.o"
            src.write_text(
                "extern char external_array[];\n"
                "void *refs[] = {external_array, external_array+24, "
                "external_array+24, external_array+48};\n")
            subprocess.run(
                ["cc", "-c", "-O0", "-fno-pie", "-o", str(obj), str(src)],
                capture_output=True, check=True, timeout=30)
            data = subprocess.run(
                ["readelf", "-rW", str(obj)], capture_output=True,
                text=True, check=True, timeout=30)
            parsed = parse_readelf_abs64_data_patch_addends(data.stdout)
            self.assertEqual(
                [addend for _, _, addend in parsed["external_array"]],
                [0, 24, 24, 48])

    def test_abs64_gap_histogram_separates_source_objects(self):
        game = [{"s"} for _ in range(8)]
        mapping = [
            {"s": [(".rela.data", x) for x in (0, 16, 40, 72, 112)]},
            {"s": [(".rela.data", x) for x in (0, 8, 16)]},
            *({} for _ in range(6)),
        ]
        result = summarize_high_fanout_abs64_patch_gaps(
            {"s"}, game, [], mapping)
        self.assertEqual(result["high_fanout_abs64_gap_total_records"], 8)
        self.assertEqual(result["high_fanout_abs64_gap_source_objects"], 2)
        self.assertEqual(result["high_fanout_abs64_gap_source_sections"], 2)
        self.assertEqual(result["high_fanout_abs64_gap_adjacent_site_pairs"], 6)
        expected = {"8": 2, "16": 1, "24": 1, "32": 1,
                    "40_to_64": 1, "over_64": 0, "non_multiple_8": 0}
        for key, count in expected.items():
            self.assertEqual(result["high_fanout_abs64_gap_" + key], count)
        self.assertEqual(
            result["high_fanout_abs64_gap_largest_source_object_records"], 5)
        self.assertEqual(
            result["high_fanout_abs64_gap_second_largest_source_object_records"], 3)
        self.assertEqual(result["high_fanout_abs64_gap_smallest_positive_distance_bytes"], 8)
        self.assertTrue(
            result["offset_gaps_do_not_identify_c_struct_or_executed_game"])

    def test_abs64_gap_splits_sections_and_unaligned_spacing(self):
        game = [{"target"} for _ in range(8)]
        mapping = [{
            "target": [(".rela.data", 0), (".rela.data", 12),
                       (".rela.data", 100), (".rela.data.rel.ro", 4)]
        }] + [{} for _ in range(7)]
        result = summarize_high_fanout_abs64_patch_gaps(
            {"target"}, game, [], mapping)
        self.assertEqual(result["high_fanout_abs64_gap_source_sections"], 2)
        self.assertEqual(result["high_fanout_abs64_gap_adjacent_site_pairs"], 2)
        self.assertEqual(result["high_fanout_abs64_gap_non_multiple_8"], 1)
        self.assertEqual(result["high_fanout_abs64_gap_over_64"], 1)
        self.assertEqual(result["high_fanout_abs64_gap_singleton_sections"], 1)

    def test_abs64_gap_rejects_duplicate_and_fake_source_inventory(self):
        game = [{"s"} for _ in range(8)]
        dupe = [{"s": [(".rela.data", 8), (".rela.data", 8)]}] + [
            {} for _ in range(7)]
        with self.assertRaisesRegex(ValueError, "duplicate ABS64"):
            summarize_high_fanout_abs64_patch_gaps(
                {"s"}, game, [], dupe)
        with self.assertRaisesRegex(ValueError, "object count invalid"):
            summarize_high_fanout_abs64_patch_gaps(
                {"s"}, game, [], [{}])

    def test_abs64_source_objects_do_not_mix_offsets_between_files(self):
        game = [{"target"} for _ in range(8)]
        maps = [
            {"target": [(".rela.data", i) for i in (0, 8, 16, 32)]},
            {"target": [(".rela.data", i) for i in (0, 8)]},
            {"target": [(".rela.data.rel.ro", 0)]},
            *({} for _ in range(5)),
        ]
        summary = summarize_high_fanout_abs64_patch_layout(
            {"target"}, game, [], maps)
        self.assertEqual(summary["high_fanout_abs64_data_records"], 7)
        self.assertEqual(summary["high_fanout_abs64_data_symbol_names"], 1)
        self.assertEqual(summary["high_fanout_abs64_data_source_objects"], 3)
        self.assertEqual(summary["high_fanout_abs64_data_source_sections"], 3)
        self.assertEqual(summary["high_fanout_abs64_data_aligned_eight_byte_records"], 7)
        self.assertEqual(summary["high_fanout_abs64_data_adjacent_eight_byte_pairs"], 3)
        self.assertEqual(summary["high_fanout_abs64_data_longest_eight_byte_run"], 3)
        self.assertEqual(
            summary["high_fanout_abs64_data_max_records_in_one_source_object"], 4)
        self.assertTrue(
            summary["patch_offset_adjacency_does_not_prove_runtime_pointer_table"])

    def test_abs64_duplicate_section_patch_rejected(self):
        game = [{"wide"} for _ in range(8)]
        maps = [{"wide": [(".rela.data", 8), (".rela.data", 8)]},
                *({} for _ in range(7))]
        with self.assertRaisesRegex(ValueError, "duplicate ABS64"):
            summarize_high_fanout_abs64_patch_layout(
                {"wide"}, game, [], maps)

    def test_abs64_wide_game_only_filters_shared_and_rare(self):
        game = [{"wide", "shared"} for _ in range(8)]
        game[0].add("rare")
        maps = [{"wide": [(".rela.data", 8)],
                 "shared": [(".rela.data", 24)],
                 "rare": [(".rela.data", 32)]}] + [{} for _ in range(7)]
        result = summarize_high_fanout_abs64_patch_layout(
            {"wide", "shared", "rare"}, game, [{"shared"}], maps)
        self.assertEqual(result["high_fanout_abs64_data_records"], 1)
        self.assertEqual(result["high_fanout_abs64_data_symbol_names"], 1)

    def test_native_gcc_abs64_data_section_offsets(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            src, obj = root / "pointer.c", root / "pointer.o"
            src.write_text(
                "extern int foreign_word;\n"
                "void *locations[] = {&foreign_word, &foreign_word, &foreign_word};\n")
            subprocess.run(
                ["cc", "-c", "-O0", "-fno-pie", "-o", str(obj), str(src)],
                check=True, capture_output=True, timeout=30)
            data = subprocess.run(
                ["readelf", "-rW", str(obj)], check=True,
                capture_output=True, text=True, timeout=30)
            raw = parse_readelf_abs64_data_patch_offsets(data.stdout)
            self.assertEqual(len(raw["foreign_word"]), 3)
            offsets = [offset for _, offset in raw["foreign_word"]]
            self.assertEqual(
                offsets, [min(offsets), min(offsets)+8, min(offsets)+16])

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
