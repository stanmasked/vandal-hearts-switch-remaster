#!/usr/bin/env python3
"""Stage366: preserve external SDL2 install evidence without a false CI pass."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from classify_switch_portlib_install import classify  # noqa: E402

class Stage366PortlibEvidenceTests(unittest.TestCase):
    def test_original_403_is_dependency_failure_not_game_compile(self):
        log = (":: Synchronizing package databases...\n"
               "curl: (22) The requested URL returned error: 403\n"
               "error: failed to synchronize all databases "
               "(error invoking external downloader)\n")
        r = classify("switch-sdl2", log)
        self.assertEqual(r["failure_code"], "EXTERNAL_DEVKITPRO_MIRROR_HTTP_403")
        self.assertFalse(r["compile_performed"])
        self.assertFalse(r["dependency_accepted"])

    def test_neither_404_nor_compiler_failure_can_be_relabelled_http403(self):
        for sample in ("error: target not found: switch-sdl2",
                       "undefined reference to SDL_OpenAudioDevice",
                       "fatal error: SDL.h: No such file or directory"):
            with self.subTest(sample=sample):
                self.assertNotEqual(
                    classify("switch-sdl2", sample)["failure_code"],
                    "EXTERNAL_DEVKITPRO_MIRROR_HTTP_403")

    def test_ci_preserves_original_log_and_nonzero_classifier(self):
        yaml = (ROOT / ".github/workflows/switch-audio-nro.yml").read_text()
        self.assertIn('set -euo pipefail', yaml)
        self.assertIn('install_log="stage366-sdl2-install.log"', yaml)
        self.assertIn('--package switch-sdl2 --log "$install_log" \\', yaml)
        self.assertIn('| tee stage366-sdl2-diagnostic.txt', yaml)
        self.assertIn('            exit 1', yaml)
        self.assertIn('      - name: Preserve Stage366 SDL2 install evidence even when dependency fails\n'
                      '        if: always()', yaml)
        self.assertIn('name: stage366-sdl2-portlib-install-evidence', yaml)
        self.assertIn('            stage366-sdl2-install.log', yaml)
        self.assertIn('            stage366-sdl2-diagnostic.txt', yaml)
        self.assertIn('          if-no-files-found: warn', yaml)
        self.assertIn('      - name: Compile and inspect music NRO', yaml)

if __name__ == "__main__":
    unittest.main()
