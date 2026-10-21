"""Real native GCC/ar/ld census tests; no user retail assets or names logged."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.check_map02_private_incremental_link import (
    _open_owned, _unresolved, OUTPUT, probe_private_incremental_link,
)
from tools.check_map02_public_x11_after_sdl2 import _save_local_undefined_manifest
from tools.check_map02_public_glibc_pc_provider_census import (
    SCHEMA, audit_glibc_static_coverage,
)


class OriginalPCGLibCProviderCensusTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="map02-glibc-census-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.original = self.compile(
            "original",
            "extern int orig_libc(void), orig_libm(void), orig_both(void),"
            " orig_uncovered(void), orig_sdl(void);\n"
            "int entrypoint(void){return orig_libc()+orig_libm()+"
            "orig_both()+orig_uncovered()+orig_sdl();}\n")
        self.original.chmod(0o600)
        sdl_member = self.compile(
            "sdl-member",
            "extern int added_sdl(void);\n"
            "int orig_sdl(void) {return added_sdl();}\n")
        sdl_archive = self.archive("first-real-sdl.a", sdl_member)
        self.orig_manifest = self.make_manifest("original-manifest", self.original)
        sdl_out = self.root / "after-sdl2-link"
        probe_private_incremental_link(
            self.orig_manifest, self.original, [sdl_archive], sdl_out,
            expected_initial_strong_imports=5)
        self.sdl_elf = sdl_out / OUTPUT
        self.sdl_manifest = self.make_manifest("sdl-manifest", self.sdl_elf)
        group_member = self.compile(
            "four-group-member",
            "extern int new_four(void); int added_sdl(void){return new_four();}\n")
        dummy_member = self.compile(
            "four-group-dummy", "int unrelated_four_member(void){return 1;}\n")
        group_first = self.archive("group-x11.a", group_member)
        group_second = self.archive("group-xcb.a", dummy_member)
        four_out = self.root / "after-four-real-link"
        probe_private_incremental_link(
            self.sdl_manifest, self.sdl_elf, [group_first, group_second],
            four_out, group_archives=True, expected_initial_strong_imports=5)
        self.four_elf = four_out / OUTPUT
        libc_member = self.compile(
            "libc-provider",
            "int orig_libc(void){return 1;}\n"
            "int orig_both(void){return 2;}\n")
        libm_member = self.compile(
            "libm-provider",
            "int orig_libm(void){return 3;}\n"
            "int orig_both(void){return 4;}\n")
        self.libc = self.archive("libc-normal.a", libc_member)
        self.libm = self.archive("libm-versioned-normal.a", libm_member)

    def compile(self, name, source):
        path = self.root / (name + ".c")
        path.write_text(source, encoding="utf-8")
        output = self.root / (name + ".o")
        subprocess.run(
            ["cc", "-std=c99", "-c", str(path), "-o", str(output)],
            check=True, capture_output=True, timeout=30)
        return output

    def archive(self, name, *members):
        path = self.root / name
        subprocess.run(
            ["ar", "rcs", str(path), *(str(x) for x in members)],
            check=True, capture_output=True, timeout=30)
        path.chmod(0o600)
        return path

    def make_manifest(self, name, elf):
        folder = self.root / name
        folder.mkdir(mode=0o700)
        e = _open_owned(elf, require_private=True)
        try:
            strong, weak = _unresolved(e)
            return _save_local_undefined_manifest(folder, e, strong, weak)
        finally:
            os.close(e[0])

    def census(self, root, *, libc=None, libm=None, manifest=None, **kwargs):
        expected = dict(expected_original=5, expected_after_sdl=5,
                        expected_original_survivors=4, expected_final=5)
        expected.update(kwargs)
        return audit_glibc_static_coverage(
            manifest or self.orig_manifest, self.original,
            self.sdl_manifest, self.sdl_elf, self.four_elf,
            libc or self.libc, libm or self.libm, root, **expected)

    def test_native_export_name_census_has_disjoint_buckets(self):
        root = self.root / "glibc-census-output"
        r = self.census(root)
        self.assertEqual(r["schema"], SCHEMA)
        self.assertEqual(r["original_initial_strong_undefined"], 5)
        self.assertEqual(r["after_sdl2_strong_undefined"], 5)
        self.assertEqual(r["four_archives_final_strong_undefined"], 5)
        self.assertEqual(r["original_pc_still_strong_undefined"], 4)
        self.assertEqual(r["original_pc_with_libc_strong_export"], 2)
        self.assertEqual(r["original_pc_with_libm_strong_export"], 2)
        self.assertEqual(r["original_pc_libc_only_strong_export"], 1)
        self.assertEqual(r["original_pc_libm_only_strong_export"], 1)
        self.assertEqual(r["original_pc_both_strong_exports"], 1)
        self.assertEqual(r["original_pc_without_either_strong_export"], 1)
        self.assertTrue(r["only_export_name_presence_measured"])
        self.assertFalse(r["native_glibc_link_or_compatibility_proven"])
        self.assertFalse(r["fully_linked_game_executable"])
        self.assertFalse(r["authentic_map02_execution_proven"])
        self.assertEqual(root.stat().st_mode & 0o777, 0o700)
        for path in ("glibc-system-libc-static.a", "glibc-system-libm-static.a"):
            self.assertEqual((root / path).stat().st_mode & 0o777, 0o600)
        for private in ("orig_libc", "orig_libm", "orig_both",
                        "orig_uncovered", str(self.root)):
            self.assertNotIn(json.dumps(private), json.dumps(r))

    def test_wrong_baseline_rejected_before_files_created(self):
        folder = self.root / "wrong-count"
        with self.assertRaisesRegex(ValueError, "baseline and origin differ"):
            self.census(folder, expected_original_survivors=2)
        self.assertFalse(folder.exists())

    def test_thin_or_symlinked_glibc_archive_never_used(self):
        thin = self.root / "thin-libm.a"
        member = self.compile("thin-libm-source", "int orig_libm(void){return 3;}\n")
        subprocess.run(
            ["ar", "rcsT", str(thin), str(member)],
            check=True, capture_output=True, timeout=30)
        with self.assertRaisesRegex(ValueError, "not an ordinary static archive"):
            self.census(self.root / "thin-output", libm=thin)
        self.assertFalse((self.root / "thin-output" / "glibc-system-libm-static.a").exists())
        alias = self.root / "symlink-libm.a"
        alias.symlink_to(self.libm)
        with self.assertRaises((OSError, ValueError)):
            self.census(self.root / "symlink-output", libm=alias)
        self.assertFalse((self.root / "symlink-output" / "glibc-system-libm-static.a").exists())

    def test_existing_output_preserved(self):
        root = self.root / "occupied"
        root.mkdir()
        keep = root / "sentinel"
        keep.write_bytes(b"keep")
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.census(root)
        self.assertEqual(keep.read_bytes(), b"keep")

    def test_forged_original_import_manifest_rejected_before_output(self):
        doc = json.loads(self.orig_manifest.read_text())
        doc["strong_symbols"] = ["fabricated", *doc["strong_symbols"][1:]]
        forged = self.root / "forged-original.json"
        forged.write_text(json.dumps(doc), encoding="utf-8")
        target = self.root / "forged-target"
        with self.assertRaises(ValueError):
            self.census(target, manifest=forged)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
