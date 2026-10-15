"""Synthetic checks for the local, user-executed Map02 session preparation."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.prepare_map02_session import plan_session


class PrepareMap02SessionTests(unittest.TestCase):
    def _fixture(self, root):
        upstream = root / "upstream"
        upstream.mkdir()
        retail = upstream / "SLUS_004.47"
        retail.write_bytes(b"synthetic US exe")
        disc = root / "Disc image with spaces.bin"
        disc.write_bytes(b"synthetic image")
        krom = root / "KROM image with spaces.bin"
        krom.write_bytes(b"synthetic font")
        return upstream, retail, disc, krom

    def _preflight(self, krom):
        return {"ready_for_attempt": True, "blockers": [],
                "checks": {"krom_source_path": str(krom)}}

    def _prepare(self, upstream, directory, **options):
        self.assertEqual(options, {"full_trace": True})
        self.assertEqual(directory.name, "trace")
        directory.mkdir(parents=True)
        overlay = directory / "map02_trace.mk"
        overlay.write_text("# generated test overlay\n")
        return overlay

    def test_prepares_one_build_capture_verify_script_without_executing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream, retail, disc, krom = self._fixture(root)
            session = root / "session"
            before = retail.read_bytes()
            with patch("tools.prepare_map02_session.inspect",
                       return_value=self._preflight(krom)) as inspected, \
                 patch("tools.prepare_map02_session.prepare",
                       side_effect=self._prepare) as prepared:
                plan = plan_session(
                    upstream, session, disc_image=disc,
                    krom_source=krom, no_webp=True, no_hdvideo=True,
                )
            self.assertEqual(inspected.call_count, 1)
            self.assertEqual(prepared.call_count, 1)
            self.assertEqual(retail.read_bytes(), before)
            self.assertEqual(plan["trace_mode"], "full")
            self.assertFalse(plan["build_executed"])
            self.assertFalse(plan["game_executed"])
            self.assertFalse((upstream / "platform/pc").exists())
            self.assertFalse(Path(plan["capture_dir"]).exists())
            script_path = session / "build_capture_verify.sh"
            script = script_path.read_text(encoding="utf-8")
            self.assertEqual(plan["shell_sha256"], hashlib.sha256(script.encode()).hexdigest())
            self.assertIn("NO_WEBP=1", script)
            self.assertIn("NO_HDVIDEO=1", script)
            self.assertIn("REGION=us", script)
            self.assertIn("VH_DISC_IMAGE=" + shlex.quote(str(disc)), script)
            self.assertIn("VH_KROM_SOURCE=" + shlex.quote(str(krom)), script)
            self.assertIn("--require-complete", script)
            self.assertIn("capture_status=0", script)
            self.assertIn("|| capture_status=$?", script)
            self.assertLess(script.index("capture_status=0"),
                            script.index("--require-complete"))
            self.assertEqual(script_path.stat().st_mode & 0o077, 0)
            syntax = subprocess.run(["sh", "-n", str(script_path)],
                                    text=True, capture_output=True)
            self.assertEqual(syntax.returncode, 0, syntax.stderr)
            self.assertEqual(json.loads((session / "session_plan.json").read_text()),
                             plan)
            self.assertEqual(json.loads((session / "preflight.json").read_text()),
                             self._preflight(krom))

    def test_blockers_leave_no_preparation_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream, _, disc, krom = self._fixture(root)
            session = root / "blocked-session"
            with patch("tools.prepare_map02_session.inspect",
                       return_value={"blockers": ["retail_executable_md5_mismatch",
                                                  "disc_release_unrecognized"]}), \
                 patch("tools.prepare_map02_session.prepare") as prepared:
                with self.assertRaisesRegex(ValueError, "retail_executable_md5_mismatch"):
                    plan_session(upstream, session, disc_image=disc,
                                 krom_source=krom)
            prepared.assert_not_called()
            self.assertFalse(session.exists())

    def test_rejects_existing_and_in_checkout_session_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream, _, disc, krom = self._fixture(root)
            existing = root / "existing"
            existing.mkdir()
            with self.assertRaisesRegex(ValueError, "already exists"):
                plan_session(upstream, existing, disc_image=disc, krom_source=krom)
            with self.assertRaisesRegex(ValueError, "outside the upstream"):
                plan_session(upstream, upstream / "internal",
                             disc_image=disc, krom_source=krom)

    def test_requires_retail_executable_in_pinned_checkout_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream, retail, disc, krom = self._fixture(root)
            retail.unlink()
            with patch("tools.prepare_map02_session.inspect",
                       return_value=self._preflight(krom)), \
                 patch("tools.prepare_map02_session.prepare") as prepared:
                with self.assertRaisesRegex(ValueError, "expected original US"):
                    plan_session(upstream, root / "output", disc_image=disc,
                                 krom_source=krom)
            prepared.assert_not_called()
            self.assertFalse((root / "output").exists())

    def test_omitted_optional_dependency_switches_keep_full_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream, _, disc, krom = self._fixture(root)
            with patch("tools.prepare_map02_session.inspect",
                       return_value=self._preflight(krom)), \
                 patch("tools.prepare_map02_session.prepare", side_effect=self._prepare):
                plan = plan_session(upstream, root / "default-session",
                                    disc_image=disc, krom_source=krom)
            script = Path(plan["user_shell_script"]).read_text()
            self.assertNotIn("NO_WEBP=1", script)
            self.assertNotIn("NO_HDVIDEO=1", script)


if __name__ == "__main__":
    unittest.main()
