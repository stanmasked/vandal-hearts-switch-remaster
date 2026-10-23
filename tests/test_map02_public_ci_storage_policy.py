"""Keep MAP02 public CI limited to code, synthetic tests and sanitized evidence."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
LINUX_EXTERNAL = ROOT / ".github/workflows/map02-bizhawk211-linux-external-tool-compile.yml"
NATIVE_PORT = ROOT / ".github/workflows/map02-linux-octoshock-native-port.yml"


class PublicCIStoragePolicyTests(unittest.TestCase):
    def test_linux_compile_workflow_does_not_publish_runtime_dll_or_game_data(self):
        text = LINUX_EXTERNAL.read_text(encoding="utf-8")
        self.assertNotIn("actions/upload-artifact", text)
        self.assertIn(
            "VH_MAP02_STORAGE_POLICY_PASS public_runtime_artifact_upload=0 original_media_upload=0",
            text,
        )
        self.assertIn(
            "VH_MAP02_LINUX_OFFICIAL_OCTOSHOCK_ABSENT_EXPECTED psx_capture_ready=0",
            text,
        )
        self.assertNotIn("vandalhearts.bk2", text.lower())
        self.assertNotIn("SCPH-7003", text)

    def test_native_port_workflow_does_not_publish_compiled_library(self):
        text = NATIVE_PORT.read_text(encoding="utf-8")
        self.assertNotIn("actions/upload-artifact", text)
        self.assertIn("No compiled library or private game asset is uploaded.", text)
        self.assertIn("private_temp_only=1 original_disc=0 bios=0 bk2=0", text)


if __name__ == "__main__":
    unittest.main()
