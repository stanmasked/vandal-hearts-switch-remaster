"""Asset-free local compatibility receipt contracts; never real user assets."""
import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.map02_intel_mac_local_acceptance import (
    CATALINA, SCHEMA, bounded_version, checked_manifest_fingerprint, inspect_host_identity, local_acceptance,
    validate_json_stream, validated_results,
)

INTEGRITY = {
    "schema": "vh.map02.intel-mac.offline-preexec-verify.v1",
    "file_digests_verified": 31,
    "public_pc_source_git_blob_verified": True,
    "no_unlisted_files_or_symlinks": True,
    "private_user_data_read": False,
    "kit_signature_verified": False,
}
SELFCHECK = {
    "schema": "vh.map02.intel-mac.offline-private-ft4-readiness.v1",
    "intel_macos_host_checked": True,
    "pinned_public_pc_raster_verified": True,
    "synthetic_regressions_total": 49,
    "private_format_timeline_tests_passed": 14,
    "private_format_native_ft4_tests_passed": 25,
    "private_format_real_cli_tests_passed": 3,
    "private_format_adversarial_cli_tests_passed": 7,
    "synthetic_c11_ft4_frame_passed": True,
    "c11_macho_macos_minimum": "10.15",
    "c11_macho_minimum_verified": True,
    "external_network_used": False,
    "owner_ps1_disc_or_capture_read": False,
    "real_retail_map02_authenticated": False,
    "nintendo_switch_hardware_proven": False,
}
HELPERS = {
    "schema": "vh.map02.catalina.pinned-pc-helper-macho-audit.v1",
    "compiled_helpers_audited": 3,
    "synthetic_helpers_executed": 2,
    "private_timeline_missing_input_rejected": True,
    "helper_architecture": "x86_64",
    "helper_macos_minimum": "10.15",
    "all_helper_load_commands_verified": True,
    "only_system_dynamic_libraries": True,
    "original_ps1_assets_read": False,
    "retail_gameplay_authenticated": False,
}
SUITE_STREAM = json.dumps(SELFCHECK) + "\n" + json.dumps(HELPERS) + "\n"


