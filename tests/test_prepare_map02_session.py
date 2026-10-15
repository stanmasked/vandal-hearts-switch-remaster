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
from tools.prepare_map02_pcport import PINNED_BLOB_SHA1, PINNED_UPSTREAM_REF
from tools.verify_map02_session import verify_session


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
        identity = "1" * 64
        renderer_marker = "VH_MAP02_TRACE_BUILD_ID:" + identity
        loader_marker = "VH_MAP02_TRACE_LOADER_ID:" + identity
        sources = {
            relative: {"git_blob_sha1": blob, "matches_pinned": True,
                       "sha256": "0" * 64}
            for relative, blob in PINNED_BLOB_SHA1.items()
        }
        payloads = {
            "game_setup.trace.c": '/* fixture */\nconst char *loader = "' + loader_marker + '";\n',
            "graphics.trace.c": '/* fixture */\nconst char *renderer = "' + renderer_marker + '";\n',
            "map02_trace.mk": "VH_MAP02_TRACE_DIR := " + str(directory) + "\n",
        }
        for name, payload in payloads.items():
            (directory / name).write_text(payload, encoding="utf-8")
        provenance = {
            "upstream_reference": PINNED_UPSTREAM_REF,
            "trace_mode": "full",
            "allow_modified_source": False,
            "source_files": sources,
            "generated_files": {
                name: hashlib.sha256(content.encode("utf-8")).hexdigest()
                for name, content in payloads.items()
            },
            "binary_marker": renderer_marker,
            "binary_loader_marker": loader_marker,
        }
        (directory / "source_provenance.json").write_text(
            json.dumps(provenance) + "\n", encoding="utf-8")
        return directory / "map02_trace.mk"

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
            self.assertEqual(plan["preflight_sha256"],
                             hashlib.sha256((session / "preflight.json").read_bytes()).hexdigest())
            self.assertEqual(plan["provenance_sha256"],
                             hashlib.sha256((session / "trace/source_provenance.json").read_bytes()).hexdigest())
            self.assertEqual(verify_session(session)["integrity"], "verified")
            self.assertIn("tools.verify_map02_session", script)
            self.assertLess(script.index("tools.verify_map02_session"),
                            script.index("tools.preflight_map02_pcport"))
            self.assertIn("NO_WEBP=1", script)
            self.assertIn("NO_HDVIDEO=1", script)
            self.assertIn("REGION=us", script)
            self.assertIn("VH_DISC_IMAGE=" + shlex.quote(str(disc)), script)
            self.assertIn("VH_KROM_SOURCE=" + shlex.quote(str(krom)), script)
            self.assertIn("--require-complete", script)
            self.assertIn("tools.report_map02_bridge", script)
            self.assertIn("bridge_review.md", script)
            self.assertIn("bridge_review.json", script)
            self.assertLess(script.index("tools.verify_map02_capture"),
                            script.index("tools.report_map02_bridge"))
            self.assertLess(script.index("tools.report_map02_bridge"),
                            script.index('if [ "$capture_status" -ne 0 ]'))
            self.assertIn("preflight_at_build.json", script)
            self.assertIn("tools.preflight_map02_pcport", script)
            self.assertIn("--disc-image " + shlex.quote(str(disc)), script)
            self.assertIn("--krom-source " + shlex.quote(str(krom)), script)
            self.assertLess(script.index("tools.preflight_map02_pcport"),
                            script.index("VH_KROM_SOURCE="))
            self.assertLess(script.index("tools.preflight_map02_pcport"),
                            script.index("make -f Makefile"))
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

    def test_tampered_session_script_and_provenance_are_rejected(self):
        for relative, error in (
            ("build_capture_verify.sh", "SHA-256 mismatch"),
            ("preflight.json", "SHA-256 mismatch"),
            ("trace/source_provenance.json", "SHA-256 mismatch"),
            ("trace/game_setup.trace.c", "SHA-256 mismatch"),
            ("trace/graphics.trace.c", "SHA-256 mismatch"),
            ("trace/map02_trace.mk", "SHA-256 mismatch"),
        ):
            with self.subTest(file=relative), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                upstream, _, disc, krom = self._fixture(root)
                session = root / "session"
                with patch("tools.prepare_map02_session.inspect",
                           return_value=self._preflight(krom)), \
                     patch("tools.prepare_map02_session.prepare",
                           side_effect=self._prepare):
                    plan_session(upstream, session, disc_image=disc, krom_source=krom)
                path = session / relative
                path.write_bytes(path.read_bytes() + b"\n/* edited */\n")
                with self.assertRaisesRegex(ValueError, error):
                    verify_session(session)

    def test_rejects_relocated_or_previously_used_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream, _, disc, krom = self._fixture(root)
            session = root / "session"
            with patch("tools.prepare_map02_session.inspect",
                       return_value=self._preflight(krom)), \
                 patch("tools.prepare_map02_session.prepare",
                       side_effect=self._prepare):
                plan_session(upstream, session, disc_image=disc, krom_source=krom)
            plan_path = session / "session_plan.json"
            plan = json.loads(plan_path.read_text())
            original = dict(plan)
            plan["binary"] = "/tmp/not-the-matching-game"
            plan_path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, "game binary"):
                verify_session(session)
            plan_path.write_text(json.dumps(original))
            (session / "capture").mkdir()
            with self.assertRaisesRegex(ValueError, "capture directory already exists"):
                verify_session(session)

    def test_valid_hashes_cannot_hide_source_or_marker_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream, _, disc, krom = self._fixture(root)
            session = root / "session"
            with patch("tools.prepare_map02_session.inspect",
                       return_value=self._preflight(krom)), \
                 patch("tools.prepare_map02_session.prepare",
                       side_effect=self._prepare):
                plan_session(upstream, session, disc_image=disc, krom_source=krom)

            prov_path = session / "trace/source_provenance.json"
            plan_path = session / "session_plan.json"
            def update_provenance(**changes):
                provenance = json.loads(prov_path.read_text())
                provenance.update(changes)
                prov_path.write_text(json.dumps(provenance))
                plan = json.loads(plan_path.read_text())
                plan["provenance_sha256"] = hashlib.sha256(prov_path.read_bytes()).hexdigest()
                plan_path.write_text(json.dumps(plan))

            update_provenance(allow_modified_source=True)
            with self.assertRaisesRegex(ValueError, "unmodified pinned full trace"):
                verify_session(session)
            update_provenance(allow_modified_source=False,
                              binary_loader_marker="VH_MAP02_TRACE_LOADER_ID:" + "2" * 64)
            with self.assertRaisesRegex(ValueError, "build identities do not match"):
                verify_session(session)

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
            preflight_line = next(line for line in script.splitlines()
                                  if "tools.preflight_map02_pcport" in line)
            self.assertNotIn("--no-webp", preflight_line)
            self.assertNotIn("--no-hdvideo", preflight_line)


if __name__ == "__main__":
    unittest.main()
