"""Offline synthetic tests for a pinned, private PC GPU Make override.

No copyrighted game resources and no native game executable are needed.
Real pinned PC GPU/raster source composition is separately tested by CI.
"""
import json
from pathlib import Path
import shutil
import subprocess
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
                 "\nBACKEND_SRCS := libgpu.c pc_raster.c\n"
                 "BACKEND_OBJS := $(BUILD_DIR)/libgpu.o $(BUILD_DIR)/pc_raster.o\n"
                 "default: $(GAME_O_FILES) $(BACKEND_OBJS)\n"
                 "objs: default $(DATA_OBJS)\n"
                 "link: $(DATA_OBJS)\n"
                 "\t$(CC) $(GAME_O_FILES) $(BACKEND_OBJS) $(DATA_OBJS)\n"
                 "$(BUILD_DIR)/libgpu.o: src/libgpu.c\n"
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
        # Generated C lives outside platform/pc/src, so -Isrc must
        # reproduce the original source-directory header lookup.
        # Two preprocessing recipes and two object recipes share the include profile.
        self.assertEqual(result.count("-Iinclude -Isrc"), 1)
        self.assertEqual(result.count("$(VH_MAP02_PRIVATE_INCLUDE_FLAGS)"), 2)
        self.assertIn("map02-private-gpu-preprocess:", result)
        self.assertEqual(result.count(" -E -x c -o "), 2)
        self.assertEqual(result.count("-x $(VH_MAP02_PRIVATE_INPUT_LANG) -c"), 2)
        self.assertIn("$(error MAP02 private GPU requires isolated BUILD_DIR=", result)
        self.assertIn("$(error MAP02 private GPU instrumentation supports pinned US", result)
        self.assertIn("map02-private-gpu-objects:", result)
        self.assertIn("map02-private-pc-link: link", result)
        self.assertIn("link: objs", result)
        self.assertIn("pc_raster.private.c", result)
        self.assertIn("libgpu.private.c", result)
        for flag in builder.FLAGS:
            self.assertEqual(result.count(flag), 1)

    def test_actual_make_dry_run_selects_both_private_compilers_and_rejects_baseline(self):
        if not shutil.which("make"):
            self.skipTest("GNU Make required")
        pc = self.root / "public-pc" / "platform" / "pc"
        pc.mkdir(parents=True)
        (pc / "src").mkdir()
        original = (
            "REGION ?= us\nBUILD_DIR ?= build\n"
            "BACKEND_OBJS := $(BUILD_DIR)/libgpu.o $(BUILD_DIR)/pc_raster.o\n"
            "GAME_O_FILES := $(BUILD_DIR)/mock-game.o\n"
            "DATA_OBJS := $(BUILD_DIR)/mock-data.o\n"
            "objs: $(GAME_O_FILES) $(BACKEND_OBJS) $(DATA_OBJS)\n"
            "link: $(DATA_OBJS)\n"
            "\t@echo LINK_WITH $(GAME_O_FILES) $(BACKEND_OBJS) $(DATA_OBJS)\n"
            "$(BUILD_DIR)/mock-game.o: src/mock-game.c\n"
            "\t$(CC) -c -o $@ $<\n"
            "$(BUILD_DIR)/mock-data.o: src/mock-data.c\n"
            "\t$(CC) -c -o $@ $<\n"
            "CC := cc\nM32 := -m64\nSAN :=\nPORT_WARN := -Wall\n"
            "$(BUILD_DIR)/libgpu.o: src/libgpu.c\n"
            "\t$(CC) -c -o $@ $<\n"
            "$(BUILD_DIR)/pc_raster.o: src/pc_raster.c\n"
            "\t$(CC) -c -o $@ $<\n"
        )
        (pc / "Makefile").write_text(original)
        for name in ("libgpu.c", "pc_raster.c", "mock-game.c", "mock-data.c"):
            (pc / "src" / name).write_text("int baseline_" + name.split(".")[0] + ";\n")
        self.destination.mkdir()
        for name in (builder.GENERATED_GPU, builder.GENERATED_RASTER):
            (self.destination / name).write_text("int private_probe;\n")
        (self.destination / builder.GENERATED_MAKE).write_text(
            builder.make_overlay(self.destination))
        arguments = [
            "make", "-n", "-f", "Makefile", "-f",
            str(self.destination / builder.GENERATED_MAKE),
        ]
        def invoke(region, build):
            return subprocess.run(
                arguments + ["REGION=" + region, "BUILD_DIR=" + build,
                             "map02-private-gpu-objects"],
                cwd=pc, capture_output=True, text=True, timeout=20,
                check=False)
        good = invoke("us", "build-map02-fixture")
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertIn(str(self.destination / builder.GENERATED_GPU), good.stdout)
        self.assertIn(str(self.destination / builder.GENERATED_RASTER), good.stdout)
        self.assertIn("-DVH_MAP02_GPU_CAPTURE", good.stdout)
        self.assertIn("-DVH_MAP02_DDA_SPAN_TRACE", good.stdout)
        self.assertEqual(good.stdout.count("-Iinclude -Isrc"), 2)
        self.assertNotIn(" -c -o build-map02-fixture/libgpu.o src/libgpu.c", good.stdout)
        # The new full-link entry point must first build *all* original
        # game/backend/data objects, then invoke upstream's link recipe.
        full = subprocess.run(
            arguments + ["REGION=us", "BUILD_DIR=build-map02-fixture",
                         "map02-private-pc-link"],
            cwd=pc, capture_output=True, text=True, timeout=20,
            check=False)
        self.assertEqual(full.returncode, 0, full.stderr)
        self.assertIn("src/mock-game.c", full.stdout)
        self.assertIn("src/mock-data.c", full.stdout)
        self.assertIn(str(self.destination / builder.GENERATED_GPU), full.stdout)
        self.assertIn(str(self.destination / builder.GENERATED_RASTER), full.stdout)
        self.assertIn("LINK_WITH build-map02-fixture/mock-game.o", full.stdout)
        self.assertLess(full.stdout.index(str(self.destination / builder.GENERATED_GPU)),
                        full.stdout.index("LINK_WITH"))
        self.assertLess(full.stdout.index("src/mock-data.c"),
                        full.stdout.index("LINK_WITH"))
        baseline = invoke("us", "build")
        self.assertNotEqual(baseline.returncode, 0)
        self.assertIn("requires isolated BUILD_DIR", baseline.stderr)
        wrong_region = invoke("jp", "build-map02-fixture")
        self.assertNotEqual(wrong_region.returncode, 0)
        self.assertIn("supports pinned US PC port only", wrong_region.stderr)
        for bad in (
                "build-map02-../../outside",
                "build-map02-foo/bar",
                "build-map02-evil;touchBAD",
                "build-map02-foo:bar",
                "build-map02-foo.bar",
                "build-map02-some path",
                "build-map02-"):
            with self.subTest(build=bad):
                refused = invoke("us", bad)
                self.assertNotEqual(refused.returncode, 0)
                # GNU Make may reject ':' or ';' while parsing its
                # original rules before our overlay's error guards.
                # Both are safe refusals: no compile/link is executed.
                if bad in ("build-map02-evil;touchBAD", "build-map02-foo:bar"):
                    self.assertTrue(
                        "MAP02 private GPU BUILD_DIR" in refused.stderr
                        or "missing separator" in refused.stderr
                        or "target pattern contains no '%'" in refused.stderr,
                        refused.stderr)
                else:
                    self.assertIn("MAP02 private GPU BUILD_DIR", refused.stderr)
                self.assertNotIn("private_probe", refused.stdout)

    def test_bad_or_make_special_directory_rejected(self):
        for name in ("x space", "x$(shell true)", "x:colon", "x;semi"):
            with self.subTest(name=name), self.assertRaisesRegex(
                    ValueError, "unsafe characters"):
                builder.make_overlay(self.root / name)

    def test_synthetic_generation_keeps_original_inputs_unchanged(self):
        known, fake = self.fake_sources()
        before = {path: (self.upstream / path).read_bytes() for path in fake}
        with (patch.object(builder, "_require_pinned_clean_checkout"),
              patch.object(builder, "git_blob_sha1",
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
        self.assertTrue(out["full_checkout_head_verified"])
        self.assertTrue(out["full_tracked_checkout_clean"])
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

    def test_refuses_pinned_makefile_with_wrong_full_link_graph(self):
        known, fake = self.fake_sources()
        original_make = fake[builder.MAKE_REL]
        wrong = original_make.replace(b"objs: default $(DATA_OBJS)",
                                      b"objs: default")
        (self.upstream / builder.MAKE_REL).write_bytes(wrong)
        # Treat modified bytes as a pinned blob for this negative unit:
        # proves semantic Make checks are independent from blob SHA.
        known[wrong] = builder.PINNED_BLOB_SHA1[builder.MAKE_REL]
        with (patch.object(builder, "_require_pinned_clean_checkout"),
              patch.object(builder, "git_blob_sha1",
                           side_effect=lambda raw: known[raw])):
            with self.assertRaisesRegex(ValueError, "full-link Make dependency"):
                builder.prepare(self.upstream, self.destination)
        self.assertFalse(self.destination.exists())

    def test_rejects_wrong_full_checkout_commit_without_exposing_paths(self):
        self.fake_sources()
        from types import SimpleNamespace
        result = SimpleNamespace(returncode=0, stdout="0" * 40 + "\n")
        with (patch.object(builder.shutil, "which", return_value="/usr/bin/git"),
              patch.object(builder.subprocess, "run", return_value=result)):
            with self.assertRaisesRegex(ValueError, "checkout HEAD differs") as caught:
                builder.prepare(self.upstream, self.destination)
        self.assertNotIn(str(self.upstream), str(caught.exception))
        self.assertFalse(self.destination.exists())

    def test_rejects_dirty_tracked_source_but_ignores_untracked_assets(self):
        self.fake_sources()
        from types import SimpleNamespace
        ok = SimpleNamespace(returncode=0,
                             stdout=builder.PINNED_UPSTREAM_REF + "\n")
        changed = SimpleNamespace(returncode=0,
                                  stdout=" M src/core/graphics.c\n")
        with (patch.object(builder.shutil, "which", return_value="/usr/bin/git"),
              patch.object(builder.subprocess, "run", side_effect=[ok, changed])):
            with self.assertRaisesRegex(
                    ValueError, "tracked source files modified") as caught:
                builder.prepare(self.upstream, self.destination)
        self.assertNotIn("graphics.c", str(caught.exception))
        self.assertFalse(self.destination.exists())
        with patch.object(builder.shutil, "which", return_value="/usr/bin/git"):
            with patch.object(builder.subprocess, "run",
                              side_effect=[ok, SimpleNamespace(returncode=0, stdout="")]):
                # The pinned three-file SHA remains separately mandatory,
                # even when the tracked tree is clean.
                with self.assertRaisesRegex(ValueError, "Git blob differs"):
                    builder.prepare(self.upstream, self.destination)

    def test_refuses_wrong_pinned_blob_and_does_not_publish_output(self):
        self.fake_sources()
        with patch.object(builder, "_require_pinned_clean_checkout"):
            with self.assertRaisesRegex(ValueError, "Git blob differs"):
                builder.prepare(self.upstream, self.destination)
        self.assertFalse(self.destination.exists())

    def test_refuses_generation_into_original_upstream_tree(self):
        self.fake_sources()
        with self.assertRaisesRegex(ValueError, "outside upstream"):
            builder.prepare(self.upstream, self.upstream / "generated")

    def test_symlinked_output_parent_cannot_write_into_upstream(self):
        self.fake_sources()
        alias = self.root / "disguised-private-parent"
        alias.symlink_to(self.upstream, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "outside upstream|symlink alias"):
            builder.prepare(self.upstream, alias / "private-overlay")
        self.assertFalse((self.upstream / "private-overlay").exists())


if __name__ == "__main__":
    unittest.main()
