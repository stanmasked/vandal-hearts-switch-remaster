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
                                          KROM_US_BYTES, check_disc_image,
                                          identify_disc_boot_family, inspect)


def fake_sources(root):
    for rel in REQUIRED_SOURCE_FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("/* fixture */\n", encoding="utf-8")
    exe = root / "SLUS_004.47"
    exe.write_bytes(b"fixture US game executable")
    krom = root / "KROMDAT.BIN"
    krom.write_bytes(b"K" * KROM_US_BYTES)
    disc = root / "game.bin"
    raw = bytearray(500 * 2352)
    raw[16 * 2352 + 24:16 * 2352 + 24 + 7] = b"\x01CD001\x01"
    raw[23 * 2352 + 24:23 * 2352 + 24 + 8] = b"PS-X EXE"
    image_offset = (0x800f5551 - 0x80010000) + 0x800
    ident_offset = ((23 + image_offset // 2048) * 2352
                    + 24 + image_offset % 2048)
    raw[ident_offset:ident_offset + 14] = b"BASLUS-00447VH"
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
                       hashlib.md5(exe.read_bytes()).hexdigest()), \
                 patch("tools.preflight_map02_pcport.KROM_US_SHA256",
                       hashlib.sha256(krom.read_bytes()).hexdigest()):
                report = inspect(root, disc_image=disc, krom_source=krom)
            self.assertTrue(report["ready_for_attempt"], report)
            self.assertEqual(report["blockers"], [])
            self.assertTrue(report["checks"]["disc_raw_layout_ok"])
            self.assertTrue(report["checks"]["retail_executable_md5_matches"])
            self.assertEqual(report["checks"]["upstream_revision"], UPSTREAM_COMMIT)

    def test_tracked_upstream_edits_are_rejected_but_untracked_files_allowed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe, krom, disc = fake_sources(root)
            subprocess.run(["git", "init", "-q", str(root)],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", str(root), "add",
                            *REQUIRED_SOURCE_FILES],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.email=trace@example.invalid",
                            "-c", "user.name=Trace Test", "commit", "-qm", "fixture"],
                           check=True, capture_output=True)

            def controlled_run(args, *, cwd=None):
                if "rev-parse" in args:
                    return SimpleNamespace(returncode=0,
                                           stdout=UPSTREAM_COMMIT + "\n")
                if "status" in args:
                    return subprocess.run(args, cwd=cwd, capture_output=True,
                                          text=True, check=False)
                return SimpleNamespace(returncode=0, stdout="")

            with patch("tools.preflight_map02_pcport._run",
                       side_effect=controlled_run), \
                 patch("tools.preflight_map02_pcport.US_EXE_MD5",
                       hashlib.md5(exe.read_bytes()).hexdigest()), \
                 patch("tools.preflight_map02_pcport.KROM_US_SHA256",
                       hashlib.sha256(krom.read_bytes()).hexdigest()):
                clean = inspect(root, disc_image=disc, krom_source=krom,
                                no_hdvideo=True, no_webp=True)
                self.assertTrue(clean["checks"]["upstream_tracked_tree_clean"])
                self.assertNotIn("upstream_tracked_tree_dirty", clean["blockers"])
                # Proprietary/game-derived files may be untracked; they do not
                # dirty the pinned source integrity check.
                (root / "private-asset.bin").write_bytes(b"not git tracked")
                untracked = inspect(root, disc_image=disc, krom_source=krom,
                                    no_hdvideo=True, no_webp=True)
                self.assertTrue(untracked["checks"]["upstream_tracked_tree_clean"])
                edited = root / REQUIRED_SOURCE_FILES[0]
                edited.write_text("/* modified original */\n")
                dirty = inspect(root, disc_image=disc, krom_source=krom,
                                no_hdvideo=True, no_webp=True)
                self.assertIn("upstream_tracked_tree_dirty", dirty["blockers"])
                self.assertIn(REQUIRED_SOURCE_FILES[0],
                              dirty["checks"]["upstream_modified_tracked_paths"])
                # Restore working tree, then verify staged-only changes are
                # also detected, not just unstaged file edits.
                subprocess.run(["git", "-C", str(root), "checkout", "--",
                                REQUIRED_SOURCE_FILES[0]],
                               check=True, capture_output=True)
                edited.write_text("/* modified in git index */\n")
                subprocess.run(["git", "-C", str(root), "add",
                                REQUIRED_SOURCE_FILES[0]],
                               check=True, capture_output=True)
                staged = inspect(root, disc_image=disc, krom_source=krom,
                                 no_hdvideo=True, no_webp=True)
                self.assertIn("upstream_tracked_tree_dirty", staged["blockers"])

    def test_unavailable_git_status_never_passes_source_check(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe, krom, disc = fake_sources(root)
            def broken_status(args, *, cwd=None):
                if "status" in args:
                    return SimpleNamespace(returncode=128, stdout="")
                return fake_run(args, cwd=cwd)
            with patch("tools.preflight_map02_pcport._run",
                       side_effect=broken_status):
                result = inspect(root, disc_image=disc, krom_source=krom)
            self.assertIn("upstream_tracked_tree_unverified", result["blockers"])
            self.assertFalse(result["checks"]["upstream_tracked_tree_clean"])

    def test_localized_or_changed_executable_must_not_pass_us_data_generator_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe, krom, disc = fake_sources(root)
            with patch("tools.preflight_map02_pcport._run", side_effect=fake_run):
                report = inspect(root, disc_image=disc, krom_source=krom)
            self.assertIn("retail_executable_md5_mismatch", report["blockers"])
            self.assertFalse(report["ready_for_attempt"])
            # A patched/localized executable may preserve the original boot/card ID.
            # Runtime family recognition is not proof of exact retail executable identity.
            self.assertEqual(report["checks"]["disc_boot_id_family"], "USA")
            self.assertTrue(report["checks"]["disc_boot_id_accepted_by_us_runtime"])
            self.assertFalse(report["checks"]["disc_exact_retail_release_verified"])
            self.assertIn("localized or patched content",
                          report["checks"]["disc_identification_basis"])

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
                if "rev-parse" in args or "status" in args:
                    return fake_run(args)
                return SimpleNamespace(returncode=0 if args[-1] in ("sdl2", "openal") else 1,
                                       stdout="")
            with patch("tools.preflight_map02_pcport._run", side_effect=deps), \
                 patch("tools.preflight_map02_pcport.shutil.which", side_effect=lambda x: "/usr/bin/" + x), \
                 patch("tools.preflight_map02_pcport.US_EXE_MD5",
                       hashlib.md5(exe.read_bytes()).hexdigest()), \
                 patch("tools.preflight_map02_pcport.KROM_US_SHA256",
                       hashlib.sha256(krom.read_bytes()).hexdigest()):
                full = inspect(root, disc_image=disc, krom_source=krom)
                minimal = inspect(root, disc_image=disc, krom_source=krom,
                                  no_webp=True, no_hdvideo=True)
            self.assertIn("pkg_libwebp_missing", full["blockers"])
            self.assertIn("pkg_libavformat_missing", full["blockers"])
            self.assertNotIn("pkg_sdl2_missing", full["blockers"])
            self.assertTrue(minimal["ready_for_attempt"])
            self.assertNotIn("pkg_libwebp", minimal["checks"])

    def test_krom_requires_precise_generator_glyph_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe, krom, disc = fake_sources(root)
            with patch("tools.preflight_map02_pcport._run", side_effect=fake_run), \
                 patch("tools.preflight_map02_pcport.US_EXE_MD5",
                       hashlib.md5(exe.read_bytes()).hexdigest()):
                report = inspect(root, disc_image=disc, krom_source=krom)
            self.assertIn("krom_charset2_sha256_mismatch", report["blockers"])
            self.assertFalse(report["checks"]["krom_charset2_sha256_matches"])
            krom.write_bytes(b"K" * (KROM_US_BYTES - 1))
            short = inspect(root, disc_image=disc, krom_source=krom)
            self.assertIn("krom_source_too_small", short["blockers"])

    def test_complete_bios_region_is_hashed_from_correct_offset(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe, krom, disc = fake_sources(root)
            glyphs = krom.read_bytes()
            bios = bytearray(512 * 1024)
            bios[0x66000:0x66000 + KROM_US_BYTES] = glyphs
            bios_path = root / "scph1001.bin"
            bios_path.write_bytes(bios)
            with patch("tools.preflight_map02_pcport._run", side_effect=fake_run), \
                 patch("tools.preflight_map02_pcport.US_EXE_MD5",
                       hashlib.md5(exe.read_bytes()).hexdigest()), \
                 patch("tools.preflight_map02_pcport.KROM_US_SHA256",
                       hashlib.sha256(glyphs).hexdigest()):
                report = inspect(root, disc_image=disc, krom_source=bios_path)
            self.assertTrue(report["checks"]["krom_charset2_sha256_matches"])
            self.assertEqual(report["checks"]["krom_source_layout"], "full_bios")
            self.assertEqual(report["checks"]["krom_charset2_sha256"],
                             hashlib.sha256(glyphs).hexdigest())

    def test_us_and_asia_disc_boot_id_matches_pinned_libcd(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe, krom, disc = fake_sources(root)
            self.assertEqual(identify_disc_boot_family(disc), "USA")
            self.assertEqual(check_disc_image(disc)[0], True)
            image_offset = (0x800f5551 - 0x80010000) + 0x800
            ident_offset = ((23 + image_offset // 2048) * 2352
                            + 24 + image_offset % 2048)
            with disc.open("r+b") as handle:
                handle.seek(ident_offset)
                handle.write(b"BISCPS-45183VH")
            self.assertEqual(identify_disc_boot_family(disc), "Asia")
            with patch("tools.preflight_map02_pcport._run", side_effect=fake_run), \
                 patch("tools.preflight_map02_pcport.US_EXE_MD5",
                       hashlib.md5(exe.read_bytes()).hexdigest()), \
                 patch("tools.preflight_map02_pcport.KROM_US_SHA256",
                       hashlib.sha256(krom.read_bytes()).hexdigest()):
                result = inspect(root, disc_image=disc, krom_source=krom,
                                 no_webp=True, no_hdvideo=True)
            self.assertTrue(result["checks"]["disc_boot_id_accepted_by_us_runtime"])
            self.assertEqual(result["checks"]["disc_boot_id_family"], "Asia")

    def test_other_disc_with_valid_iso_pvd_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe, krom, disc = fake_sources(root)
            with disc.open("r+b") as handle:
                handle.seek(23 * 2352 + 24)
                handle.write(b"OTHER EX")
            self.assertEqual(identify_disc_boot_family(disc), "unknown")
            with patch("tools.preflight_map02_pcport._run", side_effect=fake_run):
                result = inspect(root, disc_image=disc, krom_source=krom)
            self.assertIn("disc_boot_id_unrecognized", result["blockers"])
            self.assertTrue(result["checks"]["disc_raw_layout_ok"])

    def test_japanese_disc_is_rejected_for_pinned_us_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe, krom, disc = fake_sources(root)
            image_offset = (0x800f76a9 - 0x80010000) + 0x800
            ident_offset = ((15200 + image_offset // 2048) * 2352
                            + 24 + image_offset % 2048)
            with disc.open("r+b") as handle:
                handle.seek(23 * 2352 + 24)
                handle.write(b"OTHER EX")
                handle.seek(15200 * 2352 + 24)
                handle.write(b"PS-X EXE")
                handle.seek(ident_offset)
                handle.write(b"BISLPM-86007VH")
                handle.truncate(((ident_offset // 2352) + 1) * 2352)
            self.assertEqual(identify_disc_boot_family(disc), "Japan")
            with patch("tools.preflight_map02_pcport._run", side_effect=fake_run):
                result = inspect(root, disc_image=disc, krom_source=krom)
            self.assertIn("disc_region_not_supported_by_us_build", result["blockers"])

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
