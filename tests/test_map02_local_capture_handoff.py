"""Asset-free pre-run executable/game-image and final MAP02 handoff tests.

The production final GTE/DrawOTag verifier is mocked here ONLY. Original
game assets are never included; binary and game image are synthetic bytes.
"""
import hashlib
import io
import json
import subprocess
from contextlib import redirect_stderr
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from tools.map02_local_capture_handoff import (
    HANDOFF, PLAN, _validate_plan, _validated_handoff,
    prepare_local_capture, seal_local_capture, verify_local_capture,
    SOURCE_BLOBS, verify_pinned_upstream,
)
from tools.prepare_map02_pcport import git_blob_sha1
from tools.publish_map02_window_scoped_witness import MANIFEST as FINAL


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class LocalMap02CaptureHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.handoff = root / "handoff"
        self.source = root / "source"
        self.windows = root / "windows"
        self.scoped = root / "scoped"
        for directory in (
            self.handoff, self.source, self.windows, self.scoped,
        ):
            directory.mkdir(mode=0o700)
        self.upstream = root / "synthetic-pinned-original-pc-checkout"
        fixture_blobs = {}
        for relative in SOURCE_BLOBS:
            original = b"synthetic pinned source test only " + relative.encode()
            path = self.upstream / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(original)
            fixture_blobs[relative] = git_blob_sha1(original)
        # The real Git blob pin set remains checked in a separate CI step
        # against the downloaded actual upstream checkout. This unit-only
        # fixture explicitly substitutes synthetic blob identities.
        original_patch = patch(
            "tools.map02_local_capture_handoff.SOURCE_BLOBS",
            fixture_blobs)
        original_patch.start()
        self.addCleanup(original_patch.stop)
        self.binary = root / "pc-original-test-binary"
        self.game = root / "owned-synthetic-game-image"
        self.binary.write_bytes(b"synthetic instrumented PC program, not executable")
        self.game.write_bytes(b"fake tiny game image; no retail content")
        self.game.chmod(0o600)
        self.session = "a" * 64
        self.final_bytes = (json.dumps({
            "gpu_frame": 7, "capture_session_linked": True,
            "capture_session_sha256": self.session,
            "only_synthetic_test_fixture": True,
        }, sort_keys=True) + "\n").encode()
        (self.source / FINAL).write_bytes(self.final_bytes)
        self.final_mock = patch(
            "tools.map02_local_capture_handoff.verify_published_window_scoped_witness",
            return_value={"private_witness_sha256": digest(self.final_bytes),
                          "global_draw_ordinals_checked": 2},
        )
        self.verified = self.final_mock.start()
        self.addCleanup(self.final_mock.stop)

    def prepare(self):
        return prepare_local_capture(
            self.handoff, self.binary, self.game, frame=7,
            upstream=self.upstream)

    def seal(self):
        return seal_local_capture(self.handoff, self.source, self.windows,
                                  self.scoped, self.binary, self.game,
                                  upstream=self.upstream)

    def verify(self):
        return verify_local_capture(self.handoff, self.source, self.windows,
                                    self.scoped, self.binary, self.game,
                                    upstream=self.upstream)

    def test_prelaunch_plan_and_verified_handoff_are_private_and_bound(self):
        before = self.prepare()
        self.assertFalse(before["capture_executed"])
        self.assertFalse(before["original_gameplay_authenticated"])
        plan = json.loads((self.handoff / PLAN).read_bytes())
        self.assertEqual(plan["pinned_upstream_source_identity_sha256"],
                         verify_pinned_upstream(self.upstream))
        self.assertEqual(plan["pc_executable_sha256"], digest(self.binary.read_bytes()))
        self.assertEqual(plan["owned_game_image_sha256"], digest(self.game.read_bytes()))
        self.assertEqual(stat.S_IMODE((self.handoff / PLAN).stat().st_mode), 0o600)
        after = self.seal()
        self.assertFalse(after["gameplay_origin_authenticated"])
        self.assertEqual(after["gpu_draw_frame"], 7)
        handoff = json.loads((self.handoff / HANDOFF).read_bytes())
        self.assertEqual(handoff["capture_session_sha256"], self.session)
        self.assertEqual(handoff["source_gte_gpu_witness_sha256"],
                         digest(self.final_bytes))
        self.assertEqual(stat.S_IMODE((self.handoff / HANDOFF).stat().st_mode),
                         0o600)
        self.assertEqual(self.verify()["local_capture_handoff_sha256"],
                         after["local_capture_handoff_sha256"])
        self.assertGreaterEqual(self.verified.call_count, 3)
        self.assertFalse(list(self.handoff.glob(".*.tmp")))

    def test_never_overwrite_plan_or_handoff(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.prepare()
        self.seal()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.seal()

    def test_detects_changed_local_pc_binary_before_sealing(self):
        self.prepare()
        self.binary.write_bytes(self.binary.read_bytes() + b" changed")
        with self.assertRaisesRegex(ValueError, "differs from pre-run"):
            self.seal()
        self.assertFalse((self.handoff / HANDOFF).exists())

    def test_detects_changed_game_image_before_sealing(self):
        self.prepare()
        self.game.write_bytes(self.game.read_bytes() + b" changed")
        with self.assertRaisesRegex(ValueError, "differs from pre-run"):
            self.seal()
        self.assertFalse((self.handoff / HANDOFF).exists())

    def test_reverify_rejects_mutated_binary_and_owned_input(self):
        self.prepare()
        self.seal()
        self.binary.write_bytes(self.binary.read_bytes() + b" bad")
        with self.assertRaises(ValueError):
            self.verify()
        self.binary.write_bytes(b"synthetic instrumented PC program, not executable")
        self.game.write_bytes(b"different input, not retail image")
        with self.assertRaises(ValueError):
            self.verify()

    def test_reverify_rejects_modified_final_gte_witness(self):
        self.prepare()
        self.seal()
        final = self.source / FINAL
        final.write_bytes(self.final_bytes + b"\n")
        with self.assertRaisesRegex(ValueError, "digest changed"):
            self.verify()
        self.assertTrue((self.handoff / HANDOFF).exists())

    def test_rejects_wrong_gpu_session_and_gte_verifier_failure(self):
        self.prepare()
        self.verified.return_value = {
            "private_witness_sha256": "0" * 64,
        }
        with self.assertRaisesRegex(ValueError, "digest changed"):
            self.seal()
        self.verified.side_effect = ValueError("source GTE not checked")
        with self.assertRaisesRegex(ValueError, "GTE"):
            self.seal()
        self.assertFalse((self.handoff / HANDOFF).exists())

    def test_missing_and_symlinked_or_worldreadable_game_refused(self):
        self.game.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "owner-private"):
            self.prepare()
        self.game.chmod(0o600)
        link = self.handoff.parent / "game-link"
        link.symlink_to(self.game)
        with self.assertRaisesRegex(ValueError, "linked"):
            prepare_local_capture(self.handoff, self.binary, link,
                                  frame=7, upstream=self.upstream)
        self.handoff.chmod(0o755)
        with self.assertRaises(ValueError):
            self.prepare()

    def test_rejects_modified_pinned_original_gpu_source(self):
        self.prepare()
        raster = self.upstream / "platform/pc/src/pc_raster.c"
        raster.write_bytes(raster.read_bytes() + b" injected")
        with self.assertRaisesRegex(ValueError, "differs from pinned"):
            self.seal()
        self.assertFalse((self.handoff / HANDOFF).exists())

    def test_rejects_pinned_original_gpu_source_symlink(self):
        raster = self.upstream / "platform/pc/src/pc_raster.c"
        contents = raster.read_bytes()
        raster.unlink()
        destination = self.upstream / "raster-backup.c"
        destination.write_bytes(contents)
        raster.symlink_to(destination)
        with self.assertRaisesRegex(ValueError, "source missing or linked"):
            self.prepare()

    def test_source_directories_must_not_alias_or_be_public(self):
        self.prepare()
        with self.assertRaises(ValueError):
            seal_local_capture(self.handoff, self.handoff, self.windows,
                               self.scoped, self.binary, self.game,
                               upstream=self.upstream)
        self.scoped.chmod(0o755)
        with self.assertRaises(ValueError):
            self.seal()

    def test_bad_frame_and_duplicate_keys_and_false_attestation_refused(self):
        with self.assertRaises(ValueError):
            prepare_local_capture(self.handoff, self.binary, self.game,
                                  frame=0, upstream=self.upstream)
        self.prepare()
        path = self.handoff / PLAN
        raw = path.read_bytes()
        path.write_bytes(raw.replace(b'"target_gpu_draw_frame":7',
                                     b'"target_gpu_draw_frame":7,"target_gpu_draw_frame":7'))
        with self.assertRaises(ValueError):
            self.seal()
        self.assertFalse((self.handoff / HANDOFF).exists())
        self.assertRaises(ValueError, _validated_handoff, {
            "schema": "vh.map02.local-capture-handoff.v1",
            "owned_game_binary_executed_proven": True,
        })

    def test_cli_prepare_seal_verify_redact_private_input_exception_paths(self):
        import sys
        import tools.map02_local_capture_handoff as handoff_cli

        private_path = str(self.game)
        for operation, action, failure in (
            ("prepare", "prepare_local_capture",
             OSError("cannot open original image " + private_path)),
            ("seal", "seal_local_capture",
             ValueError("private ELF path changed: " + str(self.binary))),
            ("verify", "verify_local_capture",
             subprocess.TimeoutExpired([str(self.binary)], 2)),
        ):
            with self.subTest(operation=operation):
                arguments = [
                    "map02-local-capture-handoff", operation, str(self.handoff),
                    "--pc-binary", str(self.binary),
                    "--owned-game-image", str(self.game),
                    "--upstream-checkout", str(self.upstream),
                ]
                if operation == "prepare":
                    arguments.extend(("--frame", "7"))
                else:
                    arguments.extend((
                        "--source-bundle", str(self.source),
                        "--native-windows", str(self.windows),
                        "--scoped-capture", str(self.scoped),
                    ))
                stderr = io.StringIO()
                with (patch.object(sys, "argv", arguments),
                      patch.object(handoff_cli, action, side_effect=failure),
                      redirect_stderr(stderr)):
                    with self.assertRaises(SystemExit) as thrown:
                        handoff_cli.main()
                self.assertEqual(thrown.exception.code, 2)
                self.assertIn(
                    "private MAP02 capture handoff preparation or verification failed",
                    stderr.getvalue())
                for path in (str(self.binary), str(self.game),
                             str(self.handoff), str(self.upstream)):
                    self.assertNotIn(path, stderr.getvalue())

    def test_exclusive_link_error_rolls_back(self):
        self.prepare()
        with patch("tools.map02_local_capture_handoff.os.link",
                   side_effect=OSError("local permission denied")):
            with self.assertRaises(OSError):
                self.seal()
        self.assertFalse((self.handoff / HANDOFF).exists())
        self.assertFalse(list(self.handoff.glob(".*.tmp")))


if __name__ == "__main__":
    unittest.main()
