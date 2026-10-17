"""Asset-free MAP02 full-game GNU Make dry-run auditing regressions."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import tools.check_map02_cycle_make_plan as check
import tools.prepare_map02_cycle_build as maker
from tools.prepare_map02_pcport import git_blob_sha1


def valid_dry_run(root):
    build = check.BUILD + "/"
    original = [
        "src/core/cd.o", "src/core/graphics.o",
        *("src/core/extras_%02d.o" % i for i in range(88)),
        "libcd.o", "libgpu.o", "pc_raster.o", "pc_kanji_font.o", "generated_data.o",
        "pc_battle_data.o", "pc_string_table.o",
        "map02_cycle_order.o", "map02_cd_read_probe.o",
        "map02_capture_session.o", "map02_scoped_blend_sink.o",
        "map02_scoped_blend_stage.o", "map02_vram_edges.o",
    ]
    lines = [
        "cc -DVH_MAP02_CYCLE_ORDER -DVH_MAP02_CD_READ_PROBE "
        "-c " + str(root / "core_cd.c") + " -o " + build + "src/core/cd.o",
        "cc -DVH_MAP02_CYCLE_ORDER -c " +
        str(root / "libcd.c") + " -o " + build + "libcd.o",
        "cc -DVH_MAP02_GPU_CAPTURE -DVH_MAP02_POSIX_CAPTURE_WINDOWS "
        "-DVH_MAP02_SCOPED_BLEND_PROBE -DVH_MAP02_VRAM_EDGE_PROBE "
        "-DVH_MAP02_POSIX_STAGE -DVH_MAP02_CAPTURE_SESSION -c " +
        str(root / "libgpu.c") + " -o " + build + "libgpu.o",
        "cc -DVH_MAP02_SCOPED_BLEND_PROBE -c " +
        str(root / "pc_raster.c") + " -o " + build + "pc_raster.o",
        "VH_REGION=us VH_GENERATED_OUT=" + build +
        "map02_pinned_kanji_font.c python3 " +
        str(root / maker.FONT_GENERATOR_SNAPSHOT),
        "cc -m64 -c " + build + "map02_pinned_kanji_font.c -o " +
        build + "pc_kanji_font.o",
        "cc -m64 " + " ".join(build + x for x in original) +
        " -lSDL2 -lopenal -lGL -lm -lpthread -rdynamic -o " +
        build + "vandalhearts_pc",
    ]
    return "\n".join(lines) + "\n"


class CycleMakePlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-make-graph-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.output = self.root / "private-bundle"
        self.upstream = self.root / "pinned-upstream"
        file = self.upstream / "src/core/cd.c"
        file.parent.mkdir(parents=True)
        file.write_text("void Original(void) {}\n")
        self.font_generator = self.upstream / maker.FONT_GENERATOR
        self.font_generator.parent.mkdir(parents=True, exist_ok=True)
        self.font_generator.write_text("# synthetic font generator\\n")
        self.make = self.upstream / "platform/pc/Makefile"
        self.make.parent.mkdir(parents=True, exist_ok=True)
        self.make.write_text("link: $(DATA_OBJS)\nBACKEND_OBJS GAME_C_FLAGS PORT_WARN\n")
        source_map = {
            "core_cd.c": ("src/core/cd.c", git_blob_sha1(file.read_bytes()),
                          lambda txt: txt + "/* Diagnostic */\n")
        }
        self.mocks = (
            patch.object(maker, "SOURCE_MAP", source_map),
            patch.object(check, "SOURCE_MAP", source_map),
            patch.object(maker, "MAKEFILE_SHA",
                         git_blob_sha1(self.make.read_bytes())),
            patch.object(maker, "MAKE_ANCHORS", ("link: $(DATA_OBJS)",)),
            patch.object(maker, "FONT_GENERATOR_BLOB_SHA1",
                         git_blob_sha1(self.font_generator.read_bytes())),
            patch.object(check, "FONT_GENERATOR_BLOB_SHA1",
                         git_blob_sha1(self.font_generator.read_bytes())),
            patch.object(check, "PINNED_BLOB_SHA1",
                         {"platform/pc/Makefile":
                          git_blob_sha1(self.make.read_bytes())}),
        )
        for item in self.mocks:
            item.start()
            self.addCleanup(item.stop)
        maker.prepare(self.upstream, self.output)

    def test_full_game_link_graph_reports_only_dry_run(self):
        result = check.verify_dry_run(valid_dry_run(self.output), self.output)
        self.assertEqual(result["private_source_compile_rules_verified"], 4)
        self.assertGreaterEqual(result["original_and_diagnostic_required_objects"], 14)
        self.assertFalse(result["fully_linked_executable_created"])
        self.assertFalse(result["original_map02_rendering_proven"])
        self.assertTrue(result["private_pinned_font_generation_verified"])

    def test_missing_original_and_observer_objects_rejected(self):
        for name in ("src/core/graphics.o", "generated_data.o",
                     "pc_kanji_font.o", "map02_cycle_order.o", "map02_vram_edges.o"):
            with self.subTest(missing=name):
                changed = valid_dry_run(self.output).replace(
                    check.BUILD + "/" + name + " ", "")
                with self.assertRaisesRegex(ValueError, "excludes original"):
                    check.verify_dry_run(changed, self.output)

    def test_rejects_wrong_output_or_absent_private_compilation(self):
        cmd = valid_dry_run(self.output)
        with self.assertRaisesRegex(ValueError, "command missing"):
            check.verify_dry_run(
                cmd.replace("vandalhearts_pc", "wrong_binary"), self.output)
        with self.assertRaisesRegex(ValueError, "duplicated"):
            check.verify_dry_run(cmd + cmd.splitlines()[-1] + "\n", self.output)
        with self.assertRaisesRegex(ValueError, "private source"):
            check.verify_dry_run(
                cmd.replace(str(self.output / "libcd.c"), "src/libcd.c"),
                self.output)

    def test_mutable_original_krom_generator_is_rejected_in_make_plan(self):
        good = valid_dry_run(self.output)
        pinned = str(self.output / maker.FONT_GENERATOR_SNAPSHOT)
        with self.assertRaisesRegex(ValueError, "pinned KROM"):
            check.verify_dry_run(
                good.replace(pinned, "tools/gen_kanji_font.py"), self.output)
        with self.assertRaisesRegex(ValueError, "pinned KROM"):
            check.verify_dry_run(
                good.replace("map02_pinned_kanji_font.c -o ",
                             "src/pc_kanji_font.c -o "), self.output)
        with self.assertRaisesRegex(ValueError, "unpinned KROM"):
            check.verify_dry_run(
                good + "python3 tools/gen_kanji_font.py\\n", self.output)

    def test_private_font_generator_snapshot_is_checked_by_preflight(self):
        font = self.output / maker.FONT_GENERATOR_SNAPSHOT
        self.assertEqual(font.stat().st_mode & 0o777, 0o600)
        self.assertEqual(font.read_bytes(), self.font_generator.read_bytes())
        font.write_bytes(font.read_bytes() + b"# altered")
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            check.preflight(self.upstream, self.output)

    def test_missing_macro_and_hd_codec_libraries_rejected(self):
        cmd = valid_dry_run(self.output)
        with self.assertRaisesRegex(ValueError, "diagnostics flag"):
            check.verify_dry_run(
                cmd.replace("-DVH_MAP02_CAPTURE_SESSION ", ""), self.output)
        with self.assertRaisesRegex(ValueError, "HD codec"):
            check.verify_dry_run(cmd.replace("-rdynamic", "-lwebp -rdynamic"),
                                 self.output)

    def test_privacy_and_digest_checks_fail_on_changed_generated_source(self):
        path = check.preflight(self.upstream, self.output)
        self.assertEqual(path, self.output / "map02_cycle.mk")
        altered = self.output / "core_cd.c"
        altered.write_bytes(altered.read_bytes() + b"tamper")
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            check.preflight(self.upstream, self.output)

    def test_modified_manifest_and_unknown_private_file_rejected(self):
        with (self.output / "accidental-asset.bin").open("wb") as f:
            f.write(b"unlisted")
        with self.assertRaisesRegex(ValueError, "unapproved file"):
            check.preflight(self.upstream, self.output)
        (self.output / "accidental-asset.bin").unlink()
        (self.output / "core_cd.c").chmod(0o644)
        with self.assertRaisesRegex(ValueError, "owner-only"):
            check.preflight(self.upstream, self.output)

    def test_symlinked_bundle_rejected(self):
        symlink = self.root / "linked"
        symlink.symlink_to(self.output, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            check.preflight(self.upstream, symlink)


if __name__ == "__main__":
    unittest.main()
