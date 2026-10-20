"""Source-independent negative checks for three pinned-PC Catalina C helpers."""
import unittest
from unittest.mock import patch

from tools.map02_catalina_helper_macho_audit import (
    SCHEMA, SOURCE_PROGRAMS, only_system_dependencies, verify,
)

LINKED_OK = (
    "/tmp/vh-map02-catalina/verify:\n"
    "\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1345.0.0)\n"
)
LINKED_BAD = (
    "/tmp/vh-map02-catalina/verify:\n"
    "\t@rpath/libmap02-private.dylib (compatibility version 1.0.0, current version 1.0.0)\n"
)


class CatalinaHelperMachOContractTests(unittest.TestCase):
    def test_only_system_dylibs_permitted(self):
        self.assertTrue(only_system_dependencies(LINKED_OK))
        self.assertTrue(only_system_dependencies(
            LINKED_OK + "\t/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation (compatibility version 150.0.0, current version 1.0.0)\n"
        ))

    def test_rpath_homebrew_and_relative_dependencies_refused(self):
        for bad in (
            LINKED_BAD,
            LINKED_OK + "\t/opt/homebrew/lib/libExtra.dylib (compatibility version 1.0.0, current version 1.0.0)\n",
            LINKED_OK + "\t./libExtra.dylib (compatibility version 1.0.0, current version 1.0.0)\n",
        ):
            with self.subTest(bad=bad.splitlines()[-1][:40]):
                self.assertFalse(only_system_dependencies(bad))

    def test_missing_macho_dependencies_refused(self):
        for text in ("", "/tmp/verify:\n", "not otool output\n", "libSystem\n"):
            with self.subTest(text=text):
                self.assertFalse(only_system_dependencies(text))

    def test_explicit_three_actual_source_binaries_and_schema(self):
        self.assertEqual(SCHEMA, "vh.map02.catalina.pinned-pc-helper-macho-audit.v1")
        self.assertEqual(SOURCE_PROGRAMS, ("page", "ft4", "private-timeline"))

    def test_non_mac_fails_before_pinned_file_read(self):
        with patch(
            "tools.map02_catalina_helper_macho_audit.require_intel_mac",
            side_effect=ValueError("not Intel macOS")
        ), patch(
            "tools.map02_catalina_helper_macho_audit.pinned_public_raster"
        ) as read_public:
            with self.assertRaisesRegex(ValueError, "not Intel macOS"):
                verify("/private/file/should/not/be/read")
            read_public.assert_not_called()


if __name__ == "__main__":
    unittest.main()
