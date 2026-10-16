#!/usr/bin/env python3
"""Stage 218 host-only SD transfer verification with simulated mounted folders."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import verify_switch_audio_bundle as bundle  # noqa: E402
import verify_switch_audio_sd_transfer as transfer  # noqa: E402
from test_verify_switch_audio_bundle import synthetic_structural_nro  # noqa: E402


class SdTransferTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.source = self.base / "evidence"
        self.mount = self.base / "mock-sd-mount"
        (self.source / "nro").mkdir(parents=True)
        self.mount.mkdir()
        self.nro = self.source / "nro" / "vandal-hearts-prototype.nro"
        self.nro.write_bytes(synthetic_structural_nro())
        self.dest = self.mount / transfer.DEFAULT_DESTINATION
        bundle.create(self.source, "nro/vandal-hearts-prototype.nro", [],
                      "a" * 40, "")
        self.plan = self.base / "host-side-transfer-plan.json"

    def plan_record(self, target=transfer.DEFAULT_DESTINATION):
        return transfer.create_plan(self.source, self.mount, self.plan, target)

    def manual_copy(self):
        self.dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.nro, self.dest)

    def test_fingerprint_before_copy_does_not_modify_sd(self):
        result = self.plan_record()
        self.assertEqual(result["result"], "SOURCE_FINGERPRINT_RECORDED")
        self.assertEqual(result["hardware_status"], "HARDWARE NOT TESTED")
        self.assertTrue(result["requires_manual_copy"])
        self.assertFalse(result["destination_previously_existed"])
        self.assertFalse(self.dest.exists())
        p = transfer.read_plan(self.plan)
        self.assertIsNone(p["destination_before"])
        self.assertFalse(p["copy_performed"])

    def test_missing_copy_is_rejected(self):
        self.plan_record()
        with self.assertRaisesRegex(transfer.TransferError, "missing"):
            transfer.verify(self.source, self.mount, self.plan)

    def test_matching_manual_copy_is_not_hardware_acceptance(self):
        self.plan_record()
        self.manual_copy()
        report = transfer.verify(self.source, self.mount, self.plan)
        self.assertEqual(report["result"], "DESTINATION_BYTES_MATCH_PLANNED_NRO")
        self.assertEqual(report["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(report["destination_medium"], "NOT_VERIFIED_AS_PHYSICAL_SD")
        self.assertEqual(report["sd_durability"], "NOT_TESTED")
        self.assertEqual(report["copy_operation"], "NOT_OBSERVED_BY_VERIFIER")
        self.assertFalse(report["destination_was_already_identical_before_plan"])
        self.assertEqual(report["nro_size"], self.nro.stat().st_size)

    def test_truncated_copy_fails_instead_of_returning_success(self):
        self.plan_record()
        self.manual_copy()
        self.dest.write_bytes(self.dest.read_bytes()[:-1])
        with self.assertRaisesRegex(transfer.TransferError, "SHA-256/size"):
            transfer.verify(self.source, self.mount, self.plan)

    def test_same_size_copy_corruption_is_detected(self):
        self.plan_record()
        self.manual_copy()
        data = bytearray(self.dest.read_bytes())
        data[-1] ^= 1
        self.dest.write_bytes(data)
        with self.assertRaisesRegex(transfer.TransferError, "SHA-256/size"):
            transfer.verify(self.source, self.mount, self.plan)

    def test_existing_old_sd_build_is_recorded_without_overwrite(self):
        self.dest.parent.mkdir(parents=True)
        self.dest.write_bytes(b"old NRO version")
        result = self.plan_record()
        self.assertTrue(result["destination_previously_existed"])
        self.assertEqual(self.dest.read_bytes(), b"old NRO version")
        before = transfer.read_plan(self.plan)["destination_before"]
        self.assertEqual(before["size"], len(b"old NRO version"))
        self.manual_copy()
        verified = transfer.verify(self.source, self.mount, self.plan)
        self.assertTrue(verified["destination_previously_existed"])
        self.assertFalse(verified["destination_was_already_identical_before_plan"])

    def test_existing_identical_nro_cannot_prove_a_new_copy(self):
        self.manual_copy()
        self.plan_record()
        report = transfer.verify(self.source, self.mount, self.plan)
        self.assertTrue(report["destination_was_already_identical_before_plan"])
        self.assertEqual(report["copy_operation"], "NOT_OBSERVED_BY_VERIFIER")

    def test_cannot_reuse_plan_for_modified_source_file_or_manifest(self):
        self.plan_record()
        self.manual_copy()
        self.nro.write_bytes(self.nro.read_bytes() + b"change")
        with self.assertRaisesRegex(bundle.BundleError, "SHA-256 mismatch"):
            transfer.verify(self.source, self.mount, self.plan)
        self.nro.write_bytes(synthetic_structural_nro())
        raw = json.loads((self.source / bundle.MANIFEST_NAME).read_text())
        raw["ci_run_url"] = "https://github.com/example/other/actions/runs/1"
        (self.source / bundle.MANIFEST_NAME).write_text(json.dumps(raw))
        with self.assertRaisesRegex(transfer.TransferError, "source evidence manifest changed"):
            transfer.verify(self.source, self.mount, self.plan)

    def test_cannot_substitute_different_manifest_plan_commit(self):
        self.plan_record()
        self.manual_copy()
        p = json.loads(self.plan.read_text())
        p["git_sha"] = "b" * 40
        self.plan.write_text(json.dumps(p))
        with self.assertRaisesRegex(transfer.TransferError, "source identity changed"):
            transfer.verify(self.source, self.mount, self.plan)

    def test_destination_path_traversal_and_wrong_file_are_rejected(self):
        for path in ("../outside/vandal-hearts-prototype.nro",
                     "/tmp/vandal-hearts-prototype.nro",
                     "switch/./vandal-hearts-prototype.nro",
                     "switch/other.nro",
                     "switch\\vandal-hearts-prototype.nro"):
            with self.subTest(path=path), self.assertRaises(transfer.TransferError):
                transfer.create_plan(self.source, self.mount, self.plan, path)
        self.assertFalse(self.plan.exists())

    def test_sd_destination_symlink_is_rejected_even_when_bytes_match(self):
        self.dest.parent.mkdir(parents=True)
        self.dest.symlink_to(self.nro)
        with self.assertRaisesRegex(transfer.TransferError, "symbolic link"):
            self.plan_record()

    def test_symlink_parent_is_rejected(self):
        (self.mount / "switch").symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(transfer.TransferError, "symbolic link"):
            self.plan_record()

    def test_plan_must_be_host_side_and_exclusive(self):
        with self.assertRaisesRegex(transfer.TransferError, "outside"):
            transfer.create_plan(self.source, self.mount, self.mount / "transfer.json")
        with self.assertRaisesRegex(transfer.TransferError, "outside"):
            transfer.create_plan(self.source, self.mount, self.source / "transfer.json")
        self.plan_record()
        with self.assertRaisesRegex(transfer.TransferError, "already exists"):
            self.plan_record()

    def test_mount_must_not_alias_source_or_be_symlink(self):
        with self.assertRaisesRegex(transfer.TransferError, "separate"):
            transfer.create_plan(self.source, self.base, self.plan)
        alias = self.base / "sd-link"
        alias.symlink_to(self.mount, target_is_directory=True)
        with self.assertRaisesRegex(transfer.TransferError, "symbolic link"):
            transfer.create_plan(self.source, alias, self.plan)

    def test_plan_forged_pass_is_rejected(self):
        self.plan_record()
        plan = json.loads(self.plan.read_text())
        plan["hardware_status"] = "PASS"
        self.plan.write_text(json.dumps(plan))
        with self.assertRaisesRegex(transfer.TransferError, "must not claim"):
            transfer.read_plan(self.plan)

    def test_read_plan_duplicate_json_keys_is_rejected(self):
        self.plan.write_text('{"schema":"x","schema":"y"}')
        with self.assertRaisesRegex(bundle.BundleError, "duplicate JSON key"):
            transfer.read_plan(self.plan)

    def test_cli_plan_and_verify_exit_codes(self):
        command = [sys.executable, str(ROOT / "tools" /
                                      "verify_switch_audio_sd_transfer.py")]
        prepare = subprocess.run(
            command + ["plan", str(self.source), "--sd-root", str(self.mount),
                       "--output", str(self.plan)],
            capture_output=True, text=True, check=False)
        self.assertEqual(prepare.returncode, 0, prepare.stdout + prepare.stderr)
        self.assertEqual(json.loads(prepare.stdout)["hardware_status"],
                         "HARDWARE NOT TESTED")
        early = subprocess.run(
            command + ["verify", str(self.source), "--sd-root", str(self.mount),
                       "--plan", str(self.plan)],
            capture_output=True, text=True, check=False)
        self.assertEqual(early.returncode, 2, early.stdout + early.stderr)
        self.assertEqual(json.loads(early.stdout)["result"], "FAILED")
        self.manual_copy()
        good = subprocess.run(
            command + ["verify", str(self.source), "--sd-root", str(self.mount),
                       "--plan", str(self.plan)],
            capture_output=True, text=True, check=False)
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.assertEqual(json.loads(good.stdout)["result"],
                         "DESTINATION_BYTES_MATCH_PLANNED_NRO")


if __name__ == "__main__":
    unittest.main()
