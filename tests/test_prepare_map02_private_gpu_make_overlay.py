"""Offline synthetic tests for a pinned, private PC GPU Make override.

No copyrighted game resources and no native game executable are needed.
Real pinned PC GPU/raster source composition is separately tested by CI.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import prepare_map02_private_gpu_make_overlay as builder


class PrivateGpuMakeOverlayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vh-map02-private-make-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.upstream = self.root / "public-pc-source"
        self.upstream.mkdir()
        self.destination = self.root / "private-gpu-build"

    def fake_sources(self):
        fake = {
            builder.MAKE_REL:
                ("\n".join(builder.REQUIRED_MAKE_ANCHORS) +
                 "\n$(BUILD_DIR)/libgpu.o: src/libgpu.c\n"
                 "$(BUILD_DIR)/pc_raster.o: src/pc_raster.c\n").encode(),
            builder.GPU_REL: b"gpu-fake-original",
            builder.RASTER_REL: b"raster-fake-original",
        }
        for path, contents in fake.items():
            target = self.upstream / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents)
        known = {
            fake[builder.MAKE_REL]: builder.PINNED_BLOB_SHA1[builder.MAKE_REL],
            fake[builder.GPU_REL]: builder.GPU_BLOB,
            fake[builder.RASTER_REL]: builder.RASTER_BLOB,
        }
        return known, fake

    def test_real_make_recipe_replaces_both_objects_in_isolated_build(self):
        result = builder.make_overlay(self.destination)
        self.assertIn("$(BUILD_DIR)/libgpu.o:", result)
        self.assertIn("$(BUILD_DIR)/pc_raster.o:", result)
        self.assertIn("$(M32) $(SAN) $(PORT_WARN)", result)
        self.assertIn("$(error MAP02 private GPU requires isolated BUILD_DIR=", result)
        self.assertIn("$(error MAP02 private GPU instrumentation supports pinned US", result)
        self.assertIn("map02-private-gpu-objects:", result)
        self.assertIn("pc_raster.private.c", result)
        self.assertIn("libgpu.private.c", result)
        for flag in builder.FLAGS:
            self.assertEqual(result.count(flag), 1)

    def test_bad_or_make_special_directory_rejected(self):
        for name in ("x space", "x$(shell true)", "x:colon", "x;semi"):
            with self.subTest(name=name), self.assertRaisesRegex(
                    ValueError, "unsafe characters"):
                builder.make_overlay(self.root / name)

    def test_synthetic_generation_keeps_original_inputs_unchanged(self):
        known, fake = self.fake_sources()
        before = {path: (self.upstream / path).read_bytes() for path in fake}
        with (patch.object(builder, "git_blob_sha1",
                           side_effect=lambda b: known[b]),
              patch.object(builder, "multi_gpu", side_effect=lambda s: "GPU["+s+"]"),
              patch.object(builder, "multi_raster", side_effect=lambda s: "M["+s+"]"),
              patch.object(builder, "instrument_raster_skips",
                           side_effect=lambda s: "S["+s+"]"),
              patch.object(builder, "instrument_vertical",
                           side_effect=lambda s: "V["+s+"]"),
              patch.object(builder, "instrument_span",
                           side_effect=lambda s: "D["+s+"]")):
            out = builder.prepare(self.upstream, self.destination)
        self.assertTrue(out["source_pinned"])
        self.assertTrue(out["native_gpu_two_word_and_dda_in_same_make_objects"])
        self.assertFalse(out["game_assets_included"])
        self.assertFalse(out["retail_map02_gameplay_captured"])
        self.assertFalse(out["hd_replacement_authorized"])
        self.assertEqual(out["output_files"], sorted(
            [builder.GENERATED_GPU, builder.GENERATED_RASTER,
             builder.GENERATED_MAKE]))
        self.assertEqual((self.destination / builder.GENERATED_GPU).read_text(),
                         "GPU[gpu-fake-original]")
        self.assertEqual((self.destination / builder.GENERATED_RASTER).read_text(),
                         "D[V[S[M[raster-fake-original]]]]")
        self.assertEqual({path: (self.upstream / path).read_bytes()
                          for path in fake}, before)
        with self.assertRaisesRegex(ValueError, "already exists"):
            builder.prepare(self.upstream, self.destination)

    def test_refuses_wrong_pinned_blob_and_does_not_publish_output(self):
        self.fake_sources()
        with self.assertRaisesRegex(ValueError, "Git blob differs"):
            builder.prepare(self.upstream, self.destination)
        self.assertFalse(self.destination.exists())

    def test_refuses_generation_into_original_upstream_tree(self):
        self.fake_sources()
        with self.assertRaisesRegex(ValueError, "outside upstream"):
            builder.prepare(self.upstream, self.upstream / "generated")


if __name__ == "__main__":
    unittest.main()
