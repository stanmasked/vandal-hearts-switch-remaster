#!/usr/bin/env python3
"""v145 exact private binary->challenge->source MIPS receipt binding."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"tests"))

from test_map02_v141_private_original_mmio_claims import (
    synthetic_source_claims,encode_events,
)
from tools.analyze_map02_v131_private_mips_mmio import Refused
from tools.check_map02_v145_native_build_binding import (
    _read_binary,_read_manifest,_fields,prepare,verify,MANIFEST_FILE,
    SOURCE_COMMIT,SCHEMA,REQUIRED_KEYS,
)


class ExactPinnedSyntheticPCSXBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._fixture=tempfile.TemporaryDirectory(prefix="vh145-fixture-",dir=ROOT)
        cls.fixture_root=Path(cls._fixture.name)
        cls.real_binary=cls.fixture_root/"source-compiled-elf"
        code=cls.fixture_root/"source.c"
        code.write_text("int main(void) { return 144; }\n")
        cc=os.environ.get("CC","cc")
        proc=subprocess.run(
            [cc,"-O1",str(code),"-o",str(cls.real_binary)],
            cwd=cls.fixture_root,capture_output=True,text=True,
            timeout=40,check=False)
        if proc.returncode:
            raise AssertionError("native synthetic host ELF compiler refused")
        cls.real_binary.chmod(0o700)

    @classmethod
    def tearDownClass(cls):
        cls._fixture.cleanup()

    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix="vh145-private-",dir=ROOT)
        self.root=Path(self.t.name)
        self.output=self.root/"receipt"
        self.external=self.root/"external"
        self.manifest_dir=self.root/"binding"
        for p in (self.output,self.external,self.manifest_dir):
            p.mkdir(mode=0o700)
            p.chmod(0o700)
        self.challenge=self.external/"independent-run-challenge.hex"
        self.challenge.write_bytes(b"8cf32604bb108a94f9658cd3a1e072bf\n")
        self.challenge.chmod(0o600)
        self.sidecar=self.output/"vh144-run-challenge.hex"
        self.sidecar.write_bytes(self.challenge.read_bytes())
        self.sidecar.chmod(0o600)
        self.receipt=self.output/"vh142-interpreter-mmio.jsonl"
        self.receipt.write_bytes(
            encode_events(synthetic_source_claims()[2]))
        self.receipt.chmod(0o600)
        self.executable=self.root/"pcsx-native-compiled-elf"
        shutil.copyfile(self.real_binary,self.executable)
        self.executable.chmod(0o700)

    def tearDown(self):
        self.t.cleanup()

    def _binding(self):
        self.assertTrue(prepare(self.executable,self.challenge,self.manifest_dir))
        return self.manifest_dir/MANIFEST_FILE

    def test_actual_elf_and_synthetic_source_build_prepared_and_verified(self):
        path=self._binding()
        self.assertTrue(verify(self.executable,self.challenge,
                               path,self.receipt))
        manifest,data=_read_manifest(path)
        self.assertEqual(set(manifest),REQUIRED_KEYS)
        self.assertEqual(manifest["schema"],SCHEMA)
        self.assertEqual(manifest["pinned_source_commit"],SOURCE_COMMIT)
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        self.assertIn(b"synthetic_exe_sha256",data)

    def test_changed_executable_after_prepare_is_refused(self):
        manifest=self._binding()
        with self.executable.open("ab") as f:
            f.write(b"deliberately-mutated-host-ELF")
        with self.assertRaises(Refused):
            verify(self.executable,self.challenge,manifest,self.receipt)

    def test_different_compiled_elf_cannot_substitute(self):
        manifest=self._binding()
        different=self.root/"other-elf"
        shutil.copyfile(self.real_binary,different)
        different.chmod(0o700)
        with different.open("ab") as f:
            f.write(b"wrong-build")
        with self.assertRaises(Refused):
            verify(different,self.challenge,manifest,self.receipt)

    def test_second_prepare_refuses_without_deleting_existing_manifest(self):
        manifest=self._binding()
        existing=manifest.read_bytes()
        with self.assertRaises(Refused):
            prepare(self.executable,self.challenge,self.manifest_dir)
        self.assertEqual(manifest.read_bytes(),existing)
        self.assertTrue(verify(self.executable,self.challenge,
                               manifest,self.receipt))

    def test_executable_symlinks_modes_and_non_elf_refused(self):
        symlink=self.root/"symlinked-executable"
        symlink.symlink_to(self.executable)
        with self.assertRaises(Refused):
            _read_binary(symlink)
        ancestor=self.root/"alias"
        ancestor.symlink_to(self.fixture_root,target_is_directory=True)
        with self.assertRaises(Refused):
            _read_binary(ancestor/self.real_binary.name)
        self.executable.chmod(0o766)
        with self.assertRaises(Refused):
            _read_binary(self.executable)
        self.executable.chmod(0o700)
        self.executable.write_bytes(b"\x00"*96)
        with self.assertRaises(Refused):
            _read_binary(self.executable)

    def test_private_manifest_tamper_and_duplicate_json_keys_refused(self):
        manifest=self._binding()
        data=json.loads(manifest.read_bytes())
        for changed in (
            dict(data,binary_sha256="0"*64),
            dict(data,pinned_source_commit="0"*40),
            dict(data,synthetic_exe_sha256="0"*64),
            dict(data,expected_challenge_sha256="0"*64),
            dict(data,unexpected_field="error"),
        ):
            body=(json.dumps(changed,sort_keys=True,separators=(",",":"))+"\n").encode()
            manifest.write_bytes(body)
            with self.assertRaises(Refused):
                verify(self.executable,self.challenge,manifest,self.receipt)
        duplicate=(manifest.read_bytes().rstrip(b"\n")[:-1]+b','
                   b'"schema":"vh.map02.native-synthetic-emulator-build-binding.v1"}\n')
        manifest.write_bytes(duplicate)
        with self.assertRaises(Refused):
            _read_manifest(manifest)

    def test_mismatched_challenge_and_modified_mmio_refused(self):
        manifest=self._binding()
        self.challenge.write_bytes(b"0"*32+b"\n")
        with self.assertRaises(Refused):
            verify(self.executable,self.challenge,manifest,self.receipt)
        self.challenge.write_bytes(self.sidecar.read_bytes())
        corrupt=list(synthetic_source_claims()[2])
        pc,word,addr,value=corrupt[2]
        corrupt[2]=(pc,word^1,addr,value)
        self.receipt.write_bytes(encode_events(corrupt))
        with self.assertRaises(Refused):
            verify(self.executable,self.challenge,manifest,self.receipt)

    def test_invalid_private_ownership_or_manifest_dir_refused(self):
        self.manifest_dir.chmod(0o755)
        with self.assertRaises(Refused):
            prepare(self.executable,self.challenge,self.manifest_dir)
        self.manifest_dir.chmod(0o700)
        self.challenge.chmod(0o644)
        with self.assertRaises(Refused):
            prepare(self.executable,self.challenge,self.manifest_dir)
        self.assertFalse((self.manifest_dir/MANIFEST_FILE).exists())

    def test_cli_reports_status_only_and_refuses_wrong_native_binary(self):
        cli=[sys.executable,"-m",
             "tools.check_map02_v145_native_build_binding"]
        def run(*parts):
            return subprocess.run([*cli,*map(str,parts)],
                cwd=ROOT,capture_output=True,text=True,
                timeout=25,check=False)
        prep=run("prepare",self.executable,self.challenge,self.manifest_dir)
        self.assertEqual(prep.returncode,0)
        self.assertIn("VH145_PRIVATE_EMULATOR_BUILD_PREPARED",prep.stdout)
        m=self.manifest_dir/MANIFEST_FILE
        result=run("verify",self.executable,self.challenge,m,self.receipt)
        self.assertEqual(result.returncode,0)
        self.assertIn("VH145_NATIVE_BUILD_AND_RECEIPT_BOUND_PASS",result.stdout)
        self.assertEqual(result.stderr,"")
        with self.executable.open("ab") as f:
            f.write(b"after-execution-build-change")
        denied=run("verify",self.executable,self.challenge,m,self.receipt)
        self.assertEqual(denied.returncode,2)
        self.assertEqual(denied.stdout,"")
        self.assertEqual(denied.stderr.strip(),
                         "VH145_PRIVATE_EMULATOR_BUILD_BINDING_REFUSED")
        for message in (prep.stdout,result.stdout,denied.stderr):
            for secret in (str(self.executable),str(m),
                           str(self.receipt),self.challenge.read_text().strip()):
                self.assertNotIn(secret,message)

    def test_source_only_ci_and_native_binding_job_retained(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        standalone=(ROOT/".github/workflows/map02-v145-emulator-build-binding.yml").read_text()
        for token in (
            "check_map02_v145_native_build_binding",
            "test_map02_v145_native_build_binding.py",
            "VH145_PRIVATE_EMULATOR_BUILD_PREPARED",
            "VH145_NATIVE_BUILD_AND_RECEIPT_BOUND_PASS",
            "git -C upstream-pcsx rev-parse HEAD",
            "VH144_NATIVE_RUN_CHALLENGE_BOUND_PASS",
            "VH142_CORRUPTED_NATIVE_RECEIPT_REJECTED",
            "for mode in 04 13 22 31 40; do",
            "path: proof/public/",
        ):
            self.assertIn(token,workflow)
        for token in ("check_map02_v145_native_build_binding",
                      "test_map02_v145_native_build_binding.py",
                      "no_retail_exe_in_public_tests=1"):
            self.assertIn(token,standalone)


if __name__=="__main__":
    unittest.main()
