"""Mocked original inputs + real private filesystem layout, no game bytes."""
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import tools.check_map02_private_cycle_readiness as readiness
from tools.map02_local_capture_handoff import (
    PLAN, PLAN_SCHEMA, PINNED_UPSTREAM_REF, REQUIRED_DIAGNOSTIC_MACROS,
)


class PrivateCycleReadinessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="vh-map02-ready-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.roles = ("source", "native", "scoped", "handoff",
                      "cycle", "preview", "preoverlay")
        self.dirs = {key: self.root / key for key in self.roles}
        for value in self.dirs.values():
            value.mkdir(mode=0o700)
        self.binary = self.root / "synthetic-pc-elf"
        self.image = self.root / "synthetic-owned-image"
        self.upstream = self.root / "fake-source"
        self.bundle = self.root / "fake-overlay"
        self.receipt = self.root / "fake-build-receipt"
        self.plan = {
            "schema": PLAN_SCHEMA,
            "pinned_original_pc_source_commit": PINNED_UPSTREAM_REF,
            "target_gpu_draw_frame": 12,
            "pinned_upstream_source_identity_sha256": "a" * 64,
            "pc_executable_sha256": "b" * 64,
            "owned_game_image_sha256": "c" * 64,
            "diagnostic_compile_macros": list(REQUIRED_DIAGNOSTIC_MACROS),
            "gameplay_origin_authenticated": False,
            "physical_ps1_equivalence_proven": False,
        }
        self.save_plan()
        self.game_proof = ((1, 2, 3, 4), "c" * 64)
        mocks = (
            ("verify_pinned_upstream", "a" * 64),
            ("stable_owned_elf_sha256", "b" * 64),
            ("audit_cycle_elf", {"required_symbols_present": 22}),
            ("_stable_owned_cycle_image", self.game_proof),
            ("verify_build_receipt", {
                "source_pinned_full_elf_bytes_checked": True}),
        )
        self.patches = [
            patch.object(readiness, name, return_value=result)
            for name, result in mocks
        ]
        self.mocks = [p.start() for p in self.patches]
        for entry in self.patches:
            self.addCleanup(entry.stop)

    def save_plan(self):
        f = self.dirs["handoff"] / PLAN
        f.write_bytes(
            (json.dumps(self.plan, sort_keys=True, separators=(",", ":"))
             + "\n").encode())
        f.chmod(0o600)

    def verify(self):
        return readiness.verify_private_cycle_readiness(
            *(self.dirs[role] for role in self.roles),
            pc_binary=self.binary, owned_game_image=self.image,
            upstream_checkout=self.upstream,
            build_receipt_dir=self.receipt, build_bundle_dir=self.bundle)

    def test_original_source_and_owned_game_bindings_checked_without_execution(self):
        with patch("subprocess.Popen",
                   side_effect=AssertionError("never execute native PC ELF")):
            result = self.verify()
        self.assertTrue(result["ready_for_controlled_local_launch"])
        self.assertEqual(result["private_directories_checked"], 7)
        self.assertEqual(result["capture_folders_empty"], 5)
        for flag in ("gameplay_process_started", "original_map02_rendering_proven",
                     "hardware_ps1_equivalence_proven", "game_content_emitted"):
            self.assertFalse(result[flag])
        self.assertEqual(self.mocks[0].call_count, 2)
        self.assertEqual(self.mocks[1].call_count, 2)
        self.assertEqual(self.mocks[3].call_count, 2)
        self.mocks[4].assert_called_once()

    def test_rejects_source_executable_and_image_drift_from_plan(self):
        for index, bad, phrase in (
            (0, "0" * 64, "source identity"),
            (1, "0" * 64, "executable differs"),
            (3, ((1, 2, 3, 4), "0" * 64), "game image differs"),
        ):
            with self.subTest(index=index):
                with patch.object(readiness,
                                  ("verify_pinned_upstream",
                                   "stable_owned_elf_sha256", None,
                                   "_stable_owned_cycle_image")[index],
                                  return_value=bad):
                    with self.assertRaisesRegex(ValueError, phrase):
                        self.verify()

    def test_rejects_invalid_or_missing_full_build_receipt(self):
        with patch.object(readiness, "verify_build_receipt",
                          return_value={"source_pinned_full_elf_bytes_checked": False}):
            with self.assertRaisesRegex(ValueError, "build provenance"):
                self.verify()
        with patch.object(readiness, "verify_build_receipt",
                          side_effect=ValueError("no matching original US build")):
            with self.assertRaisesRegex(ValueError, "matching original"):
                self.verify()

    def test_rejects_elf_symbols_or_plan_authentication_override(self):
        with patch.object(readiness, "audit_cycle_elf",
                          return_value={"required_symbols_present": 0}):
            with self.assertRaisesRegex(ValueError, "cycle symbols"):
                self.verify()
        self.plan["gameplay_origin_authenticated"] = True
        self.save_plan()
        with self.assertRaisesRegex(ValueError, "overstated"):
            self.verify()

    def test_rejects_game_or_elf_replacement_in_second_audit(self):
        for name, outcome, phrase in (
            ("stable_owned_elf_sha256", ["b" * 64, "f" * 64],
             "changed during preflight"),
            ("_stable_owned_cycle_image",
             [self.game_proof, ((1, 44, 3, 4), "c" * 64)],
             "changed during preflight"),
            ("verify_pinned_upstream", ["a" * 64, "f" * 64],
             "changed during preflight"),
        ):
            with self.subTest(name=name):
                with patch.object(readiness, name, side_effect=outcome):
                    with self.assertRaisesRegex(ValueError, phrase):
                        self.verify()

    def test_rejects_late_unexpected_capture_output(self):
        first = readiness.inspect_private_launch_layout

        def mutate(*args):
            output = first(*args)
            if not (self.dirs["native"] / "late-data").exists():
                (self.dirs["native"] / "late-data").write_bytes(b"synthetic")
            return output

        with patch.object(readiness, "inspect_private_launch_layout",
                          side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "not empty"):
                self.verify()

    def test_rejects_identical_bytes_plan_inode_swap(self):
        plan = self.dirs["handoff"] / PLAN
        backup = self.root / "old-plan-outside-capture"
        def swap_after_verification(*args, **kwargs):
            raw = plan.read_bytes()
            plan.replace(backup)
            plan.write_bytes(raw)
            plan.chmod(0o600)
            return {"source_pinned_full_elf_bytes_checked": True}
        with patch.object(readiness, "verify_build_receipt",
                          side_effect=swap_after_verification):
            with self.assertRaisesRegex(ValueError, "changed during preflight"):
                self.verify()
        self.assertTrue(backup.exists())

    def test_rejects_same_layout_after_directory_inode_swap(self):
        original = self.dirs["preview"]
        backup = self.root / "former-preview-dir"
        def swap_preview_dir(*args, **kwargs):
            original.replace(backup)
            original.mkdir(mode=0o700)
            return {"source_pinned_full_elf_bytes_checked": True}
        with patch.object(readiness, "verify_build_receipt",
                          side_effect=swap_preview_dir):
            with self.assertRaisesRegex(ValueError, "layout changed"):
                self.verify()
        self.assertTrue(backup.is_dir())

    def test_cli_redacts_private_paths_in_process_and_io_failures(self):
        private = "/private/user/SLUS_004.47"
        args = (["map02-ready"] +
                [str(self.dirs[name]) for name in self.roles] +
                ["--pc-binary", str(self.binary),
                 "--owned-game-image", str(self.image),
                 "--upstream-checkout", str(self.upstream),
                 "--build-receipt-dir", str(self.receipt),
                 "--build-bundle-dir", str(self.bundle)])
        for error in (OSError("disk missing " + private),
                      ValueError("original EXE " + private),
                      subprocess.TimeoutExpired([private], 2, output=b"secret")):
            with self.subTest(error=type(error).__name__):
                stderr = io.StringIO()
                with (patch("sys.argv", args),
                      patch.object(readiness, "verify_private_cycle_readiness",
                                   side_effect=error),
                      redirect_stderr(stderr)):
                    with self.assertRaises(SystemExit) as aborted:
                        readiness.main()
                self.assertEqual(aborted.exception.code, 2)
                self.assertIn("readiness unavailable", stderr.getvalue())
                self.assertNotIn(private, stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
