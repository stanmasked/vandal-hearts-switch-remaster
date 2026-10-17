#!/usr/bin/env python3
"""Stage 238: optional portlib 403 is an infrastructure blocker, not CI PASS."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import classify_switch_portlib_install as check  # noqa: E402


class OptionalSwitchPortlibTests(unittest.TestCase):
    def test_real_403_default_pacman_install(self):
        actual = ("error: failed retrieving file 'dkp-libs.db' from "
                  "pkg.devkitpro.org : The requested URL returned error: 403\n"
                  "error: failed to synchronize all databases\n")
        report = check.classify("switch-openal-soft", actual)
        self.assertEqual(report["failure_code"], "EXTERNAL_DEVKITPRO_MIRROR_HTTP_403")
        self.assertFalse(report["dependency_accepted"])
        self.assertFalse(report["compile_performed"])
        self.assertEqual(report["hardware_status"], "HARDWARE NOT TESTED")

    def test_real_403_curl_xfer_command_install(self):
        actual = (":: Synchronizing package databases...\n"
                  "curl: (22) The requested URL returned error: 403\n"
                  "error: failed to synchronize all databases "
                  "(error invoking external downloader)\n")
        report = check.classify("switch-sdl2", actual)
        self.assertEqual(report["failure_code"], "EXTERNAL_DEVKITPRO_MIRROR_HTTP_403")

    def test_403_forbidden_with_response_label(self):
        self.assertEqual(check.classify("switch-sdl2", "HTTP/2 403 Forbidden")
                         ["failure_code"], "EXTERNAL_DEVKITPRO_MIRROR_HTTP_403")

    def test_network_failure_not_disguised_as_403(self):
        self.assertEqual(check.classify(
            "switch-sdl2", "temporary failure in name resolution"
        )["failure_code"], "EXTERNAL_DEVKITPRO_PACKAGE_NETWORK_FAILURE")

    def test_missing_package_is_distinct_from_mirror(self):
        self.assertEqual(check.classify(
            "switch-sdl2", "error: target not found: switch-sdl2"
        )["failure_code"], "OPTIONAL_DEVKITPRO_PACKAGE_NOT_FOUND")

    def test_compiler_error_is_not_called_mirror_failure(self):
        result = check.classify("switch-sdl2", "error: undefined reference to foo")
        self.assertEqual(result["failure_code"],
                         "UNCLASSIFIED_OPTIONAL_PACKAGE_INSTALL_FAILURE")

    def test_unknown_package_rejected(self):
        for value in ("switch-pc-port", "../foo", "", "switch-sdl2; true"):
            with self.subTest(value=value), self.assertRaises(check.PortlibInstallError):
                check.classify(value, "curl: (22) 403")

    def test_cli_always_nonzero_and_reports_explanation(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "failed-install.log"
            log.write_text("curl: (22) The requested URL returned error: 403\n")
            call = subprocess.run([
                sys.executable, str(ROOT / "tools" /
                                    "classify_switch_portlib_install.py"),
                "--package", "switch-sdl2", "--log", str(log)],
                text=True, capture_output=True, check=False)
            self.assertEqual(call.returncode, 2)
            self.assertIn('"result": "OPTIONAL_DEPENDENCY_NOT_INSTALLED"', call.stdout)
            self.assertIn('"failure_code": "EXTERNAL_DEVKITPRO_MIRROR_HTTP_403"',
                          call.stdout)
            self.assertIn("::error title=", call.stdout)

    def test_cli_missing_log_fails_closed(self):
        call = subprocess.run([
            sys.executable, str(ROOT / "tools" /
                                "classify_switch_portlib_install.py"),
            "--package", "switch-openal-soft", "--log", "/no/such/log"
        ], text=True, capture_output=True, check=False)
        self.assertEqual(call.returncode, 2)
        self.assertEqual(json.loads(call.stdout)["result"], "INVALID_INSTALL_LOG")


if __name__ == "__main__":
    unittest.main()
