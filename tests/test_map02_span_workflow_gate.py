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
        self.assertIn('Publish source-pinned DDA candidate build evidence', text)
        self.assertIn('GITHUB_STEP_SUMMARY', text)
        self.assertIn('Save reproducible original GPU object manifest', text)
        self.assertIn('sha256sum --check evidence/objects.sha256', text)
        self.assertIn('actions/upload-artifact@v4', text)
        self.assertIn('map02-original-gpu-candidate-evidence', text)
        self.assertIn('test "$(git rev-parse HEAD)" = 14552fffa0e0b47e02b57592e274fc6e7a649923', text)
        self.assertIn('sha256sum "build/map02-vertical-dda/$object"', text)
        self.assertIn('This is a compile/link check, NOT an original MAP02 gameplay capture.', text)
        self.assertIn('objcopy --only-section=.text -O binary', text)
        self.assertIn('cmp build/map02-vertical-dda/span-baseline.text.bin', text)
        self.assertIn('readelf -rW build/map02-vertical-dda/span.baseline.o', text)
        self.assertIn('readelf -rW build/map02-vertical-dda/candidate.baseline.o', text)
        self.assertIn('cmp build/map02-vertical-dda/span-baseline.relocations.txt', text)
        self.assertIn('span-clang.${mode}.o', text)
        self.assertIn('cmp build/map02-vertical-dda/span-clang-baseline.text.bin', text)
        self.assertIn('cmp build/map02-vertical-dda/span-clang-baseline.relocations.txt', text)
        self.assertIn('nm --defined-only "build/map02-vertical-dda/candidate-linked-clang.${mode}.o"', text)
        self.assertIn('nm --defined-only build/map02-vertical-dda/candidate-linked.baseline.o', text)
        self.assertIn('Candidate observer leaked into Clang baseline', text)

    def test_evidence_manifest_is_executable_and_sha_provenance_is_unambiguous(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        manifest = text.split("      - name: Save reproducible original GPU object manifest", 1)[1].split(
            "      - name: Upload original GPU object evidence", 1)[0]
        self.assertIn("REMASTER_SOURCE_HEAD: ${{ github.event.pull_request.head.sha || github.sha }}", manifest)
        self.assertIn('test "$(git -C ../../../remaster rev-parse HEAD)" = "$GITHUB_SHA"', manifest)
        self.assertIn("remaster-source-head.txt", manifest)
        self.assertIn("remaster-commit.txt", manifest)
        self.assertIn("sha256sum --check evidence/objects.sha256", manifest)
        for line in manifest.splitlines():
            if (line.strip().startswith("sha256sum candidate-linked.diagnostic.o") or
                    line.strip().startswith("candidate-linked-clang.diagnostic.o")):
                self.assertEqual(len(line) - len(line.rstrip(chr(92))), 1,
                                 "Bash line continuation must be exactly one backslash")
            if "printf '%s" in line:
                self.assertIn("printf '%s" + chr(92) + "n'", line)
                self.assertNotIn("printf '%s" + chr(92) * 2 + "n'", line)

    def test_sparse_checkout_supplies_all_pinned_pc_source_headers(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        checkout = text.split("      - name: Checkout pinned public PC-port source", 1)[1].split(
            "      - name: Audit local preflight against public pinned upstream", 1)[0]
        for name in ("libsnd_internal.h", "pc_balance.h", "pc_etc_internal.h",
                     "pc_gpu_internal.h", "pc_movie_subs.h", "pc_overlay.h",
                     "pc_saves.h"):
            self.assertIn("platform/pc/src/" + name, checkout)

    def test_private_make_uses_sealed_descriptors_in_ci(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        private_build = text.split(
            "      - name: Build pinned two-word GPU and native DDA objects through original PC Make", 1
        )[1].split("      - name: Run patch generator regression tests", 1)[0]
        self.assertIn("python3 -m tools.run_map02_sealed_gpu_receipt_chain", private_build)
        self.assertIn("test_build_map02_private_gpu_make_overlay.py", private_build)
        self.assertIn('assert report["sealed_inputs"] == 6 + report["pinned_headers_checked"]', private_build)
        self.assertIn('assert report["pinned_headers_sealed"] == report["pinned_headers_checked"]',
                      private_build)
        self.assertIn('assert report["header_path_mutations_rejected"]', private_build)
        self.assertIn('assert report["compiler_tools_before_after_match"]', private_build)
        self.assertIn('assert report["compiler_shared_objects_before_after_match"]',
                      private_build)
        self.assertIn('assert report["compiler_runtime_mappings_correlated_to_resolved_files"]',
                      private_build)
        self.assertIn('assert report["compiler_runtime_log_pids_verified"]', private_build)
        self.assertIn('assert report["compiler_runtime_executables_bound_to_selected_tools"]',
                      private_build)
        self.assertIn('assert report["kernel_tool_exec_witnesses"] == 6', private_build)
        self.assertIn('assert report["actual_make_children_kernel_attested"]', private_build)
        self.assertIn('assert report["kernel_make_primary_executables_match_sha256"]', private_build)
        self.assertIn('assert report["kernel_make_primary_mapped_libraries_match_sha256"]',
                      private_build)
        self.assertIn('assert not report["separate_make_object_replay_performed"]', private_build)
        self.assertIn('assert report["system_header_bytes_before_after_match"]', private_build)
        self.assertIn('assert report["compiled_from_sealed_preprocessor_output"]', private_build)
        self.assertIn('assert report["staged_header_hashes_verified"]', private_build)
        self.assertIn('assert report["pinned_headers_checked"] >= 40', private_build)
        self.assertIn('assert not report["all_headers_sealed"]', private_build)
        self.assertIn("--build-dir build-map02-private-ci", private_build)
        self.assertNotIn("BUILD_DIR=build-map02-private-ci map02-private-gpu-objects",
                         private_build)
        pr_paths = text.split("  pull_request:\n    paths:", 1)[1].split("\njobs:", 1)[0]
        self.assertIn("'tools/build_map02_private_gpu_make_overlay.py'", pr_paths)
        self.assertIn("'tests/test_build_map02_private_gpu_make_overlay.py'", pr_paths)
        self.assertIn("'tools/consume_map02_sealed_gpu_objects.py'", pr_paths)
        self.assertIn("'tools/verify_map02_linked_gpu_object.py'", pr_paths)
        self.assertIn("'tools/run_map02_sealed_gpu_receipt_chain.py'", pr_paths)
        self.assertIn("'tests/test_run_map02_sealed_gpu_receipt_chain.py'", pr_paths)
        self.assertIn("'tools/verify_map02_published_receipt.py'", pr_paths)
        self.assertIn("'tests/test_verify_map02_published_receipt.py'", pr_paths)
        self.assertIn("id: map02_receipt_commitment", private_build)
        self.assertIn("uses: actions/upload-artifact@v4", private_build)
        self.assertIn("verify-published-gpu-receipt:", text)
        self.assertIn("needs: verify-trace-patch", text)
        self.assertIn("uses: actions/download-artifact@v4", text)
        self.assertIn("--expected-sha256", text)
        self.assertIn('assert not receipt["independent_digital_signature_verified"]', text)
        self.assertIn('assert bundle["sealed_receipt_snapshots"] == 3', private_build)
        self.assertIn('assert not bundle["externally_authenticated"]', private_build)
        self.assertIn('assert verified["linked_hash_verified_against_receipt"]', private_build)
        self.assertIn('assert verified["linked_bytes_sealed_before_binutils"]', private_build)
        self.assertIn("'tests/test_consume_map02_sealed_gpu_objects.py'", pr_paths)
        self.assertIn('assert linked["binutils_consumed_sealed_objects"]', private_build)

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
