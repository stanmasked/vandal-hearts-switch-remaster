"""Adversarial actual-CLI trials on synthetic MAP02 native FT4 receipts.

Unlike in-process unit tests, each trial launches the genuine private command
and ensures a corrupt GPU/source witness returns no raw data or local paths.
All input files and GPU bytes are invented for these tests, never retail.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from test_verify_map02_timeline_native_ft4_join import TimelineToNativeFt4JoinTests

ROOT = Path(__file__).resolve().parent.parent
RASTER = os.environ.get("MAP02_PINNED_RASTER")


class Map02PrivateFt4MutationCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not RASTER:
            raise RuntimeError("pinned PUBLIC PC raster required for synthetic tests")

    def setUp(self):
        self.fixture = TimelineToNativeFt4JoinTests(
            "test_different_clocks_reversed_ot_order_and_per_face_clut"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.source = self.fixture.base.root
        self.native = self.fixture.native

    def cli(self, *, raster=None):
        return subprocess.run(
            [
                sys.executable, "-m", "tools.verify_map02_private_pc_native_ft4",
                str(self.source), str(self.native),
                str(raster if raster is not None else Path(RASTER).resolve()),
                "--compiler", os.environ.get("CC", "clang"),
            ],
            cwd=str(ROOT), capture_output=True, text=True, timeout=120,
        )

    def rejected_without_leak(self, result):
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn(
            "local MAP02 source/native FT4 verification unavailable",
            result.stderr,
        )
        combined = result.stdout + result.stderr
        for forbidden in (
            str(self.source), str(self.native), str(Path(RASTER).resolve()),
            "gpu-native-events.jsonl", "gpu-vram-000.bin",
            "gpu-face-timeline-join.json", "map02.decoded.bin",
            "perimeter_xy", "bgr555", "camera", "31978", "801f",
            "\\"source\\":", "\\"texture\\":",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)

    def test_all_five_ft4_packet_register_or_geometry_mutations(self):
        before = copy.deepcopy(self.fixture.packets[0])
        for kind in ("xy", "uv", "tpage", "clut", "window"):
            with self.subTest(kind=kind):
                mutated = copy.deepcopy(before)
                if kind in ("xy", "uv", "window"):
                    mutated[kind][0] ^= 1
                else:
                    mutated[kind] ^= 1
                self.fixture.packets[0] = mutated
                self.fixture.save()  # recompute native log digest, do not use trivial SHA failure
                self.rejected_without_leak(self.cli())
        self.fixture.packets[0] = before

    def test_duplicate_native_packet_refuses_ambiguous_source_match(self):
        self.fixture.packets.append(copy.deepcopy(self.fixture.packets[0]))
        self.fixture.native_vrams.append(self.fixture.native_vrams[0])
        self.fixture.save()  # recompute hashes: ambiguity rather than stale SHA
        self.rejected_without_leak(self.cli())

    def test_native_snapshot_missing_refused(self):
        (self.native / "gpu-0000-vram.bin").unlink()
        self.rejected_without_leak(self.cli())

    def test_source_snapshot_mutated_even_outside_textured_region(self):
        path = self.source / "gpu-vram-000.bin"
        raw = bytearray(path.read_bytes())
        raw[-1] ^= 1
        path.write_bytes(raw)
        self.rejected_without_leak(self.cli())

    def test_native_vram_modified_at_real_clut_word(self):
        raw = bytearray(self.fixture.native_vrams[0])
        # Self-consistently regenerate all four native snapshots and log.
        # But material at source face 1's CLUT differs from its source VRAM.
        offset = (499 * 1024 + 690) * 2
        raw[offset] ^= 0x1f
        self.fixture.native_vrams = [bytes(raw), bytes(raw)]
        self.fixture.save()
        self.rejected_without_leak(self.cli())

    def test_native_event_relative_escape_path_is_refused(self):
        self.fixture.native_events[0]["snapshot"] = "../outside-vram.bin"
        self.fixture.write_native()  # maps native event log SHA to new stream
        self.rejected_without_leak(self.cli())

    def test_wrong_private_directory_permissions_refused(self):
        original = self.native.stat().st_mode & 0o777
        self.native.chmod(0o755)
        try:
            self.rejected_without_leak(self.cli())
        finally:
            self.native.chmod(original)


if __name__ == "__main__":
    unittest.main()
