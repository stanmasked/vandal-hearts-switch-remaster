"""Exercise actual offline per-FT4 CLI and suppress all private diagnostics.

Two fixture clocks (source 411/native 12) and entirely invented snapshots.
The test's subprocess uses exactly the intended owner-local CLI, not the
in-process verify_unified() API. No real PlayStation disc is involved.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import test_verify_map02_timeline_native_ft4_join as synthetic_fixture

ROOT = Path(__file__).resolve().parent.parent
RASTER = os.environ.get("MAP02_PINNED_RASTER")


class Map02PrivateFt4CommandLineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not RASTER:
            raise RuntimeError("public pinned PC raster is required for synthetic tests")

    def setUp(self):
        base_type = synthetic_fixture.TimelineToNativeFt4JoinTests
        self.fixture = base_type(
            "test_different_clocks_reversed_ot_order_and_per_face_clut"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.source = self.fixture.base.root
        self.native = self.fixture.native
        self.assertNotEqual(self.fixture.base.frame, self.fixture.native_frame)

    def invoke(self):
        return subprocess.run(
            [sys.executable, "-m", "tools.verify_map02_private_pc_native_ft4",
             str(self.source), str(self.native), str(Path(RASTER).resolve()),
             "--compiler", os.environ.get("CC", "clang")],
            cwd=str(ROOT), capture_output=True, text=True, timeout=120,
        )

    def assert_no_private_material(self, execution):
        combined = execution.stdout + execution.stderr
        for secret in (str(self.source), str(self.native), "gpu-vram-000.bin",
                       "gpu-native-events.jsonl", "perimeter_xy",
                       "bgr555", "camera", "31978", "0x801f"):
            self.assertNotIn(secret, combined)

    def test_cli_two_clocks_and_reversed_gpu_order(self):
        execution = self.invoke()
        self.assertEqual(execution.returncode, 0, execution.stderr[:200])
        self.assertFalse(execution.stderr)
        report = json.loads(execution.stdout)
        self.assertEqual(report["source_submissions_checked"], 2)
        self.assertEqual(report["source_native_ft4_unique_matches"], 2)
        self.assertEqual(report["compiled_pc_sampletexture_texels_checked"], 131072)
        self.assertFalse(report["retail_gameplay_authenticated"])
        self.assertFalse(report["private_game_bytes_emitted"])
        self.assert_no_private_material(execution)

    def test_cli_rejects_wrong_frame_mapping_without_leaking(self):
        claim = self.source / "gpu-face-timeline-join.json"
        value = json.loads(claim.read_text())
        value["gpu_draw_frame"] += 1
        claim.write_text(json.dumps(value))
        execution = self.invoke()
        self.assertNotEqual(execution.returncode, 0)
        self.assertEqual(execution.stdout, "")
        self.assertIn(
            "local MAP02 source/native FT4 verification unavailable",
            execution.stderr,
        )
        self.assert_no_private_material(execution)

    def test_cli_rejects_symlinked_native_vram_without_leaking(self):
        original = self.native / "gpu-0000-vram.bin"
        backing = self.native / "local-synthetic-vram.bin"
        original.rename(backing)
        original.symlink_to(backing)
        execution = self.invoke()
        self.assertNotEqual(execution.returncode, 0)
        self.assertEqual(execution.stdout, "")
        self.assertIn(
            "local MAP02 source/native FT4 verification unavailable",
            execution.stderr,
        )
        self.assert_no_private_material(execution)


if __name__ == "__main__":
    unittest.main()
