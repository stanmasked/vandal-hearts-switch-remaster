"""Real native GCC/ar/ld tests for X11/XCB/Xau/Xdmcp archive group."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.check_map02_private_incremental_link import (
    _open_owned, _unresolved, OUTPUT,
)
from tools.check_map02_public_x11_after_sdl2 import _save_local_undefined_manifest
from tools.check_map02_public_four_archive_group import (
    SCHEMA, measure_four_group,
)


class FourSystemArchiveGroupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="map02-four-archive-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.original = self.compile(
            "original-partial",
            "extern int go_x11(void); extern int not_provided(void);\n"
            "int start(void) {return go_x11()+not_provided();}\n")
        self.original.chmod(0o600)
        x11_one = self.compile(
            "x11-first",
            "extern int go_xcb(void); int go_x11(void) {return go_xcb();}\n")
        x11_last = self.compile(
            "x11-last",
            "int go_x11_final(void) {return 99;}\n")
        xcb = self.compile(
            "xcb", "extern int go_xau(void); int go_xcb(void) {return go_xau();}\n")
        xau = self.compile(
            "xau", "extern int go_xdmcp(void); int go_xau(void) {return go_xdmcp();}\n")
        xdmcp = self.compile(
            "xdmcp",
            "extern int go_x11_final(void); int go_xdmcp(void) {return go_x11_final();}\n")
        self.x11 = self.archive("libX11.a", x11_one, x11_last)
        self.xcb = self.archive("libxcb.a", xcb)
        self.xau = self.archive("libXau.a", xau)
        self.xdmcp = self.archive("libXdmcp.a", xdmcp)
        self.x11.chmod(0o600)
        self.xcb.chmod(0o600)
        manifest_dir = self.root / "manifest-private"
        manifest_dir.mkdir(mode=0o700)
        entry = _open_owned(self.original, require_private=True)
        try:
            s, w = _unresolved(entry)
            self.manifest = _save_local_undefined_manifest(
                manifest_dir, entry, s, w)
        finally:
            os.close(entry[0])

    def compile(self, label, source):
        c = self.root / (label + ".c")
        c.write_text(source, encoding="utf-8")
        o = self.root / (label + ".o")
        subprocess.run(
            ["cc", "-std=c99", "-c", str(c), "-o", str(o)],
            check=True, timeout=30, capture_output=True)
        return o

    def archive(self, name, *objects):
        dest = self.root / name
        subprocess.run(
            ["ar", "rcs", str(dest), *(str(o) for o in objects)],
            check=True, capture_output=True, timeout=30)
        return dest

    def test_native_group_follows_four_archive_cross_references(self):
        dest = self.root / "fresh-native-four-archive-group"
        result = measure_four_group(
            self.manifest, self.original, self.x11, self.xcb,
            self.xau, self.xdmcp, dest, expected_after_sdl2_strong=2)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["initial_after_sdl2_strong_undefined"], 2)
        self.assertEqual(result["original_strong_imports_resolved"], 1)
        self.assertEqual(result["original_strong_imports_remaining"], 1)
        self.assertEqual(result["new_strong_imports_from_four_archives"], 0)
        self.assertEqual(result["final_strong_undefined_after_four_archives"], 1)
        self.assertEqual(result["original_with_any_of_four_strong_providers"], 1)
        self.assertEqual(result["original_without_four_strong_providers"], 1)
        self.assertTrue(result["real_four_archive_group_ld_r_executed"])
        self.assertFalse(result["retail_assets_linked"])
        self.assertFalse(result["fully_linked_game_executable"])
        self.assertFalse(result["authentic_map02_execution_proven"])
        self.assertEqual(dest.stat().st_mode & 0o777, 0o700)
        self.assertEqual((dest / "linked").stat().st_mode & 0o777, 0o700)
        self.assertEqual((dest / "linked" / OUTPUT).stat().st_mode & 0o777, 0o600)
        self.assertEqual((dest / "xau-system-candidate.a").stat().st_mode & 0o777, 0o600)
        self.assertEqual((dest / "xdmcp-system-candidate.a").stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            result["linked_four_archive_elf_sha256"],
            hashlib.sha256((dest / "linked" / OUTPUT).read_bytes()).hexdigest())
        undefined = subprocess.run(
            ["nm", "-u", str(dest / "linked" / OUTPUT)],
            check=True, timeout=30, capture_output=True, text=True).stdout
        self.assertIn("not_provided", undefined)
        self.assertNotIn("go_xau", undefined)
        self.assertNotIn("go_xdmcp", undefined)
        self.assertNotIn("go_x11_final", undefined)
        for private in ("go_x11", "go_xcb", "go_xau",
                        "go_xdmcp", "not_provided", str(self.root)):
            self.assertNotIn(private, json.dumps(result))

    def test_wrong_baseline_rejected_before_creating_files(self):
        for expected in (1085, True, -1):
            with self.subTest(expected=expected):
                folder = self.root / ("wrong-" + str(expected))
                with self.assertRaisesRegex(ValueError, "invalid|differs"):
                    measure_four_group(
                        self.manifest, self.original, self.x11, self.xcb,
                        self.xau, self.xdmcp, folder,
                        expected_after_sdl2_strong=expected)
                self.assertFalse(folder.exists())

    def test_thin_system_archive_rejected_without_link(self):
        bad_member = self.compile(
            "thin-external-xau", "int go_xau(void) {return 3;}\n")
        thin = self.root / "thin-Xau.a"
        subprocess.run(
            ["ar", "rcsT", str(thin), str(bad_member)],
            check=True, capture_output=True, timeout=30)
        folder = self.root / "bad-thin"
        with self.assertRaisesRegex(ValueError, "not an ordinary static archive"):
            measure_four_group(
                self.manifest, self.original, self.x11, self.xcb,
                thin, self.xdmcp, folder, expected_after_sdl2_strong=2)
        self.assertFalse((folder / "linked").exists())

    def test_symlink_and_duplicate_source_archives_fail_closed(self):
        linked = self.root / "untrusted-Xdmcp.a"
        linked.symlink_to(self.xdmcp)
        with self.assertRaises((OSError, ValueError)):
            measure_four_group(
                self.manifest, self.original, self.x11, self.xcb,
                self.xau, linked, self.root / "bad-symlink",
                expected_after_sdl2_strong=2)
        self.assertFalse((self.root / "bad-symlink" / "linked").exists())
        with self.assertRaisesRegex(ValueError, "source or input identity differs"):
            measure_four_group(
                self.manifest, self.original, self.x11, self.x11,
                self.xau, self.xdmcp, self.root / "same-archive",
                expected_after_sdl2_strong=2)
        self.assertFalse((self.root / "same-archive").exists())

    def test_existing_output_never_overwritten(self):
        target = self.root / "occupied"
        target.mkdir()
        marker = target / "keep"
        marker.write_bytes(b"unchanged")
        with self.assertRaisesRegex(ValueError, "must not exist"):
            measure_four_group(
                self.manifest, self.original, self.x11, self.xcb,
                self.xau, self.xdmcp, target, expected_after_sdl2_strong=2)
        self.assertEqual(marker.read_bytes(), b"unchanged")


if __name__ == "__main__":
    unittest.main()
