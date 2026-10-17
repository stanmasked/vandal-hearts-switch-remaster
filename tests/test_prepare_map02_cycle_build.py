"""Asset-free Make-overlay tests; real upstream translation units compile in CI.

The source-pin tests below use deliberately tiny fake originals only to
exercise transactional generation. The GitHub Actions integration step
separately generates from the exact public, pinned original PC port and
compiles all three REAL original translation units in one relocatable blob.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.prepare_map02_pcport import git_blob_sha1
import tools.prepare_map02_cycle_build as mod


class SingleElfBuildOverlayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="vh-cycle-build-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.upstream = self.root / "pinned-upstream"
        (self.upstream / "platform/pc").mkdir(parents=True)
        (self.upstream / "src/core").mkdir(parents=True)
        self.make = self.upstream / "platform/pc/Makefile"
        self.make.write_text(
            "BACKEND_OBJS GAME_C_FLAGS PORT_WARN\n"
            "link: $(DATA_OBJS)\n")
        source = self.upstream / "src/core/cd.c"
        source.write_text("void original(void) {}\n")
        self.source = source
        self.output = self.root / "build-overlay"
        source_bytes = source.read_bytes()
        self.source_map = {
            "core_cd.c": ("src/core/cd.c",
                           git_blob_sha1(source_bytes),
                           lambda s: s + "/* cycle observer hook */\n"),
        }
        self.patches = [
            patch.object(mod, "SOURCE_MAP", self.source_map),
            patch.object(mod, "MAKEFILE_SHA", git_blob_sha1(self.make.read_bytes())),
            patch.object(mod, "MAKE_ANCHORS", ("link: $(DATA_OBJS)",)),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_private_overlay_contains_pinned_build_and_all_link_objects(self):
        result = mod.prepare(self.upstream, self.output)
        self.assertEqual(result, self.output / "map02_cycle.mk")
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
        overlay = result.read_text()
        for symbol in (
            "BACKEND_OBJS += $(VH_MAP02_CYCLE_SUPPORT)",
            "link: $(VH_MAP02_CYCLE_SUPPORT)",
            "$(BUILD_DIR)/src/core/cd.o:",
            "$(BUILD_DIR)/libcd.o:",
            "$(BUILD_DIR)/libgpu.o:",
            "$(BUILD_DIR)/pc_raster.o:",
            "VH_MAP02_GPU_DEFS :=",
            "-DVH_MAP02_GPU_CAPTURE",
            "-DVH_MAP02_POSIX_CAPTURE_WINDOWS",
            "-DVH_MAP02_SCOPED_BLEND_PROBE",
            "-DVH_MAP02_VRAM_EDGE_PROBE",
            "-DVH_MAP02_CAPTURE_SESSION",
            "-DVH_MAP02_POSIX_STAGE",
            "map02_scoped_blend_sink.o",
            "map02_scoped_blend_stage.o",
            "map02_vram_edges.o",
            "-DVH_MAP02_CD_READ_PROBE",
            "-DVH_MAP02_CYCLE_ORDER",
            "-Iinclude -Isrc -g",
            "VH_MAP02_CYCLE_ROOT :=",
            "map02_cycle_order.o",
            "map02_cd_read_probe.o",
            "map02_capture_session.o",
        ):
            self.assertIn(symbol, overlay)
        self.assertFalse((self.upstream / "platform/pc/map02_cycle.mk").exists())
        self.assertEqual(self.source.read_text(), "void original(void) {}\n")
        report = json.loads(
            (self.output / "map02_cycle_build_inputs.json").read_text())
        self.assertFalse(report["retail_gameplay_executed"])
        self.assertFalse(report["original_map02_rendering_proven"])
        for name, digest in report["generated_files_sha256"].items():
            file = self.output / name
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(),
                             digest)
        with self.assertRaisesRegex(ValueError, "NEW directory"):
            mod.prepare(self.upstream, self.output)

    def test_source_or_makefile_drift_rejected_without_output(self):
        self.source.write_text("void altered(void) {}\n")
        with self.assertRaisesRegex(ValueError, "original pinned source changed"):
            mod.prepare(self.upstream, self.output)
        self.assertFalse(self.output.exists())
        self.source.write_text("void original(void) {}\n")
        self.make.write_text("link: rogue\n")
        with self.assertRaisesRegex(ValueError, "Makefile differs"):
            mod.prepare(self.upstream, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_output_inside_upstream_and_symlink(self):
        with self.assertRaisesRegex(ValueError, "outside original"):
            mod.prepare(self.upstream, self.upstream / "generated")
        link = self.root / "symlink"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "not a symlink"):
            mod.prepare(self.upstream, link)
        self.assertFalse(self.output.exists())

    def test_refuses_make_special_characters_in_path(self):
        with self.assertRaisesRegex(ValueError, "unsafe characters"):
            mod.prepare(self.upstream, self.root / "build with spaces")

    def test_immutable_compilation_flags_are_per_object(self):
        text = mod._render_makefile(self.output)
        self.assertIn("ifeq ($(BUILD_DIR),build)", text)
        self.assertIn("ifneq ($(REGION),us)", text)
        self.assertIn("ifeq ($(UNIFIED),1)", text)
        self.assertNotIn("GAME_C_FLAGS +=", text)
        self.assertNotIn("PORT_WARN +=", text)
        self.assertNotIn("HD_MAP02", text)
        self.assertIn("-DVH_MAP02_GPU_CAPTURE", text)
        self.assertIn("-DVH_MAP02_SCOPED_BLEND_PROBE", text)
        self.assertIn("$(BUILD_DIR)/pc_raster.o:", text)
        self.assertIn("$(BUILD_DIR)/map02_scoped_blend_stage.o:", text)
        self.assertIn("$(BUILD_DIR)/map02_vram_edges.o:", text)
        self.assertIn("$(VH_MAP02_STAGE_DEFS)", text)


if __name__ == "__main__":
    unittest.main()
