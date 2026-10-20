"""Synthetic private VRAM timeline ↔ pinned C SampleTexture; no retail bytes."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from test_verify_map02_vram_timeline import Map02TimelineTests
from tools.verify_map02_private_timeline_pc_vram4 import (
    SCHEMA, verify_private_timeline, make_harness,
)

PUBLIC_RASTER = os.environ.get("MAP02_PINNED_RASTER")
HEADER = Path(__file__).resolve().parent.parent / "source/map02_vram4_page.h"


class PrivatePerSubmissionPcVram4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PUBLIC_RASTER:
            raise RuntimeError(
                "MAP02_PINNED_RASTER must point to pinned public pc_raster.c"
            )

    def setUp(self):
        self.base = Map02TimelineTests(
            methodName="test_two_original_source_keys_and_independent_changed_clut"
        )
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.folder = self.base.root

    def check(self, *, portable_header=None):
        return verify_private_timeline(
            self.folder, Path(PUBLIC_RASTER),
            portable_header=portable_header,
        )

    def test_two_independent_synthetic_snapshots_match_compiled_source(self):
        report = self.check()
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["submitted_faces"], 2)
        self.assertEqual(report["compiled_pc_source_4bpp_texels_compared"], 131072)
        self.assertTrue(report["source_gte_and_snapshot_timeline_verified"])
        self.assertTrue(report["post_verification_input_stability_checked"])
        for key, value in report.items():
            if key.endswith("authenticated") or key.endswith("_emitted"):
                self.assertFalse(value)
        serialized = json.dumps(report, sort_keys=True)
        for banned in ("map02.decoded.bin", "gpu-vram-000.bin",
                       "perimeter_xy", "bgr555", "camera", str(self.folder)):
            self.assertNotIn(banned, serialized)

    def test_corrupted_portable_materializer_rejected_by_compiled_pc(self):
        original = HEADER.read_text(encoding="utf-8")
        old = "indices[i]=ix;"
        self.assertEqual(original.count(old), 1)
        mutated = original.replace(
            old, "indices[i]=(uint8_t)((ix+1u)&15u);"
        )
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.check(portable_header=mutated)

    def test_after_verify_snapshot_change_refused_even_if_unreferenced(self):
        real_validate = verify_private_timeline.__globals__["verify_timeline"]

        def mutate_after_validation(directory, *, compiler):
            result = real_validate(directory, compiler=compiler)
            file = self.folder / "gpu-vram-001.bin"
            raw = bytearray(file.read_bytes())
            raw[-1] ^= 1  # outside the original textured faces
            file.write_bytes(raw)
            return result

        with patch(
            "tools.verify_map02_private_timeline_pc_vram4.verify_timeline",
            side_effect=mutate_after_validation
        ):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.check()

    def test_source_manifest_swap_and_duplicate_source_face_rejected(self):
        self.base.events[1]["source"] = self.base.events[0]["source"].copy()
        self.base.save()
        with self.assertRaisesRegex(ValueError, "duplicate submitted source"):
            self.check()

    def test_symlinked_private_snapshot_refused(self):
        file = self.folder / "gpu-vram-001.bin"
        original = file.read_bytes()
        file.unlink()
        other = self.folder / "alternate-vram.bin"
        other.write_bytes(original)
        file.symlink_to(other)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            self.check()

    def test_pinned_public_raster_mutation_refused_without_disk_changes(self):
        public = Path(PUBLIC_RASTER).read_bytes()
        corrupted = public.replace(
            b"int index = (hw >> ((u % 4) * 4)) & 0xF;",
            b"int index = (hw >> ((u % 4) * 4)) & 0xE;",
        )
        self.assertNotEqual(public, corrupted)
        with self.assertRaisesRegex(ValueError, "not the pinned Git blob"):
            make_harness(corrupted)


if __name__ == "__main__":
    unittest.main()
