"""Synthetic read-only MAP02 private-input inventory tests.

No original Vandal Hearts game, ROM/BIOS, retail ELF, asset or disc is used.
These only exercise pathname/owner/mode inventory and non-disclosure.
"""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import tools.inspect_map02_private_inputs as inventory
from tools.check_map02_private_pc_inputs import ASSETS, EXE, FONT_GENERATOR
from tools.check_map02_cycle_make_plan import BUILD
from tools.map02_cycle_build_provenance import NAME as RECEIPT
from tools.map02_local_capture_handoff import PLAN


class Map02PrivateInputInventoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="vh-map02-input-list-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.upstream = self.root / "source-checkout"
        self.upstream.mkdir()
        self.disc = self.root / "owned-synthetic-disc"
        self.bundle = self.root / "prepared-build-overlay"
        self.receipt = self.root / "build-receipt"
        self.handoff = self.root / "capture-handoff"
        for folder in (self.bundle, self.receipt, self.handoff):
            folder.mkdir(mode=0o700)
        self.krom = self.root / "synthetic-KROMDAT.BIN"
        self.paths = (
            self.upstream, self.disc, self.bundle,
            self.receipt, self.handoff)
        self.private_path = str(self.disc)

    @staticmethod
    def make_file(path, *, mode=0o600):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic file only - never actual original content")
        path.chmod(mode)
        return path

    def populate(self):
        self.make_file(self.upstream / EXE)
        self.make_file(self.upstream / "build" / (EXE + ".elf"))
        self.make_file(self.upstream / FONT_GENERATOR)
        self.make_file(self.krom)
        for name in ASSETS:
            self.make_file(self.upstream / "assets" / name)
        self.make_file(self.disc)
        self.make_file(
            self.upstream / "platform/pc" / BUILD / "vandalhearts_pc",
            mode=0o700)
        self.make_file(self.bundle / "map02_cycle_build_inputs.json")
        self.make_file(self.bundle / "map02_cycle.mk")
        self.make_file(self.receipt / RECEIPT)
        self.make_file(self.handoff / PLAN)

    def inspect(self):
        return inventory.inspect_private_map02_inputs(
            *self.paths, krom_source=self.krom)

    def test_missing_original_paths_return_false_without_disclosing_paths(self):
        result = self.inspect()
        self.assertFalse(result["all_prerequisite_paths_present"])
        self.assertFalse(result["original_us_psx_executable_path_present"])
        self.assertFalse(result["owned_disc_image_private_path_present"])
        self.assertEqual(result["original_asset_include_paths_present"], 0)
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertFalse(result["ready_for_controlled_local_launch"])
        self.assertFalse(result["gameplay_process_started"])

    def test_complete_synthetic_inventory_is_only_presence_not_authentication(self):
        self.populate()
        files = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*") if path.is_file()
        }
        with (patch("builtins.open", side_effect=AssertionError("no file reads")),
              patch("subprocess.Popen", side_effect=AssertionError("no subprocess")),
              patch.object(Path, "read_bytes",
                           side_effect=AssertionError("no asset reads"))):
            result = self.inspect()
        self.assertTrue(result["all_prerequisite_paths_present"])
        self.assertEqual(
            result["original_asset_include_paths_present"], len(ASSETS))
        for key in ("original_file_bytes_verified",
                    "build_provenance_authenticated",
                    "ready_for_controlled_local_launch",
                    "gameplay_process_started",
                    "original_map02_rendering_proven",
                    "private_game_files_uploaded"):
            self.assertIs(result[key], False)
        self.assertEqual(files, {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*") if path.is_file()
        })
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_missing_or_malformed_prerequisite_is_localized_by_category(self):
        self.populate()
        original = self.inspect()
        self.assertTrue(original["all_prerequisite_paths_present"])
        (self.upstream / "assets" / ASSETS[1]).unlink()
        report = self.inspect()
        self.assertEqual(report["original_asset_include_paths_present"],
                         len(ASSETS) - 1)
        self.assertFalse(report["all_prerequisite_paths_present"])
        self.make_file(self.upstream / "assets" / ASSETS[1])
        self.disc.chmod(0o644)
        report = self.inspect()
        self.assertFalse(report["owned_disc_image_private_path_present"])
        self.assertFalse(report["all_prerequisite_paths_present"])
        self.disc.chmod(0o600)
        (self.receipt / RECEIPT).unlink()
        linked = self.root / "fake-receipt"
        self.make_file(linked)
        (self.receipt / RECEIPT).symlink_to(linked)
        report = self.inspect()
        self.assertFalse(report["private_build_receipt_path_present"])
        self.assertFalse(report["all_prerequisite_paths_present"])

    def test_executable_and_private_folders_require_expected_modes(self):
        self.populate()
        pc = self.upstream / "platform/pc" / BUILD / "vandalhearts_pc"
        pc.chmod(0o600)
        self.assertFalse(self.inspect()["full_pc_elf_executable_path_present"])
        pc.chmod(0o700)
        self.handoff.chmod(0o755)
        self.assertFalse(self.inspect()["private_handoff_directory_present"])
        self.assertFalse(self.inspect()["private_capture_plan_path_present"])
        self.handoff.chmod(0o700)
        self.assertTrue(self.inspect()["all_prerequisite_paths_present"])

    def test_cli_emits_only_safe_status_fields_not_private_arguments(self):
        self.populate()
        import sys
        args = ["inspect-map02-private-inputs", *(str(p) for p in self.paths),
                "--krom-source", str(self.krom)]
        output = io.StringIO()
        with patch.object(sys, "argv", args), redirect_stdout(output):
            inventory.main()
        parsed = json.loads(output.getvalue())
        self.assertTrue(parsed["all_prerequisite_paths_present"])
        self.assertFalse(parsed["original_file_bytes_verified"])
        for path in self.paths + (self.krom,):
            self.assertNotIn(str(path), output.getvalue())


if __name__ == "__main__":
    unittest.main()
