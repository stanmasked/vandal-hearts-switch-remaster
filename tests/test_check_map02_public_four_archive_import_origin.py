"""Native three-ELF tests for original-PC vs SDL2 four-archive import origin."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tools.check_map02_private_incremental_link import (
    _open_owned, _unresolved, OUTPUT, probe_private_incremental_link,
)
from tools.check_map02_public_x11_after_sdl2 import _save_local_undefined_manifest
from tools.check_map02_public_four_archive_import_origin import (
    SCHEMA, partition_four_archive_origin,
)
import tools.check_map02_public_four_archive_import_origin as target


class FourArchiveImportOriginTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory(prefix="map02-four-origin-")
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.original = self.compile(
            "pc-original",
            "extern int original_for_sdl(void), original_for_four(void),"
            " original_survives(void);\n"
            "int pc_entry(void){return original_for_sdl()+"
            "original_for_four()+original_survives();}\n")
        self.original.chmod(0o600)
        sdl_member = self.compile(
            "sdl-member",
            "extern int added_by_sdl(void);\n"
            "int original_for_sdl(void) {return added_by_sdl();}\n")
        sdl_archive = self.archive("sdl-provider.a", sdl_member)
        self.orig_manifest = self.make_manifest(self.root / "original-manifest",
                                                self.original)
        sdl_output = self.root / "sdl2-linked"
        probe_private_incremental_link(
            self.orig_manifest, self.original, [sdl_archive], sdl_output,
            expected_initial_strong_imports=3)
        self.sdl_elf = sdl_output / OUTPUT
        self.sdl_manifest = self.make_manifest(self.root / "sdl2-manifest",
                                               self.sdl_elf)
        four_one = self.compile(
            "libx11-member",
            "extern int introduced_by_four(void);\n"
            "int original_for_four(void) {return introduced_by_four();}\n")
        four_two = self.compile(
            "libxcb-member",
            "int added_by_sdl(void) {return 8;}\n")
        four_three = self.compile(
            "libxau-member",
            "int unused_xau(void) {return 9;}\n")
        four_four = self.compile(
            "libxdmcp-member",
            "int unused_xdmcp(void) {return 10;}\n")
        libraries = (
            self.archive("libX11.a", four_one),
            self.archive("libxcb.a", four_two),
            self.archive("libXau.a", four_three),
            self.archive("libXdmcp.a", four_four),
        )
        four_output = self.root / "four-group"
        probe_private_incremental_link(
            self.sdl_manifest, self.sdl_elf, list(libraries), four_output,
            group_archives=True, expected_initial_strong_imports=3)
        self.four_elf = four_output / OUTPUT

    def compile(self, name, source):
        src = self.root / (name + ".c")
        src.write_text(source, encoding="utf-8")
        obj = self.root / (name + ".o")
        subprocess.run(
            ["cc", "-std=c99", "-c", str(src), "-o", str(obj)],
            check=True, capture_output=True, timeout=30)
        return obj

    def archive(self, name, *members):
        out = self.root / name
        subprocess.run(["ar", "rcs", str(out), *(str(x) for x in members)],
                       check=True, capture_output=True, timeout=30)
        out.chmod(0o600)
        return out

    @staticmethod
    def make_manifest(directory, obj):
        directory.mkdir(mode=0o700)
        entry = _open_owned(obj, require_private=True)
        try:
            s, w = _unresolved(entry)
            return _save_local_undefined_manifest(directory, entry, s, w)
        finally:
            os.close(entry[0])

    def audit(self, *, manifest=None, original=None, sdl=None, four=None,
              **kwargs):
        return partition_four_archive_origin(
            manifest or self.orig_manifest,
            original or self.original,
            self.sdl_manifest,
            sdl or self.sdl_elf,
            four or self.four_elf,
            expected_original=3,
            expected_sdl2=3,
            expected_original_after_sdl2=2,
            expected_new_sdl2=1,
            expected_four_resolved=2,
            expected_four_new=1,
            expected_four_final=2,
            **kwargs)

    def test_real_three_native_elf_import_origin_partition(self):
        report = self.audit()
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["initial_original_strong"], 3)
        self.assertEqual(report["original_strong_still_after_sdl2"], 2)
        self.assertEqual(report["sdl2_new_strong_imports"], 1)
        self.assertEqual(report["sdl2_stage_strong_total"], 3)
        self.assertEqual(report["original_pc_strong_resolved_by_four_archives"], 1)
        self.assertEqual(report["original_pc_strong_still_after_four_archives"], 1)
        self.assertEqual(report["sdl2_introduced_strong_resolved_by_four_archives"], 1)
        self.assertEqual(report["sdl2_introduced_strong_still_after_four_archives"], 0)
        self.assertEqual(report["four_archives_new_strong_imports"], 1)
        self.assertEqual(report["four_archives_final_strong_total"], 2)
        self.assertTrue(report["every_surviving_import_accounted_for"])
        self.assertFalse(report["retail_assets_linked"])
        self.assertFalse(report["fully_linked_game_executable"])
        self.assertFalse(report["authentic_map02_execution_proven"])
        for private in ("original_survives", "added_by_sdl", "introduced_by_four",
                        str(self.original), str(self.four_elf)):
            self.assertNotIn(json.dumps(private), json.dumps(report))

    def test_wrong_actual_link_counts_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "actual GNU link counts differ"):
            partition_four_archive_origin(
                self.orig_manifest, self.original, self.sdl_manifest,
                self.sdl_elf, self.four_elf, expected_original=3,
                expected_sdl2=3, expected_original_after_sdl2=2,
                expected_new_sdl2=1, expected_four_resolved=1,
                expected_four_new=1, expected_four_final=2)

    def test_original_manifest_with_forged_name_rejected(self):
        doc = json.loads(self.orig_manifest.read_text())
        doc["strong_symbols"] = ["fabricated", *doc["strong_symbols"][1:]]
        fabricated = self.root / "fabricated-original-manifest.json"
        fabricated.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.audit(manifest=fabricated)

    def test_identical_source_and_final_elf_inode_rejected(self):
        with self.assertRaisesRegex(ValueError, "native objects alias"):
            self.audit(four=self.sdl_elf)

    def test_symlinked_elf_not_followed(self):
        alias = self.root / "sdl2-alias.o"
        alias.symlink_to(self.sdl_elf)
        with self.assertRaisesRegex(ValueError, "inaccessible"):
            self.audit(sdl=alias)

    def test_late_byte_identical_four_elf_inode_replacement_rejected(self):
        real_unresolved = target._unresolved
        altered = False

        def replace_after_read(entry):
            nonlocal altered
            result = real_unresolved(entry)
            if entry[1] == self.four_elf.absolute() and not altered:
                altered = True
                clone = self.root / "same-bytes-new-inode.o"
                shutil.copyfile(self.four_elf, clone)
                clone.chmod(0o600)
                clone.replace(self.four_elf)
            return result

        with mock.patch.object(target, "_unresolved", side_effect=replace_after_read):
            with self.assertRaisesRegex(
                    ValueError, "changed during link|path replaced"):
                self.audit()


if __name__ == "__main__":
    unittest.main()
