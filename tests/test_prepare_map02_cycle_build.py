"""Asset-free Make-overlay tests; real upstream translation units compile in CI.

The source-pin tests below use deliberately tiny fake originals only to
exercise transactional generation. The GitHub Actions integration step
separately generates from the exact public, pinned original PC port and
compiles all four REAL original CD/GPU/raster units in one relocatable blob.
"""
import hashlib
import json
import subprocess
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
        self.font_generator = self.upstream / mod.FONT_GENERATOR
        self.font_generator.parent.mkdir(parents=True, exist_ok=True)
        self.font_generator.write_text("# synthetic pinned original font script\\n")
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
            patch.object(mod, "FONT_GENERATOR_BLOB_SHA1",
                         git_blob_sha1(self.font_generator.read_bytes())),
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
            "VH_MAP02_ASSET_BOUND_SOURCES :=",
            "VH_MAP02_ASSET_BOUND_OBJECTS :=",
            "VH_MAP02_PUBLIC_CODE_OBJS :=",
            "VH_MAP02_BIOS_FONT_OBJECT := $(BUILD_DIR)/pc_kanji_font.o",
            "VH_MAP02_PUBLIC_BACKEND_OBJS :=",
            "map02-public-code: $(VH_MAP02_PUBLIC_CODE_OBJS) $(VH_MAP02_PUBLIC_BACKEND_OBJS)",
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
            "map02_pinned_gen_kanji_font.py",
            "VH_GENERATED_OUT=$@ python3",
            "$(BUILD_DIR)/map02_pinned_kanji_font.c:",
            "$(BUILD_DIR)/pc_kanji_font.o: $(BUILD_DIR)/map02_pinned_kanji_font.c",
            "src/pc_kanji_font.c: $(VH_MAP02_CYCLE_ROOT)/",
        ):
            self.assertIn(symbol, overlay)
        self.assertFalse((self.upstream / "platform/pc/map02_cycle.mk").exists())
        self.assertEqual(self.source.read_text(), "void original(void) {}\n")
        report = json.loads(
            (self.output / "map02_cycle_build_inputs.json").read_text())
        self.assertFalse(report["retail_gameplay_executed"])
        self.assertFalse(report["original_map02_rendering_proven"])
        self.assertIn(mod.FONT_GENERATOR, report["original_source_sha256"])
        self.assertEqual(
            (self.output / mod.FONT_GENERATOR_SNAPSHOT).read_bytes(),
            self.font_generator.read_bytes())
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

    def test_real_make_uses_private_font_script_not_mutated_upstream(self):
        # No owned retail KROM is needed: the generated C is synthetic.
        # Actually invoke GNU Make to detect unexpected inherited recipes.
        original = (
            "import os\n"
            "from pathlib import Path\n"
            "Path(os.environ['VH_GENERATED_OUT']).write_text("
            "'const unsigned char pc_kanji_charset2[] = {1};\\n')\n"
        )
        self.font_generator.write_text(original, encoding="utf-8")
        (self.upstream / "platform/pc/tools").mkdir(parents=True, exist_ok=True)
        self.make.write_text(
            "GAME_ROOT := ../..\n"
            "BACKEND_OBJS := $(BUILD_DIR)/pc_kanji_font.o\n"
            "# GAME_C_FLAGS PORT_WARN\n"
            "link: $(DATA_OBJS)\n"
            "src/pc_kanji_font.c: tools/gen_kanji_font.py ; python3 $<\n"
            "$(BUILD_DIR)/pc_kanji_font.o: src/pc_kanji_font.c\n"
            "\t$(CC) -c $< -o $@\n", encoding="utf-8")
        with patch.object(mod, "MAKEFILE_SHA",
                          git_blob_sha1(self.make.read_bytes())), patch.object(
                mod, "FONT_GENERATOR_BLOB_SHA1",
                git_blob_sha1(self.font_generator.read_bytes())):
            mod.prepare(self.upstream, self.output)
        # Changing the original source after preparation must not affect the
        # private executed snapshot (preflight would reject this mutation).
        self.font_generator.write_text("raise SystemExit('wrong source')\n")
        target = "build-map02-cycle/pc_kanji_font.o"
        completed = subprocess.run(
            ["make", "-f", "Makefile", "-f", str(self.output / "map02_cycle.mk"),
             target, "BUILD_DIR=build-map02-cycle", "REGION=us"],
            cwd=self.upstream / "platform/pc", capture_output=True,
            text=True, timeout=30, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr[-700:])
        generated = self.upstream / "platform/pc/build-map02-cycle/map02_pinned_kanji_font.c"
        self.assertTrue(generated.is_file())
        self.assertEqual(generated.stat().st_mode & 0o777, 0o600)
        self.assertTrue((self.upstream / "platform/pc" / target).is_file())
        self.assertFalse(
            (self.upstream / "platform/pc/src/pc_kanji_font.c").exists())

    def test_original_font_script_drift_fails_before_private_bundle_exists(self):
        self.font_generator.write_text("# changed original font generator\\n")
        with self.assertRaisesRegex(ValueError, "font generator source drift"):
            mod.prepare(self.upstream, self.output)
        self.assertFalse(self.output.exists())

    def test_original_font_script_symlink_never_copied(self):
        data = self.font_generator.read_bytes()
        saved = self.font_generator.with_name("source-script.py")
        saved.write_bytes(data)
        self.font_generator.unlink()
        self.font_generator.symlink_to(saved)
        with self.assertRaisesRegex(ValueError, "font generator missing or linked"):
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
        self.assertNotIn("python3 tools/gen_kanji_font.py", text)
        self.assertIn("VH_REGION=us VH_GENERATED_OUT=$@ python3", text)


if __name__ == "__main__":
    unittest.main()