class Map02LocalCatalinaReceiptContracts(unittest.TestCase):
    def test_exact_two_receipts_only(self):
        first, second = validate_json_stream(SUITE_STREAM)
        self.assertEqual(first["synthetic_regressions_total"], 49)
        self.assertEqual(second["compiled_helpers_audited"], 3)
        for invalid in (SUITE_STREAM + "injected line", "{}", "", SUITE_STREAM + "x" * 25000):
            with self.subTest(case=invalid[:20]):
                with self.assertRaises((ValueError, json.JSONDecodeError)):
                    validate_json_stream(invalid)

    def test_host_version_bounded_public_value(self):
        for good in ("10.15.7", "15.7.1", "14.0", "10.15"):
            self.assertEqual(bounded_version(good), good)
        for bad in ("", "local-user-id", "15.7/Users/owner", "999.99", "15.7.1.0", "10.15.7\n"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    bounded_version(bad)

    def test_complete_invented_receipts_accepted_without_retail_claim(self):
        result = validated_results(INTEGRITY, SELFCHECK, HELPERS)
        self.assertEqual(result["synthetic_tests_verified"], 49)
        self.assertEqual(result["compiled_pc_helpers_verified"], 3)
        self.assertFalse(result["licensed_game_data_used"])

    def test_stale_or_incomplete_suite_rejected(self):
        for field, bad in (
            ("synthetic_regressions_total", 48),
            ("private_format_adversarial_cli_tests_passed", 6),
            ("c11_macho_macos_minimum", "11.0"),
            ("owner_ps1_disc_or_capture_read", True),
            ("real_retail_map02_authenticated", True),
        ):
            broken = dict(SELFCHECK, **{field: bad})
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    validated_results(INTEGRITY, broken, HELPERS)

    def test_tampered_tool_receipt_rejected(self):
        altered = dict(HELPERS, only_system_dynamic_libraries=False)
        with self.assertRaises(ValueError):
            validated_results(INTEGRITY, SELFCHECK, altered)
        incomplete = dict(INTEGRITY, no_unlisted_files_or_symlinks=False)
        with self.assertRaises(ValueError):
            validated_results(incomplete, SELFCHECK, HELPERS)

    def test_wrong_host_is_rejected_before_running_shell(self):
        with patch("platform.system", return_value="Linux"), patch(
            "platform.machine", return_value="x86_64"
        ), patch("subprocess.run") as launch:
            with self.assertRaisesRegex(ValueError, "Intel macOS host required"):
                local_acceptance()
            launch.assert_not_called()
        with patch("platform.system", return_value="Darwin"), patch(
            "platform.machine", return_value="arm64"
        ), patch("subprocess.run") as launch:
            with self.assertRaisesRegex(ValueError, "Intel macOS host required"):
                local_acceptance()
            launch.assert_not_called()

    def fake_macos(self, version, *, strict=False, after_receipt=None,
                   after_sha=None, post_error=False, reject=False):
        responses = [
            SimpleNamespace(
                returncode=0, stdout=json.dumps(INTEGRITY), stderr=""
            ),
            SimpleNamespace(returncode=0, stdout=(
                    json.dumps(dict(SELFCHECK, catalina_10_15_runtime_executed=(version == CATALINA)))
                    + "\n" + json.dumps(HELPERS) + "\n"
                ), stderr=""),
            SimpleNamespace(
                returncode=1 if post_error else 0,
                stdout=json.dumps(INTEGRITY if after_receipt is None else after_receipt),
                stderr="",
            ),
        ]
        with patch("platform.system", return_value="Darwin"), patch(
            "platform.machine", return_value="x86_64"
        ), patch("platform.mac_ver", return_value=(version, ("", "", ""), "x86_64")), patch(
            "pathlib.Path.is_file", return_value=True
        ), patch(
            "tools.map02_intel_mac_local_acceptance.inspect_host_identity",
            return_value={
                "macos_version": version,
                "darwin_kernel_major": 19 if version == CATALINA else 24,
                "host_os_sources_agree": True,
                "host_os_sources": 3,
            }
        ), patch(
            "tools.map02_intel_mac_local_acceptance.checked_manifest_fingerprint",
            side_effect=["a" * 64, "a" * 64 if after_sha is None else after_sha],
        ), patch("subprocess.run", side_effect=responses) as run:
            if reject:
                with self.assertRaises(ValueError):
                    local_acceptance(require_catalina=strict)
                return None, run.call_count
            report = local_acceptance(require_catalina=strict)
            return report, run.call_count

    def test_macos15_synthetic_ok_never_claim_catalina(self):
        report, calls = self.fake_macos("15.7.1")
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(calls, 3)
        self.assertEqual(report["synthetic_tests_verified"], 49)
        self.assertEqual(report["public_kit_manifest_sha256"], "a" * 64)
        self.assertEqual(report["public_kit_files_reverified"], 31)
        self.assertTrue(report["pre_and_post_kit_integrity_verified"])
        self.assertFalse(report["public_kit_signature_verified"])
        self.assertFalse(report["actual_catalina_10_15_7_selfcheck_passed"])
        self.assertFalse(report["independent_trusted_machine_attestation"])
        serialized = json.dumps(report)
        for forbidden in ("Users/", ".bin", ".cue", "GPU", "username", "serial", "hostname"):
            self.assertNotIn(forbidden, serialized)

    def test_strict_catalina_gate_refuses_ci_macos15_before_work(self):
        with patch("platform.system", return_value="Darwin"), patch(
            "platform.machine", return_value="x86_64"
        ), patch("platform.mac_ver", return_value=("15.7.1", ("", "", ""), "x86_64")), patch(
            "tools.map02_intel_mac_local_acceptance.inspect_host_identity",
            return_value={
                "macos_version": "15.7.1",
                "darwin_kernel_major": 24,
                "host_os_sources_agree": True,
                "host_os_sources": 3,
            }
        ), patch("subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "required actual macOS Catalina"):
                local_acceptance(require_catalina=True)
            run.assert_not_called()

    def test_catalina_receipt_label_requires_exact_patch_and_success(self):
        report, calls = self.fake_macos(CATALINA, strict=True)
        self.assertTrue(report["actual_catalina_10_15_7_selfcheck_passed"])
        self.assertEqual(calls, 3)
        self.assertFalse(report["owner_ps1_disc_authenticated"])
        self.assertFalse(report["original_playstation_gpu_pixels_verified"])


    def test_manifest_fingerprint_hashes_exact_public_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = b'{"files":{}, "public_only": true}\n'
            (root / "files.json").write_bytes(data)
            self.assertEqual(
                checked_manifest_fingerprint(root),
                hashlib.sha256(data).hexdigest(),
            )

    def test_missing_symlinked_or_binary_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                checked_manifest_fingerprint(root)
            raw = root / "outside.json"
            raw.write_text("safe", encoding="utf-8")
            (root / "files.json").symlink_to(raw)
            with self.assertRaises(ValueError):
                checked_manifest_fingerprint(root)
            (root / "files.json").unlink()
            (root / "files.json").write_bytes(b"embedded\x00binary")
            with self.assertRaises(ValueError):
                checked_manifest_fingerprint(root)

    def test_manifest_changed_after_successful_diagnostics_is_rejected(self):
        report, calls = self.fake_macos(
            "15.7.1", after_sha="b" * 64, reject=True,
        )
        self.assertIsNone(report)
        self.assertEqual(calls, 3)

    def test_postrun_reverification_detects_different_file_receipt(self):
        after = dict(INTEGRITY, file_digests_verified=30)
        report, calls = self.fake_macos(
            "15.7.1", after_receipt=after, reject=True,
        )
        self.assertIsNone(report)
        self.assertEqual(calls, 3)

    def test_postrun_reverification_failure_refuses_acceptance(self):
        report, calls = self.fake_macos(
            "15.7.1", post_error=True, reject=True,
        )
        self.assertIsNone(report)
        self.assertEqual(calls, 3)



class IntelMacThreeSourceIdentityContracts(unittest.TestCase):
    def fake(self, *, python_os="10.15.7", sw_os="10.15.7",
             kernel="19.6.0", stderr="", exitcode=0):
        output = SimpleNamespace(returncode=exitcode, stdout=sw_os + "\n", stderr=stderr)
        with patch("platform.system", return_value="Darwin"), patch(
            "platform.machine", return_value="x86_64"
        ), patch("platform.mac_ver", return_value=(python_os, ("", "", ""), "x86_64")), patch(
            "platform.release", return_value=kernel
        ), patch("subprocess.run", return_value=output) as call:
            if exitcode or stderr or python_os != sw_os or (
                python_os == "10.15.7" and not kernel.startswith("19.")
            ):
                with self.assertRaises(ValueError):
                    inspect_host_identity()
                return None, call.call_args_list
            return inspect_host_identity(), call.call_args_list

    def test_three_sources_agree_on_mocked_catalina19(self):
        receipt, calls = self.fake()
        self.assertEqual(receipt["macos_version"], "10.15.7")
        self.assertEqual(receipt["darwin_kernel_major"], 19)
        self.assertTrue(receipt["host_os_sources_agree"])
        self.assertEqual(receipt["host_os_sources"], 3)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args[0], ["/usr/bin/sw_vers", "-productVersion"])

    def test_three_sources_agree_on_mocked_mac15_darwin24(self):
        receipt, calls = self.fake(
            python_os="15.7.1", sw_os="15.7.1", kernel="24.6.0"
        )
        self.assertEqual(receipt["darwin_kernel_major"], 24)
        self.assertEqual(len(calls), 1)

    def test_python_and_native_system_version_disagree_refused(self):
        receipt, _ = self.fake(python_os="10.15.7", sw_os="15.7.1")
        self.assertIsNone(receipt)

    def test_mismatched_darwin_kernel_refused(self):
        receipt, _ = self.fake(kernel="24.6.0")
        self.assertIsNone(receipt)

    def test_sw_vers_failure_and_stderr_are_refused(self):
        for kw in ({"exitcode": 1}, {"stderr": "an error"}):
            with self.subTest(case=kw):
                receipt, _ = self.fake(**kw)
                self.assertIsNone(receipt)

    def test_native_output_injection_and_malformed_kernel_refused(self):
        for version in ("10.15.7/Users/private", "10.15.7\nhostname", "NOT_A_VERSION"):
            with self.subTest(version=version):
                with patch("platform.system", return_value="Darwin"), patch(
                    "platform.machine", return_value="x86_64"
                ), patch("platform.mac_ver", return_value=("10.15.7", ("", "", ""), "x86_64")), patch(
                    "platform.release", return_value="19.6.0"
                ), patch("subprocess.run", return_value=SimpleNamespace(
                    returncode=0, stderr="", stdout=version + "\n"
                )):
                    with self.assertRaises(ValueError):
                        inspect_host_identity()
        with patch("platform.system", return_value="Darwin"), patch(
            "platform.machine", return_value="x86_64"
        ), patch("platform.mac_ver", return_value=("10.15.7", ("", "", ""), "x86_64")), patch(
            "platform.release", return_value="Darwin 19/private"
        ), patch("subprocess.run") as run:
            with self.assertRaises(ValueError):
                inspect_host_identity()
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
