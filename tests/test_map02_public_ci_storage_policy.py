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

    def test_windows_compile_workflow_does_not_publish_experimental_dll(self):
        text = (ROOT / ".github/workflows/map02-bizhawk211-external-tool-compile.yml").read_text(encoding="utf-8")
        self.assertNotIn("actions/upload-artifact", text)
        self.assertNotIn("VH_MAP02_EXPERIMENTAL_DLL_PUBLIC_SHA256", text)
        self.assertIn(
            "VH_MAP02_STORAGE_POLICY_PASS public_runtime_artifact_upload=0 original_media_upload=0",
            text,
        )

    def test_private_map02_workflows_never_publish_artifacts(self):
        workflow_dir = ROOT / ".github/workflows"
        private_workflows = sorted(workflow_dir.glob("map02-private-*.yml"))
        self.assertTrue(private_workflows, "expected private MAP02 workflows to exist")
        for path in private_workflows:
            with self.subTest(workflow=path.name):
                self.assertNotIn("actions/upload-artifact", path.read_text(encoding="utf-8"))

    def test_map02_public_artifact_uploads_are_explicitly_allowlisted(self):
        workflow_dir = ROOT / ".github/workflows"
        allowed = {
            "map02-intel-mac-offline-kit.yml",
            "map02-offline-preextract-guard.yml",
        }
        map02_workflows = sorted(workflow_dir.glob("map02-*.yml"))
        published = {
            path.name
            for path in map02_workflows
            if "actions/upload-artifact" in path.read_text(encoding="utf-8")
        }
        self.assertEqual(published, allowed)

        kit = (workflow_dir / "map02-intel-mac-offline-kit.yml").read_text(encoding="utf-8")
        self.assertIn("Public-only reproducible ZIP, no licensed assets", kit)
        self.assertIn("assert report['private_data_included'] is False", kit)
        self.assertIn("assert report['original_ps1_assets_included'] is False", kit)
        self.assertIn("assert not any(x.startswith('assets/') for x in names)", kit)
        self.assertIn("n.endswith(('.py','.h','.c'))", kit)

        verifier = (workflow_dir / "map02-offline-preextract-guard.yml").read_text(encoding="utf-8")
        self.assertIn("path: tools/verify_and_extract_map02_offline_kit.py", verifier)
        self.assertNotIn("path: runtime-evidence/", verifier)
        self.assertNotIn("path: build/", verifier)

    def test_native_port_workflow_does_not_publish_compiled_library(self):
        text = NATIVE_PORT.read_text(encoding="utf-8")
        self.assertNotIn("actions/upload-artifact", text)
        self.assertIn("No compiled library or private game asset is uploaded.", text)
        self.assertIn("private_temp_only=1 original_disc=0 bios=0 bk2=0", text)


if __name__ == "__main__":
    unittest.main()
