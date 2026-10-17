"""Same-workflow executable provenance gate, including negative cases."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_switch_runtime_nro import verify, RuntimeNroError

SHA = "0123456789abcdef0123456789abcdef01234567"
RUN = 65001
ATTEMPT = 1

def sample(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    nro = folder / "vandal-hearts-prototype.nro"
    nro.write_bytes(b"NRO fake test fixture, structure separately mocked" * 60)
    manifest = {
        "schema": "vh-switch-same-run-nro/v1",
        "git_sha": SHA,
        "run_id": RUN,
        "run_attempt": ATTEMPT,
        "nro_name": nro.name,
        "nro_bytes": nro.stat().st_size,
        "nro_sha256": hashlib.sha256(nro.read_bytes()).hexdigest(),
    }
    (folder / "runtime-nro-manifest.json").write_text(
        json.dumps(manifest) + "\n", encoding="ascii")
    return nro, manifest

class TestSameRunNro(unittest.TestCase):
    def assert_rejects(self, mutator):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "nros"
            nro, manifest = sample(folder)
            mutator(folder, nro, manifest)
            with patch("verify_switch_audio_bundle.validate_nro_structure"):
                with self.assertRaises(RuntimeNroError):
                    verify(folder, sha=SHA, run_id=RUN, attempt=ATTEMPT)

    def test_valid_same_run_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "nros"
            nro, manifest = sample(folder)
            with patch("verify_switch_audio_bundle.validate_nro_structure") as structural:
                report = verify(folder, sha=SHA, run_id=RUN, attempt=ATTEMPT)
            structural.assert_called_once_with(nro)
            self.assertEqual(report["nro_sha256"], manifest["nro_sha256"])
            self.assertEqual(report["git_sha"], SHA)
            self.assertEqual(report["run_id"], RUN)

    def test_wrong_git_sha(self):
        self.assert_rejects(lambda f,n,m: self.write(f, m, git_sha="a" * 40))

    def test_wrong_run_id(self):
        self.assert_rejects(lambda f,n,m: self.write(f, m, run_id=RUN+1))

    def test_wrong_attempt(self):
        self.assert_rejects(lambda f,n,m: self.write(f, m, run_attempt=2))

    def test_wrong_nro_hash(self):
        self.assert_rejects(lambda f,n,m: n.write_bytes(n.read_bytes()+b"alter"))

    def test_wrong_size(self):
        self.assert_rejects(lambda f,n,m: self.write(f, m, nro_bytes=1))

    def test_extra_untrusted_file(self):
        self.assert_rejects(lambda f,n,m: (f/"extra.txt").write_text("fake"))

    def test_manifest_injected_field(self):
        self.assert_rejects(lambda f,n,m: self.write(f, m, fake_signature="hi"))

    def test_symlink_nro(self):
        def replace(f, n, m):
            n.rename(f/"other")
            n.symlink_to(f/"other")
        self.assert_rejects(replace)

    def test_hardlink_nro(self):
        self.assert_rejects(lambda f,n,m: (f/"other").hardlink_to(n))

    def test_reject_bool_run_id(self):
        self.assert_rejects(lambda f,n,m: self.write(f, m, run_id=True))

    @staticmethod
    def write(folder, record, **changes):
        record.update(changes)
        (folder / "runtime-nro-manifest.json").write_text(
            json.dumps(record)+"\n", encoding="ascii")

if __name__ == "__main__":
    unittest.main()
