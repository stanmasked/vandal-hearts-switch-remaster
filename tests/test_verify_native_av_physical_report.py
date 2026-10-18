"""Only synthetic PNG fixtures: recheck bytes and an unsigned pixel report."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from inspect_native_av_physical_screenshots import inspect
from test_inspect_native_av_physical_screenshots import frame
from verify_native_av_physical_report import verify


class PhysicalPixelReportVerificationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        self.before = root / "before.png"
        self.after = root / "after.png"
        self.report = root / "report.json"
        frame().save(self.before)
        frame(b=1, f=1, p=True).save(self.after)
        self.write_report(inspect(self.before, self.after, bind_png_hashes=True))

    def write_report(self, data):
        self.report.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")

    def cli(self, before=None, after=None, flags=()):
        return subprocess.run(
            [sys.executable, "tests/verify_native_av_physical_report.py",
             str(self.report), str(before or self.before),
             str(after or self.after), *flags],
            capture_output=True, text=True)

    def test_matching_report_recomputed_without_hardware_claim(self):
        report = verify(self.report, self.before, self.after)
        self.assertFalse(report["physical_hardware_verified"])
        self.assertFalse(report["home_event_verified"])
        self.assertFalse(report["audible_audio_verified"])
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["verification"],
                         "recomputed_png_pixel_report_match")
        self.assertFalse(summary["physical_hardware_verified"])

    def test_recomputed_focus_gate_accepts_only_new_pixel_cycle(self):
        passed = self.cli(flags=("--require-focus-pixels",))
        self.assertEqual(passed.returncode, 0, passed.stderr)
        summary = json.loads(passed.stdout)
        self.assertEqual(summary["required_pixel_conditions_reverified"],
                         ["new_focus_cycle_pixels"])
        self.assertFalse(summary["home_event_verified"])
        denied = self.cli(flags=("--require-x-return-pixels",))
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn("new_x_return_pixels", denied.stderr)
        denied = self.cli(flags=("--require-y-return-pixels",))
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn("new_y_return_pixels", denied.stderr)

    def test_recomputed_manual_x_y_gates_reject_stale_focus(self):
        frame(b=1, f=1, p=True, x="yellow", y="yellow").save(self.before)
        frame(b=1, f=1, p=True, x="blue", y="blue").save(self.after)
        self.write_report(inspect(self.before, self.after,
                                  bind_png_hashes=True))
        passed = self.cli(flags=("--require-x-return-pixels",
                                 "--require-y-return-pixels"))
        self.assertEqual(passed.returncode, 0, passed.stderr)
        flags = json.loads(passed.stdout)["required_pixel_conditions_reverified"]
        self.assertEqual(flags, ["new_x_return_pixels", "new_y_return_pixels"])
        self.assertNotEqual(self.cli(flags=("--require-focus-pixels",)).returncode, 0)
        with self.assertRaisesRegex(ValueError,"new_focus_cycle_pixels"):
            verify(self.report, self.before, self.after,
                   require_focus_pixels=True)
        # Old blue X remains blue and cannot falsely confirm a new X.
        frame(b=1, f=1, p=True, x="blue", y="yellow").save(self.before)
        self.write_report(inspect(self.before, self.after,
                                  bind_png_hashes=True))
        self.assertNotEqual(
            self.cli(flags=("--require-x-return-pixels",)).returncode, 0)

    def test_json_integrity_gate_stays_independent_of_requested_pixels(self):
        data = json.loads(self.report.read_text(encoding="utf-8"))
        data["difference"]["new_focus_cycle_pixels"] = False
        self.write_report(data)
        self.assertNotEqual(
            self.cli(flags=("--require-focus-pixels",)).returncode, 0)
        self.assertNotEqual(self.cli().returncode, 0)

    def test_png_change_outside_status_tiles_rejected(self):
        altered = frame(b=1, f=1, p=True)
        altered.putpixel((40, 40), (123, 45, 67))
        altered.save(self.after)
        self.assertNotEqual(self.cli().returncode, 0)

    def test_swapped_pngs_rejected(self):
        self.assertNotEqual(
            self.cli(before=self.after, after=self.before).returncode, 0)

    def test_modified_observation_rejected(self):
        data = json.loads(self.report.read_text(encoding="utf-8"))
        data["after"]["indicators"]["P"] = "yellow"
        self.write_report(data)
        self.assertNotEqual(self.cli().returncode, 0)

    def test_modified_hash_or_scope_disclaimer_rejected(self):
        data = json.loads(self.report.read_text(encoding="utf-8"))
        data["source_png_sha256"]["after"] = "0" * 64
        self.write_report(data)
        self.assertNotEqual(self.cli().returncode, 0)
        data = inspect(self.before, self.after, bind_png_hashes=True)
        data["audible_audio_verified"] = True
        self.write_report(data)
        self.assertNotEqual(self.cli().returncode, 0)

    def test_duplicate_keys_and_nonfinite_json_rejected(self):
        self.report.write_text('{"format":"v2","format":"v2"}',
                               encoding="utf-8")
        result = self.cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate report JSON member", result.stderr)
        self.report.write_text('{"format":NaN}', encoding="utf-8")
        result = self.cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-finite JSON number", result.stderr)

    def test_v3_nro_report_rejects_wrong_artifact_or_missing_binding(self):
        nro=Path(self.folder.name)/"probe.nro"
        binary=bytearray(0x100)
        binary[0x10:0x14]=b"NRO0"
        binary[0x18:0x1c]=(0x100).to_bytes(4,"little")
        for header,offset in ((0x20,0x80),(0x28,0x90),(0x30,0xa0)):
            binary[header:header+4]=offset.to_bytes(4,"little")
            binary[header+4:header+8]=(0x10).to_bytes(4,"little")
        nro.write_bytes(binary)
        self.write_report(inspect(self.before,self.after,
                                  bind_png_hashes=True,nro_path=nro))
        ok=self.cli(flags=("--nro",str(nro),"--require-focus-pixels"))
        self.assertEqual(ok.returncode,0,ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["source_nro_sha256"],
                         __import__("hashlib").sha256(binary).hexdigest())
        # V3 cannot be downgraded to PNG-only verification.
        self.assertNotEqual(self.cli().returncode,0)
        binary[0xe0]=1
        nro.write_bytes(binary)
        self.assertNotEqual(self.cli(flags=("--nro",str(nro))).returncode,0)

    def test_independent_expected_nro_hash_matches_and_rejects_wrong_digest(self):
        nro=Path(self.folder.name)/"external-fingerprint-probe.nro"
        binary=bytearray(0x100)
        binary[0x10:0x14]=b"NRO0"
        binary[0x18:0x1c]=(0x100).to_bytes(4,"little")
        for header,offset in ((0x20,0x80),(0x28,0x90),(0x30,0xa0)):
            binary[header:header+4]=offset.to_bytes(4,"little")
            binary[header+4:header+8]=(0x10).to_bytes(4,"little")
        nro.write_bytes(binary)
        self.write_report(inspect(self.before,self.after,
                                  bind_png_hashes=True,nro_path=nro))
        expected=hashlib.sha256(binary).hexdigest()
        valid=self.cli(flags=("--nro",str(nro),
                              "--expected-nro-sha256",expected.upper(),
                              "--require-focus-pixels"))
        self.assertEqual(valid.returncode,0,valid.stderr)
        summary=json.loads(valid.stdout)
        self.assertTrue(summary["independent_nro_digest_matched"])
        self.assertFalse(summary["physical_hardware_verified"])
        wrong=self.cli(flags=("--nro",str(nro),
                              "--expected-nro-sha256","0"*64))
        self.assertNotEqual(wrong.returncode,0)
        self.assertIn("independent expected digest",wrong.stderr)
        with self.assertRaisesRegex(ValueError,"independent expected digest"):
            verify(self.report,self.before,self.after,nro_path=nro,
                   expected_nro_sha256="0"*64)

    def test_independent_expected_digest_requires_nro_and_valid_hex(self):
        missing=self.cli(flags=("--expected-nro-sha256","0"*64))
        self.assertNotEqual(missing.returncode,0)
        self.assertIn("requires --nro",missing.stderr)
        invalid=self.cli(flags=("--nro","missing.nro",
                                "--expected-nro-sha256","not-a-sha256"))
        self.assertNotEqual(invalid.returncode,0)
        self.assertIn("64 hexadecimal characters",invalid.stderr)
        self.assertFalse(json.loads(self.cli().stdout).get(
            "independent_nro_digest_matched",True))

    def test_v2_report_rejects_unexpected_nro_binding(self):
        nro=Path(self.folder.name)/"mismatched.nro"
        nro.write_bytes(b"no-valid-nro")
        self.assertNotEqual(self.cli(flags=("--nro",str(nro))).returncode,0)

    def test_unbound_v1_or_extra_field_rejected(self):
        data = inspect(self.before, self.after)
        self.write_report(data)
        self.assertNotEqual(self.cli().returncode, 0)
        data = inspect(self.before, self.after, bind_png_hashes=True)
        data["hardware_attested"] = True
        self.write_report(data)
        self.assertNotEqual(self.cli().returncode, 0)


if __name__ == "__main__":
    unittest.main()
