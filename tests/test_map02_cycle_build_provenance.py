"""Asset-free local MAP02 build provenance tests.

A tiny synthetic fake binary and mocked native compiler/source audits are
used only to test binding and receipt integrity. No retail original ELF,
disc image, user directories, or graphics are accessed.
"""
import hashlib
import io
from contextlib import redirect_stderr
import json
import subprocess
import tools.map02_cycle_build_provenance as provenance
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.map02_cycle_build_provenance import (
    NAME, SCHEMA, create_build_receipt, verify_build_receipt,
)


class CycleBuildReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vh-map02-build-binding-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.upstream = self.root / "upstream"
        self.binary = self.upstream / "platform/pc/build-map02-cycle/vandalhearts_pc"
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b"synthetic-ELF-not-actually-runnable")
        self.binary.chmod(0o700)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir(mode=0o700)
        (self.bundle / "map02_cycle_build_inputs.json").write_bytes(
            b'{"synthetic":"pinned-only"}\n')
        (self.bundle / "map02_cycle_build_inputs.json").chmod(0o600)
        self.receipt_dir = self.root / "receipt"
        self.receipt_dir.mkdir(mode=0o700)
        self.planned = {"full_game_link_command_sha256": "a" * 64}
        self.symbols = {"required_symbols_present": 19}
        self.mocks = (
            patch("tools.map02_cycle_build_provenance.audit",
                  return_value=self.planned),
            patch("tools.map02_cycle_build_provenance.audit_cycle_elf",
                  return_value=self.symbols),
            patch("tools.map02_cycle_build_provenance.verify_generated_original_font",
                  return_value={"pinned_original_krom_font_c_identical": True}),
            patch("tools.map02_cycle_build_provenance.verify_pinned_upstream",
                  return_value="b" * 64),
            patch("tools.check_map02_cycle_make_plan.preflight",
                  return_value=self.bundle / "map02_cycle.mk"),
            patch("tools.map02_cycle_build_provenance.verify_private_pc_inputs",
                  return_value={"private_build_inputs_binding_sha256": "9" * 64}),
        )
        for item in self.mocks:
            item.start()
            self.addCleanup(item.stop)
        self.build_result = {
            "full_elf_linked": True,
            "pc_executable_sha256": hashlib.sha256(
                self.binary.read_bytes()).hexdigest(),
            "source_bound_make_command_sha256": "a" * 64,
            "required_original_cycle_and_gpu_symbols": 19,
            "private_retail_inputs_binding_sha256": "9" * 64,
        }

    def publish(self):
        return create_build_receipt(self.receipt_dir, self.binary,
                                    self.upstream, self.bundle,
                                    build_result=self.build_result)

    def verify(self):
        return verify_build_receipt(self.receipt_dir, self.binary,
                                    self.upstream, self.bundle)

    def test_exact_local_build_bytes_source_and_make_plan_join(self):
        created = self.publish()
        self.assertFalse(created["retail_gameplay_executed"])
        receipt = self.receipt_dir / NAME
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        record = json.loads(receipt.read_bytes())
        self.assertEqual(record["schema"], SCHEMA)
        self.assertEqual(record["pc_executable_sha256"],
                         self.build_result["pc_executable_sha256"])
        self.assertFalse(record["actual_gameplay_executed"])
        self.assertFalse(record["original_map02_rendering_proven"])
        self.assertFalse(record["hd_substitution_enabled"])
        self.assertTrue(self.verify()["source_pinned_full_elf_bytes_checked"])
        with self.assertRaisesRegex(ValueError, "must start empty"):
            self.publish()

    def test_cli_redacts_private_original_path_on_io_and_timeout(self):
        private_path = str(self.upstream / "SLUS_004.47")
        command = ["verify-build", str(self.receipt_dir), str(self.binary),
                   str(self.upstream), str(self.bundle)]
        for fault in (OSError("input " + private_path),
                      subprocess.TimeoutExpired(["python3", private_path], 5)):
            with self.subTest(fault=type(fault).__name__):
                output = io.StringIO()
                with (
                        patch("sys.argv", command),
                        patch.object(provenance, "verify_build_receipt",
                                     side_effect=fault),
                        redirect_stderr(output)):
                    with self.assertRaises(SystemExit) as thrown:
                        provenance.main()
                self.assertEqual(thrown.exception.code, 2)
                self.assertIn("command verification failed", output.getvalue())
                self.assertNotIn(private_path, output.getvalue())

    def test_altered_generated_krom_c_blocks_receipt_verification(self):
        self.publish()
        with patch(
                "tools.map02_cycle_build_provenance.verify_generated_original_font",
                side_effect=ValueError("generated private font C differs")):
            with self.assertRaisesRegex(ValueError, "font C differs"):
                self.verify()

    def test_changed_binary_fails_closed(self):
        self.publish()
        self.binary.write_bytes(self.binary.read_bytes() + b" mutation")
        with self.assertRaisesRegex(ValueError, "executable/source differs"):
            self.verify()

    def test_changed_owned_original_exe_or_font_identity_fails_closed(self):
        self.publish()
        with patch(
                "tools.map02_cycle_build_provenance.verify_private_pc_inputs",
                return_value={
                    "private_build_inputs_binding_sha256": "f" * 64}):
            with self.assertRaisesRegex(ValueError, "executable/source differs"):
                self.verify()

    def test_manifest_change_fails_closed(self):
        self.publish()
        file = self.bundle / "map02_cycle_build_inputs.json"
        file.write_bytes(file.read_bytes() + b" changed")
        with self.assertRaisesRegex(ValueError, "executable/source differs"):
            self.verify()

    def test_source_or_expanded_link_drift_fails_closed(self):
        self.publish()
        with patch("tools.map02_cycle_build_provenance.verify_pinned_upstream",
                   return_value="c" * 64):
            with self.assertRaisesRegex(ValueError, "executable/source differs"):
                self.verify()
        self.planned["full_game_link_command_sha256"] = "d" * 64
        with self.assertRaisesRegex(ValueError, "executable/source differs"):
            self.verify()

    def test_invalid_claims_duplicate_keys_and_extra_files_fail(self):
        self.publish()
        receipt = self.receipt_dir / NAME
        original = receipt.read_bytes()
        for mutated in (
            original.replace(b'"actual_gameplay_executed":false',
                             b'"actual_gameplay_executed":true'),
            original.replace(b'"schema":', b'"schema":"duplicate","schema":', 1),
            original[:-1],
            original.replace(b'\n', b'\r\n'),
        ):
            with self.subTest(mutated=mutated[-32:]):
                receipt.write_bytes(mutated)
                with self.assertRaises(ValueError):
                    self.verify()
        receipt.write_bytes(original)
        extra = self.receipt_dir / "extra"
        extra.write_bytes(b"unlisted")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.verify()

    def test_wrong_binary_path_and_symlink_rejected(self):
        with self.assertRaisesRegex(ValueError, "dedicated build target"):
            create_build_receipt(self.receipt_dir, self.root / "different",
                                 self.upstream, self.bundle,
                                 build_result=self.build_result)
        self.publish()
        destination = self.binary.with_name("old-binary")
        self.binary.rename(destination)
        self.binary.symlink_to(destination)
        with self.assertRaisesRegex(ValueError, "dedicated build target"):
            self.verify()

    def test_report_directory_must_be_private_and_false_build_rejected(self):
        self.receipt_dir.chmod(0o755)
        with self.assertRaises(ValueError):
            self.publish()
        self.receipt_dir.chmod(0o700)
        self.build_result["full_elf_linked"] = False
        with self.assertRaisesRegex(ValueError, "no confirmed"):
            self.publish()
        self.assertFalse((self.receipt_dir / NAME).exists())


if __name__ == "__main__":
    unittest.main()
