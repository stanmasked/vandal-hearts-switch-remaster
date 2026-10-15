"""Read-only synthetic preflight tests for the pinned PC-port diagnostics."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tools.preflight_map02_pcport import (UPSTREAM_COMMIT, REQUIRED_SOURCE_FILES,
                                          check_disc_image, inspect)


def fake_sources(root):
    for rel in REQUIRED_SOURCE_FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("/* fixture */\n", encoding="utf-8")
    exe = root / "SLUS_004.47"
    exe.write_bytes(b"fixture US game executable")
    krom = root / "KROMDAT.BIN"
    krom.write_bytes(b"K" * 4096)
    disc = root / "game.bin"
    raw = bytearray(18 * 2352)
    raw[16 * 2352 + 24:16 * 2352 + 24 + 7] = b"\x01CD001\x01"
    disc.write_bytes(raw)
    return exe, krom, disc


def fake_run(args, *, cwd=None):
    if "rev-parse" in args:
        return SimpleNamespace(returncode=0, stdout=UPSTREAM_COMMIT + "\n")
    return SimpleNamespace(returncode=0, stdout="")


class PreflightMap02PcportTests(unittest.TestCase):
    def test_ready_synthetic_host_with_expected_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe, krom, disc = fake_sources(root)
            with patch("tools.preflight_map02_pcport._run", side_effect=fake_run), \
                 patch("tools.preflight_map02_pcport.shutil.which", side_effect=lambda x: "/usr/bin/" + x), \
                 patch("tools.preflight_map02_pcport.US_EXE_MD5",
                       hashlib.md5(exe.read_bytes()).hexdigest()):
                report = inspect(root, disc_image=disc, krom_source=krom)
            self.assertTrue(report["ready_for_attempt"], report)
            self.assertEqual(report["blockers"], [])
            self.assertTrue(report["checks"]["disc_raw_layout_ok"])
            self.assertTrue(report["checks"]["retail_executable_md5_matches"])
            self.assertEqual(report["checks"]["upstream_revision"], UPSTREAM_COMMIT)

    def test_localized_or_changed_executable_must_not_pass_us_data_generator_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe, krom, disc = fake_sources(root)
            with patch("tools.preflight_map02_pcport._run", side_effect=fake_run):
                report = inspect(root, disc_image=disc, krom_source=krom)
            self.assertIn("retail_executable_md5_mismatch", report["blockers"])
            self.assertFalse(report["ready_for_attempt"])

    def test_raw_disc_structure_invalid_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe, krom, disc = fake_sources(root)
            self.assertEqual(check_disc_image(disc)[0], True)
            disc.write_bytes(b"\x00" * 2048)
            self.assertFalse(check_disc_image(disc)[0])
            with patch("tools.preflight_map02_pcport._run", side_effect=fake_run):
                report = inspect(root, disc_image=disc, krom_source=krom)
            self.assertIn("disc_raw_layout_invalid", report["blockers"])

    def test_missing_required_checkout_and_assets_are_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report = inspect(root)
            self.assertIn("upstream_source_files_missing", report["blockers"])
            self.assertIn("upstream_revision_unverified", report["blockers"])
            self.assertIn("retail_executable_missing", report["blockers"])
            self.assertIn("krom_source_missing", report["blockers"])
            self.assertIn("disc_image_not_specified", report["blockers"])

    def test_opt_out_of_hd_dependencies_does_not_hide_sdl_or_openal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe, krom, disc = fake_sources(root)
            def deps(args, *, cwd=None):
                if "rev-parse" in args:
                    return fake_run(args)
                return SimpleNamespace(returncode=0 if args[-1] in ("sdl2", "openal") else 1,
                                       stdout="")
            with patch("tools.preflight_map02_pcport._run", side_effect=deps), \
                 patch("tools.preflight_map02_pcport.shutil.which", side_effect=lambda x: "/usr/bin/" + x), \
                 patch("tools.preflight_map02_pcport.US_EXE_MD5",
                       hashlib.md5(exe.read_bytes()).hexdigest()):
                full = inspect(root, disc_image=disc, krom_source=krom)
                minimal = inspect(root, disc_image=disc, krom_source=krom,
                                  no_webp=True, no_hdvideo=True)
            self.assertIn("pkg_libwebp_missing", full["blockers"])
            self.assertIn("pkg_libavformat_missing", full["blockers"])
            self.assertNotIn("pkg_sdl2_missing", full["blockers"])
            self.assertTrue(minimal["ready_for_attempt"])
            self.assertNotIn("pkg_libwebp", minimal["checks"])

    def test_cli_reports_blockers_without_game_files(self):
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(
                [sys.executable, "-m", "tools.preflight_map02_pcport", folder],
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report["ready_for_attempt"])
            self.assertTrue(report["blockers"])
            self.assertIn("Read-only", report["notes"][0])


if __name__ == "__main__":
    unittest.main()
