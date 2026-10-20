"""Synthetic offline checks of hardware-kit integrity; no actual Switch needed."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import prepare_map02_hardware_kit as kit


class HardwareKitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / kit.NAME
        self.file.write_bytes(b"synthetic test-only NRO contents")
        self.out = self.root / "kit"
        self.original = kit.EXPECTED
        kit.EXPECTED = hashlib.sha256(self.file.read_bytes()).hexdigest()
        self.addCleanup(setattr, kit, "EXPECTED", self.original)

    def test_preparation_and_verification(self):
        m = kit.prepare(self.file, self.out)
        self.assertFalse(m["physical_switch_validated"])
        self.assertTrue(all(v == "not_tested" for v in m["test_results"].values()))
        self.assertEqual(kit.verify(self.out), m)

    def test_refuse_corrupt_input(self):
        self.file.write_bytes(b"changed")
        with self.assertRaisesRegex(kit.KitError, "unverified"):
            kit.prepare(self.file, self.out)

    def test_refuse_corrupt_packaged_artifact(self):
        kit.prepare(self.file, self.out)
        (self.out / kit.NAME).write_bytes(b"tampered")
        with self.assertRaisesRegex(kit.KitError, "NRO mismatch"):
            kit.verify(self.out)

    def test_refuse_forged_hardware_success(self):
        kit.prepare(self.file, self.out)
        path = self.out / "physical_test_manifest.json"
        data = json.loads(path.read_text())
        data["physical_switch_validated"] = True
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(kit.KitError, "falsely claims"):
            kit.verify(self.out)

    def test_refuse_forged_test_result(self):
        kit.prepare(self.file, self.out)
        path = self.out / "physical_test_manifest.json"
        data = json.loads(path.read_text())
        data["test_results"]["nro_launch"] = "pass"
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(kit.KitError, "falsely claims"):
            kit.verify(self.out)

    def test_refuse_symlink_source_and_destination(self):
        alias = self.root / "link" / kit.NAME
        alias.parent.mkdir()
        alias.symlink_to(self.file)
        with self.assertRaisesRegex(kit.KitError, "symlink"):
            kit.prepare(alias, self.out)
        destination = self.root / "linked-output"
        destination.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(kit.KitError, "symlink"):
            kit.prepare(self.file, destination)

    def test_refuse_modified_checksum_file(self):
        kit.prepare(self.file, self.out)
        (self.out / "SHA256SUMS").write_text("incorrect")
        with self.assertRaisesRegex(kit.KitError, "SHA256SUMS"):
            kit.verify(self.out)

    def test_refuse_wrong_name(self):
        wrong = self.root / "retail.nro"
        wrong.write_bytes(self.file.read_bytes())
        with self.assertRaisesRegex(kit.KitError, "filename"):
            kit.prepare(wrong, self.out)


if __name__ == "__main__":
    unittest.main()
