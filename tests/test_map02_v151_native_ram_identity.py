#!/usr/bin/env python3
"""Source-authenticated native v151 synthetic MIPS payload tests."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.apply_map02_v151_native_ram_identity import (
    expected_payload_digest, header_source, original_fixture, patch_frontend,
)


class NativeSyntheticRamDigest(unittest.TestCase):
    def test_v129_payload_is_fixed_and_source_derived(self):
        payload=original_fixture()
        self.assertEqual(len(payload),8192)
        self.assertEqual(expected_payload_digest(),hashlib.sha256(payload).digest())
        self.assertEqual(len(expected_payload_digest()),32)
        src=header_source()
        self.assertIn("static int vh151_verify_payload(",src)
        self.assertIn("vh151_sha256(loaded,8192u,actual);",src)
        self.assertNotIn("EXPECTED_SYNTHETIC_DIGEST",src)
        self.assertNotIn("original_retail",src.lower())

    def test_only_v150_synthetic_native_route_is_guarded(self):
        phrase="            if(vh150_arm(0x80010000u,0x80012000u,3u)!=0){"
        prefix=("    if(vh129_vblank_mode>=0) {\n"
                "        if(vh150_bounded_instructions){\n"+phrase+"\n")
        patched=patch_frontend(prefix)
        self.assertEqual(patched.count("vh151_verify_payload("),1)
        self.assertLess(patched.index("vh151_verify_payload("),
                        patched.index("if(vh150_arm("))
        self.assertIn('SysPrintf("VH151_NATIVE_SYNTHETIC_DIGEST_REFUSED\\n");',patched)
        self.assertIn("return 55;",patched)
        self.assertIn('#include "vh151_synthetic_sha.h"',patched)
        with self.assertRaises(ValueError):
            patch_frontend(patched)
        with self.assertRaises(ValueError):
            patch_frontend("int main(void){ return 0; }\n")

    def test_compiled_native_sha_vectors_and_tampered_source_refusal(self):
        cc=os.environ.get("CC","cc")
        if shutil.which(cc) is None:
            self.skipTest("native C compiler missing")
        program=r'''
#include <stdio.h>
#include <stdlib.h>
#include "vh151_synthetic_sha.h"
int main(int argc,char **argv) {
    unsigned char bytes[8193], digest[32];
    FILE *f;
    size_t n, i;
    if(argc!=2) return 2;
    f=fopen(argv[1],"rb");
    if(!f) return 3;
    n=fread(bytes,1,sizeof(bytes),f);
    if(ferror(f) || fclose(f)!=0 || n>8192u) return 4;
    vh151_sha256(bytes,n,digest);
    for(i=0;i<32u;i++) printf("%02x",(unsigned)digest[i]);
    printf(" verified=%d\n",n==8192u?vh151_verify_payload(bytes):-1);
    return 0;
}
'''
        fixture=original_fixture()
        samples=(b"",b"a",b"abc",b"a"*55,b"a"*56,
                 b"a"*63,b"a"*64,b"a"*65,b"b"*127,
                 fixture,fixture[:4096]+bytes([fixture[4096]^1])+fixture[4097:])
        with tempfile.TemporaryDirectory(prefix="vh151-genuine-c-") as t:
            td=Path(t)
            (td/"vh151_synthetic_sha.h").write_text(header_source())
            (td/"probe.c").write_text(program)
            exe=td/"probe"
            built=subprocess.run(
                [cc,"-std=c99","-Wall","-Wextra","-Werror","-pedantic",
                 "-I",str(td),str(td/"probe.c"),"-o",str(exe)],
                capture_output=True,text=True,timeout=30)
            self.assertEqual(built.returncode,0,built.stderr)
            for i,data in enumerate(samples):
                with self.subTest(length=len(data),sample=i):
                    src=td/"sample.bin"
                    src.write_bytes(data)
                    run=subprocess.run([str(exe),str(src)],
                        capture_output=True,text=True,timeout=10)
                    self.assertEqual(run.returncode,0,run.stderr)
                    expected=hashlib.sha256(data).hexdigest()
                    actual,verified=run.stdout.strip().split(" verified=")
                    self.assertEqual(actual,expected)
                    self.assertEqual(verified,
                        ("1" if i==len(samples)-2 else "0")
                        if len(data)==8192 else "-1")

    def test_real_native_workflow_stays_synthetic_and_checks_mutation(self):
        wf=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        isolated=(ROOT/".github/workflows/map02-v151-native-ram-identity.yml").read_text()
        for needle in (
            "apply_map02_v151_native_ram_identity",
            "VH151_NATIVE_SYNTHETIC_DIGEST_REFUSED",
            "V151_TAMPERED.EXE",
            "v151-tampered-before",
            "VH150_NATIVE_BOUNDED_INTERPRETER_PASS",
        ):
            self.assertIn(needle,wf)
        self.assertIn("test_map02_v151_native_ram_identity.py",isolated)
        self.assertIn("original_retail_executed=0",isolated)


if __name__=="__main__":
    unittest.main()
