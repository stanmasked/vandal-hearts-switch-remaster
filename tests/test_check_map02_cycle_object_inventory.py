"""Synthetic fixtures for an asset-free original-PC all-object audit.

Only the real CI invokes `make default` against pinned original public C.
These isolated tests create fake ELF-header files to test fail-closed
inventory logic, NOT to emulate the original game or claim a full link.
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from tools.check_map02_cycle_object_inventory import (
    audit_objects, BUILD, REQUIRED,
)


class OriginalCodeObjectInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vh-map02-objects-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.upstream = root / "upstream"
        self.pc = self.upstream / "platform/pc"
        self.pc.mkdir(parents=True)
        (self.pc / "Makefile").write_text(
            "src/pc_kanji_font.c: tools/gen_kanji_font.py\\n")
        self.bundle = root / "bundle"
        self.bundle.mkdir(mode=0o700)
        self.game = ["src/core/cd.o"] + [
            f"src/game_{i:02d}.o" for i in range(79)
        ]
        observer = sorted(REQUIRED - {"src/core/cd.o"})
        self.backend = observer + [
            f"native_{i:02d}.o" for i in range(30 - len(observer))
        ]
        self.objroot = self.pc / BUILD
        self.objroot.mkdir()
        for relative in self.game + self.backend:
            path = self.objroot / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\x7fELF" + b"fake-ELF" * 40)
        self.source_root = self.upstream / "src"
        (self.source_root / "core").mkdir(parents=True)
        (self.source_root / "core/cd.c").write_text("/* fake only */")
        (self.source_root / "core/text.c").write_text(
            '#include "assets/801012e4.inc"\\n')
        (self.source_root / "maps").mkdir(parents=True)
        (self.source_root / "maps/map_32.c").write_text(
            '#include "assets/801009bc.inc"\n')
        (self.source_root / "maps/map_35.c").write_text(
            '#include "assets/80100e9c.inc"\n')
        for i in range(79):
            (self.source_root / f"game_{i:02d}.c").write_text("/* fake */")
        self.preflight = patch(
            "tools.check_map02_cycle_object_inventory.preflight",
            return_value=self.bundle / "map02_cycle.mk")
        self.preflight.start()
        self.addCleanup(self.preflight.stop)
        self.stdout = (
            " ".join(BUILD + "/" + x for x in self.game) + "\n"
            + " ".join(BUILD + "/" + x for x in self.backend) + "\n"
        )

    def verify(self, stdout=None):
        with patch(
                "tools.check_map02_cycle_object_inventory.subprocess.run",
                return_value=SimpleNamespace(
                    returncode=0, stdout=self.stdout if stdout is None else stdout,
                    stderr="")):
            return audit_objects(self.upstream, self.bundle)

    def test_all_original_game_and_backend_objects_checked(self):
        data = self.verify()
        self.assertEqual(data["original_game_translation_units_compiled"], 80)
        self.assertEqual(data["native_backend_and_observer_objects_compiled"], 30)
        self.assertFalse(data["full_game_elf_linked"])
        self.assertFalse(data["actual_gameplay_executed"])
        self.assertFalse(data["original_map02_rendering_proven"])

    def test_missing_object_and_invalid_elf_header_fail_closed(self):
        target = self.objroot / "libgpu.o"
        target.unlink()
        with self.assertRaisesRegex(ValueError, "missing or linked"):
            self.verify()
        target.write_bytes(b"invalid-ELF" * 40)
        with self.assertRaisesRegex(ValueError, "not an ELF"):
            self.verify()

    def test_unlisted_backend_or_duplicate_object_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicated"):
            self.verify(self.stdout.replace(
                BUILD + "/libgpu.o", BUILD + "/libcd.o", 1))
        extra = self.objroot / "unlisted.o"
        extra.write_bytes(b"\x7fELF" + b"x" * 280)
        with self.assertRaisesRegex(ValueError, "unlisted or missing"):
            self.verify()

    def test_incomplete_source_inventory_and_overclaimed_full_link_rejected(self):
        (self.source_root / "game_02.c").unlink()
        with self.assertRaisesRegex(ValueError, "sources were not all"):
            self.verify()
        (self.source_root / "game_02.c").write_text("/* fake */")
        (self.objroot / "generated_data.o").write_bytes(b"\x7fELF" + b"x" * 300)
        with self.assertRaisesRegex(ValueError, "unlisted or missing"):
            self.verify()

    def test_non_public_font_dependency_change_fails_closed(self):
        (self.source_root / "core/text.c").write_text("/* changed */")
        with self.assertRaisesRegex(ValueError, "known original retail asset dependency changed"):
            self.verify()

    def test_missing_private_bios_generator_or_fabricated_font_rejected(self):
        (self.pc / "Makefile").write_text("src/pc_kanji_font.c: rogue.py\\n")
        with self.assertRaisesRegex(ValueError, "KROMDAT BIOS font generator dependency changed"):
            self.verify()
        (self.pc / "Makefile").write_text(
            "src/pc_kanji_font.c: tools/gen_kanji_font.py\\n")
        forged = self.objroot / "pc_kanji_font.o"
        forged.write_bytes(b"\\x7fELF" + b"x" * 300)
        with self.assertRaisesRegex(ValueError, "private KROMDAT-derived backend"):
            self.verify()

    def test_path_escape_and_bad_inventory_shape_rejected(self):
        with self.assertRaisesRegex(ValueError, "two lists"):
            self.verify("only one line\n")
        modified = self.stdout.replace(
            BUILD + "/libgpu.o", BUILD + "/../bad.o")
        with self.assertRaisesRegex(ValueError, "invalid original PC object path"):
            self.verify(modified)


if __name__ == "__main__":
    unittest.main()
