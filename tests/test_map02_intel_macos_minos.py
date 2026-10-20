"""Mach-O minimum macOS contract (not an original Catalina runtime test)."""
import unittest
from tools.map02_intel_mac_offline_selfcheck import (
    macho_minos_is_target, require_macos_deployment_target,
)

BUILD = """
Mach header
Load command 0
          cmd LC_SEGMENT_64
     cmdsize 72
Load command 1
          cmd LC_BUILD_VERSION
      cmdsize 32
     platform 1
        minos 10.15
          sdk 15.5
       ntools 1
Load command 2
          cmd LC_LOAD_DYLIB
      cmdsize 56
"""


class CatalinaMinimumBuildContractTests(unittest.TestCase):
    def test_compiled_build_version_10_15_accepted(self):
        self.assertTrue(macho_minos_is_target(BUILD, "10.15"))

    def test_older_load_command_10_15_accepted(self):
        older = """
Load command 1
          cmd LC_VERSION_MIN_MACOSX
      cmdsize 16
      version 10.15
          sdk 10.15
"""
        self.assertTrue(macho_minos_is_target(older, "10.15"))

    def test_minimum_11_0_cannot_masquerade_as_10_15(self):
        self.assertFalse(
            macho_minos_is_target(BUILD.replace("minos 10.15", "minos 11.0"), "10.15")
        )

    def test_unrelated_text_and_sdk_version_not_accepted(self):
        fake = """
Load command 1
          cmd LC_LOAD_DYLIB
     platform 1
        minos 10.15
Load command 2
          cmd LC_BUILD_VERSION
        minos 11.0
          sdk 10.15
"""
        self.assertFalse(macho_minos_is_target(fake, "10.15"))

    def test_deployment_policy_only_allows_10_15(self):
        self.assertIsNone(require_macos_deployment_target(None))
        self.assertEqual(require_macos_deployment_target("10.15"), "10.15")
        for rejected in ("10.14", "11.0", "", "10.15.7", "latest"):
            with self.subTest(rejected=rejected):
                with self.assertRaisesRegex(ValueError, "unsupported"):
                    require_macos_deployment_target(rejected)


if __name__ == "__main__":
    unittest.main()
