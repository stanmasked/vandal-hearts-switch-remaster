"""Synthetic negative controls for paired same-run experimental NROs."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_switch_runtime_nro import RuntimeNroError
from verify_switch_wet_tail_nro import verify_pair

SHA = "0123456789abcdef0123456789abcdef01234567"
RUN = 39162387252
ATTEMPT = 1


def fixture(root):
    baseline, wet = root / "baseline", root / "wet"
    baseline.mkdir()
    wet.mkdir()
    old_nro = baseline / "vandal-hearts-prototype.nro"
    new_nro = wet / "vandal-hearts-wet-tail.nro"
    old_nro.write_bytes(b"legacy synthetic header" * 150)
    new_nro.write_bytes(b"wet-tail synthetic header" * 150)
    old_hash = hashlib.sha256(old_nro.read_bytes()).hexdigest()
    new_hash = hashlib.sha256(new_nro.read_bytes()).hexdigest()
    base = dict(
        schema="vh-switch-same-run-nro/v1",
        git_sha=SHA, run_id=RUN, run_attempt=ATTEMPT,
        nro_name=old_nro.name, nro_bytes=old_nro.stat().st_size,
        nro_sha256=old_hash,
    )
    experiment = dict(
        schema="vh-switch-explicit-wet-tail/v1",
        git_sha=SHA, run_id=RUN, run_attempt=ATTEMPT, mode=1,
        nro_name=new_nro.name, nro_bytes=new_nro.stat().st_size,
        nro_sha256=new_hash, baseline_sha256=old_hash,
    )
    write(baseline / "runtime-nro-manifest.json", base)
    write(wet / "runtime-wet-tail-manifest.json", experiment)
    return baseline, wet, new_nro, base, experiment


def write(path, data):
    path.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="ascii")


class WetTailPairTests(unittest.TestCase):
    def assert_rejected(self, tamper):
        with tempfile.TemporaryDirectory() as tmp:
            baseline, wet, nro, base, experiment = fixture(Path(tmp))
            tamper(baseline, wet, nro, base, experiment)
            with patch("verify_switch_audio_bundle.validate_nro_structure"):
                with self.assertRaises(RuntimeNroError):
                    verify_pair(baseline, wet, sha=SHA, run_id=RUN,
                                attempt=ATTEMPT)

    def test_valid_pair_and_independent_structure_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline, wet, nro, base, experiment = fixture(Path(tmp))
            with patch("verify_switch_audio_bundle.validate_nro_structure") as check:
                result = verify_pair(baseline, wet, sha=SHA, run_id=RUN,
                                     attempt=ATTEMPT)
            self.assertEqual(check.call_count, 2)
            self.assertEqual(result["result"], "SAME_RUN_WET_TAIL_NRO_PAIR_VERIFIED")
            self.assertEqual(result["legacy_sha256"], base["nro_sha256"])
            self.assertEqual(result["wet_tail_sha256"], experiment["nro_sha256"])
            self.assertEqual(result["hardware_status"], "HARDWARE NOT TESTED")

    def test_wrong_source_commit(self):
        self.assert_rejected(lambda b,w,n,x,m:
            self.change(w,m,git_sha="f"*40))

    def test_wrong_workflow_run(self):
        self.assert_rejected(lambda b,w,n,x,m:
            self.change(w,m,run_id=RUN+1))

    def test_wrong_run_attempt(self):
        self.assert_rejected(lambda b,w,n,x,m:
            self.change(w,m,run_attempt=ATTEMPT+1))

    def test_wrong_mode(self):
        self.assert_rejected(lambda b,w,n,x,m: self.change(w,m,mode=0))

    def test_boolean_mode_is_not_one(self):
        self.assert_rejected(lambda b,w,n,x,m: self.change(w,m,mode=True))

    def test_wrong_nro_name(self):
        self.assert_rejected(lambda b,w,n,x,m:
            self.change(w,m,nro_name="vandal-hearts-prototype.nro"))

    def test_modified_nro_bytes(self):
        self.assert_rejected(lambda b,w,n,x,m:
            n.write_bytes(n.read_bytes()+b"tampered"))

    def test_wrong_recorded_size(self):
        self.assert_rejected(lambda b,w,n,x,m:
            self.change(w,m,nro_bytes=m["nro_bytes"]+1))

    def test_wrong_recorded_hash(self):
        self.assert_rejected(lambda b,w,n,x,m:
            self.change(w,m,nro_sha256="f"*64))

    def test_wrong_baseline_hash(self):
        self.assert_rejected(lambda b,w,n,x,m:
            self.change(w,m,baseline_sha256="f"*64))

    def test_identical_variant_rejected(self):
        def modify(b,w,n,x,m):
            n.write_bytes((b/"vandal-hearts-prototype.nro").read_bytes())
            self.change(w,m,nro_bytes=n.stat().st_size,
                        nro_sha256=x["nro_sha256"])
        self.assert_rejected(modify)

    def test_extra_manifest_field(self):
        self.assert_rejected(lambda b,w,n,x,m:
            self.change(w,m,unsigned_signature="trusted"))

    def test_extra_file(self):
        self.assert_rejected(lambda b,w,n,x,m:
            (w/"unexpected").write_text("untrusted"))

    def test_symlink_binary(self):
        def modify(b,w,n,x,m):
            other=w.parent/"source"
            n.rename(other)
            n.symlink_to(other)
        self.assert_rejected(modify)

    def test_hardlink_binary(self):
        self.assert_rejected(lambda b,w,n,x,m:
            (w.parent/"alias").hardlink_to(n))

    def test_symlink_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            baseline, wet, *_ = fixture(root)
            alias=root/"shortcut"
            alias.symlink_to(wet, target_is_directory=True)
            with patch("verify_switch_audio_bundle.validate_nro_structure"):
                with self.assertRaises(RuntimeNroError):
                    verify_pair(baseline, alias, sha=SHA, run_id=RUN,
                                attempt=ATTEMPT)

    def test_invalid_baseline(self):
        def modify(b,w,n,x,m):
            (b/"vandal-hearts-prototype.nro").write_bytes(b"corrupt")
        self.assert_rejected(modify)

    def test_oversized_manifest(self):
        self.assert_rejected(lambda b,w,n,x,m:
            (w/"runtime-wet-tail-manifest.json").write_text("{"+" "*3000+"}"))

    def test_structural_validation_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline, wet, *_=fixture(Path(tmp))
            with patch("verify_switch_audio_bundle.validate_nro_structure",
                       side_effect=RuntimeNroError("bad executable")):
                with self.assertRaises(RuntimeNroError):
                    verify_pair(baseline, wet, sha=SHA, run_id=RUN,
                                attempt=ATTEMPT)

    @staticmethod
    def change(folder, record, **updates):
        record.update(updates)
        write(folder/"runtime-wet-tail-manifest.json", record)


if __name__ == "__main__":
    unittest.main()
