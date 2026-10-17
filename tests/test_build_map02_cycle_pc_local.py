"""The full game build runner is exercised with *mocked* make/link only.

These tests do not create a real game binary or use any proprietary assets.
"""
from pathlib import Path
from contextlib import redirect_stderr
import io
import subprocess
import tools.build_map02_cycle_pc_local as local_build
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from tools.build_map02_cycle_pc_local import build_full_pc


class PrivateFullPcBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-local-build-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.pc = root / "pinned-upstream/platform/pc"
        self.pc.mkdir(parents=True)
        self.upstream = self.pc.parent.parent
        self.bundle = root / "private-bundle"
        self.bundle.mkdir(mode=0o700)
        (self.bundle / "map02_cycle.mk").write_text("private overlay\n")
        self.exe = self.pc / "build-map02-cycle/vandalhearts_pc"
        self.plan = {
            "full_game_link_command_sha256": "a" * 64,
        }
        self.patches = [
            patch("tools.build_map02_cycle_pc_local.audit",
                  return_value=self.plan),
            patch("tools.check_map02_cycle_make_plan.preflight",
                  return_value=self.bundle / "map02_cycle.mk"),
            patch("tools.build_map02_cycle_pc_local.audit_cycle_elf",
                  return_value={"required_symbols_present": 19}),
            patch("tools.build_map02_cycle_pc_local.verify_linked_original_font",
                  return_value={"pinned_original_krom_font_c_identical": True}),
            patch("tools.check_map02_private_pc_inputs.verify_private_pc_inputs",
                  return_value={
                      "private_build_inputs_binding_sha256": "9" * 64,
                      "original_map02_rendering_proven": False}),
        ]
        self.active = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)

    def build_fake(self, command, *, cwd, env, capture_output, text, timeout, check):
        self.assertEqual(cwd, self.pc)
        self.assertEqual(command[1], "-j1")
        self.assertIn("NO_HDVIDEO=1", command)
        self.assertIn("NO_WEBP=1", command)
        self.assertIn("BUILD_DIR=build-map02-cycle", command)
        self.assertNotIn("VH_ALLOW_UNVERIFIED_EXE", env)
        self.assertEqual(env.get("VH_KROM_SOURCE"), str(
            self.upstream / "external/psy-q/3.6/PSYQ/BIN/KROMDAT.BIN"))
        self.assertEqual(env.get("VH_REGION"), "us")
        self.assertEqual(env.get("VH_PSX_EXE"), str(self.upstream / "SLUS_004.47"))
        self.exe.parent.mkdir(parents=True, exist_ok=True)
        self.exe.parent.chmod(0o700)
        self.exe.write_bytes(b"synthetic; not an ELF")
        self.exe.chmod(0o700)
        return SimpleNamespace(returncode=0)

    def test_local_game_build_drops_inherited_makefile_and_eval_options(self):
        from tools.check_map02_cycle_make_plan import (
            INHERITED_MAKE_CONTROLS, INHERITED_PYTHON_CONTROLS)
        controls = INHERITED_MAKE_CONTROLS + INHERITED_PYTHON_CONTROLS
        inherited = {name: "injected-" + name for name in controls}

        def verify_make_environment(command, **kwargs):
            for key in controls:
                self.assertNotIn(key, kwargs["env"])
            return self.build_fake(command, **kwargs)

        with patch.dict(local_build.os.environ, inherited), patch(
                "tools.build_map02_cycle_pc_local.subprocess.run",
                side_effect=verify_make_environment):
            build_full_pc(self.upstream, self.bundle)

    def test_standalone_success_reporting_never_claims_runtime(self):
        with patch("tools.build_map02_cycle_pc_local.subprocess.run",
                   side_effect=self.build_fake):
            result = build_full_pc(self.upstream, self.bundle)
        self.assertTrue(result["full_elf_linked"])
        self.assertFalse(result["actual_gameplay_executed"])
        self.assertFalse(result["original_map02_rendering_proven"])
        self.assertFalse(result["physical_ps1_equivalence_proven"])
        self.assertFalse(result["hd_substitution_enabled"])
        self.assertEqual(result["required_original_cycle_and_gpu_symbols"], 19)
        self.assertEqual(len(result["pc_executable_sha256"]), 64)
        self.assertEqual(result["private_retail_inputs_binding_sha256"], "9" * 64)

    def test_unstable_original_elf_digest_prevents_private_receipt(self):
        with (patch("tools.build_map02_cycle_pc_local.subprocess.run",
                    side_effect=self.build_fake),
              patch("tools.build_map02_cycle_pc_local.stable_owned_elf_sha256",
                    side_effect=ValueError("private ELF digest input changed during hashing")),
              patch("tools.map02_cycle_build_provenance.create_build_receipt") as publish):
            with self.assertRaisesRegex(ValueError, "changed during hashing"):
                build_full_pc(self.upstream, self.bundle,
                              report_dir=self.upstream.parent / "report")
        publish.assert_not_called()

    def test_optional_private_build_receipt_emitted_only_after_elf_audit(self):
        report_dir = self.upstream.parent / "build-receipt"
        report_dir.mkdir(mode=0o700)
        with patch("tools.build_map02_cycle_pc_local.subprocess.run",
                   side_effect=self.build_fake), patch(
                "tools.map02_cycle_build_provenance.create_build_receipt",
                return_value={
                    "private_build_receipt_sha256": "e" * 64,
                    "retail_gameplay_executed": False,
                }) as publisher:
            result = build_full_pc(
                self.upstream, self.bundle, report_dir=report_dir)
        publisher.assert_called_once()
        self.assertEqual(result["private_build_receipt_sha256"], "e" * 64)
        self.assertFalse(result["retail_gameplay_executed"])

    def test_no_overwrite_even_when_prior_target_is_symlink(self):
        self.exe.parent.mkdir(parents=True, exist_ok=True)
        self.exe.parent.chmod(0o700)
        self.exe.symlink_to(self.bundle / "map02_cycle.mk")
        with patch("tools.build_map02_cycle_pc_local.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "already exists"):
                build_full_pc(self.upstream, self.bundle)
        run.assert_not_called()

    def test_no_overwrite_existing_file(self):
        self.exe.parent.mkdir(parents=True, exist_ok=True)
        self.exe.parent.chmod(0o700)
        self.exe.write_text("preserve")
        with self.assertRaisesRegex(ValueError, "already exists"):
            build_full_pc(self.upstream, self.bundle)
        self.assertEqual(self.exe.read_text(), "preserve")

    def test_cli_redacts_private_owned_paths_from_filesystem_errors(self):
        private_path = str(self.upstream / "SLUS_004.47")
        output = io.StringIO()
        with (
                patch("sys.argv", [
                    "private-build", str(self.upstream), str(self.bundle),
                    "--report-dir", str(self.upstream.parent / "receipt")]),
                patch.object(local_build, "build_full_pc",
                             side_effect=OSError("Cannot access " + private_path)),
                redirect_stderr(output)):
            with self.assertRaises(SystemExit) as thrown:
                local_build.main()
        self.assertEqual(thrown.exception.code, 2)
        self.assertIn("filesystem verification failed", output.getvalue())
        self.assertNotIn(private_path, output.getvalue())

    def test_preexisting_generated_font_or_symlink_blocks_build(self):
        private_c = self.exe.parent / "map02_pinned_kanji_font.c"
        private_c.parent.mkdir(parents=True, exist_ok=True)
        private_c.parent.chmod(0o700)
        private_c.write_bytes(b"synthetic-original-font-placeholder")
        with patch("tools.build_map02_cycle_pc_local.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "generated KROM source already exists"):
                build_full_pc(self.upstream, self.bundle)
        run.assert_not_called()
        private_c.unlink()
        private_c.symlink_to(self.bundle / "map02_cycle.mk")
        with patch("tools.build_map02_cycle_pc_local.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "generated KROM source already exists"):
                build_full_pc(self.upstream, self.bundle)
        run.assert_not_called()

    def test_byte_identical_build_folder_inode_swap_after_make_is_rejected(self):
        def swap_after_make(command, **kwargs):
            result = self.build_fake(command, **kwargs)
            original = self.exe.parent
            saved = original.with_name("swapped-synthetic-build")
            original.rename(saved)
            original.mkdir(mode=0o700)
            # The replacement contains an identical would-be successful ELF.
            # Only the directory identity distinguishes this attack.
            self.exe.write_bytes((saved / "vandalhearts_pc").read_bytes())
            self.exe.chmod(0o700)
            return result

        with patch("tools.build_map02_cycle_pc_local.subprocess.run",
                   side_effect=swap_after_make):
            with self.assertRaisesRegex(ValueError, "replaced during link"):
                build_full_pc(self.upstream, self.bundle)

    def test_existing_world_visible_build_directory_is_rejected(self):
        self.exe.parent.mkdir(parents=True, exist_ok=True)
        self.exe.parent.chmod(0o755)
        with patch("tools.build_map02_cycle_pc_local.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "owner 0700"):
                build_full_pc(self.upstream, self.bundle)
        run.assert_not_called()

    def test_linked_build_directory_cannot_redirect_private_generated_font(self):
        redirected = self.upstream.parent / "foreign-build-output"
        redirected.mkdir()
        self.exe.parent.symlink_to(redirected, target_is_directory=True)
        with patch("tools.build_map02_cycle_pc_local.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "directory linked"):
                build_full_pc(self.upstream, self.bundle)
        run.assert_not_called()
        self.assertFalse(any(redirected.iterdir()))

    def test_preexisting_font_object_or_symlink_prevents_stale_reuse(self):
        font_object = self.exe.parent / "pc_kanji_font.o"
        font_object.parent.mkdir(parents=True, exist_ok=True)
        font_object.parent.chmod(0o700)
        font_object.write_bytes(b"old synthetic object with future timestamp")
        with patch("tools.build_map02_cycle_pc_local.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "KROM object already exists"):
                build_full_pc(self.upstream, self.bundle)
        run.assert_not_called()
        font_object.unlink()
        font_object.symlink_to(self.bundle / "map02_cycle.mk")
        with patch("tools.build_map02_cycle_pc_local.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "KROM object already exists"):
                build_full_pc(self.upstream, self.bundle)
        run.assert_not_called()

    def test_compiler_failure_is_private_and_not_reported(self):
        with patch("tools.build_map02_cycle_pc_local.subprocess.run",
                   return_value=SimpleNamespace(returncode=1,
                                                stderr="/private/secret-image.bin")):
            with self.assertRaisesRegex(ValueError, "compiler output withheld") as raised:
                build_full_pc(self.upstream, self.bundle)
        self.assertNotIn("/private/secret-image.bin", str(raised.exception))

    def test_missing_output_does_not_publish_success(self):
        with patch("tools.build_map02_cycle_pc_local.subprocess.run",
                   return_value=SimpleNamespace(returncode=0)):
            with self.assertRaisesRegex(ValueError, "without an executable"):
                build_full_pc(self.upstream, self.bundle)

    def test_invalid_private_font_c_blocks_success_and_receipt(self):
        with patch("tools.build_map02_cycle_pc_local.verify_linked_original_font",
                   side_effect=ValueError("generated private font C differs")), patch(
                "tools.build_map02_cycle_pc_local.subprocess.run",
                side_effect=self.build_fake), patch(
                "tools.map02_cycle_build_provenance.create_build_receipt") as publish:
            with self.assertRaisesRegex(ValueError, "font C differs"):
                build_full_pc(self.upstream, self.bundle)
        publish.assert_not_called()

    def test_fail_closed_after_link_when_elf_audit_rejects_symbols(self):
        self.active[2].side_effect = ValueError("required DrawOTag symbol missing")
        with patch("tools.build_map02_cycle_pc_local.subprocess.run",
                   side_effect=self.build_fake):
            with self.assertRaisesRegex(ValueError, "DrawOTag"):
                build_full_pc(self.upstream, self.bundle)

    def test_validated_explicit_krom_override_reaches_full_game_generator(self):
        source = self.upstream / "private-owned-bios.bin"
        source.write_bytes(b"synthetic")
        # The actual resource validator is mocked in all build-driver
        # tests. In production it rejects nonoriginal BIOS bytes here.
        def fake_with_bios(command, *, cwd, env, capture_output,
                           text, timeout, check):
            self.assertEqual(env.get("VH_KROM_SOURCE"), str(source))
            self.assertEqual(env.get("VH_REGION"), "us")
            self.assertEqual(env.get("VH_PSX_EXE"),
                             str(self.upstream / "SLUS_004.47"))
            self.exe.parent.mkdir(parents=True, exist_ok=True)
            self.exe.parent.chmod(0o700)
            self.exe.write_bytes(b"synthetic; not a game")
            self.exe.chmod(0o700)
            return SimpleNamespace(returncode=0)
        with patch("tools.build_map02_cycle_pc_local.subprocess.run",
                   side_effect=fake_with_bios):
            result = build_full_pc(
                self.upstream, self.bundle, krom_source=source)
        self.assertFalse(result["actual_gameplay_executed"])

    def test_retail_input_changed_during_link_rejects_private_build(self):
        with patch("tools.check_map02_private_pc_inputs.verify_private_pc_inputs",
                   side_effect=[
                       {"private_build_inputs_binding_sha256": "9" * 64},
                       {"private_build_inputs_binding_sha256": "8" * 64},
                   ]), patch("tools.build_map02_cycle_pc_local.subprocess.run",
                             side_effect=self.build_fake):
            with self.assertRaisesRegex(ValueError, "changed during PC build"):
                build_full_pc(self.upstream, self.bundle)

    def test_bad_time_limits_and_changed_bundle_rejected_before_make(self):
        with self.assertRaisesRegex(ValueError, "timeout"):
            build_full_pc(self.upstream, self.bundle, timeout=4)
        self.active[0].side_effect = ValueError("changed private build source")
        with patch("tools.build_map02_cycle_pc_local.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "changed private"):
                build_full_pc(self.upstream, self.bundle)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
