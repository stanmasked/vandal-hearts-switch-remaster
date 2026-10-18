#!/usr/bin/env python3
"""Compile the genuine v147 1024-event C observer with protected native writer.

Self-authored host-only MMIO events exercise repeat PCs, overflow rejection,
0-event refusal, atomic 0600 publication and input/collision failure. This
does not simulate retail gameplay; pinned PCSX CI separately executes actual
synthetic MIPS and runs the source verifier on its private receipt.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile

from .apply_map02_v144_private_run_challenge import (
    native_challenge_bound_receipt_code,
)
from .apply_map02_v147_generic_native_mmio import native_generic_capture_code
from .verify_map02_v141_private_original_mmio_claims import (
    parse_exact_mmio_trace,read_private_exact_mmio_trace,
)
from .analyze_map02_v131_private_mips_mmio import Refused

ROOT=Path(__file__).resolve().parents[1]
CHALLENGE="a1e4095b68d2c3f001b9e7d45283a6fc"


def native_test_source():
    return (
        "#include <stdint.h>\n#include <stdlib.h>\n"
        "#include <string.h>\n"
        "typedef uint32_t u32;\n"
        "typedef struct psxRegisters {u32 pc;u32 code;} psxRegisters;\n"
        +native_challenge_bound_receipt_code()
        +native_generic_capture_code()+
        r'''
int main(int argc,char **argv) {
    psxRegisters reg={0};
    unsigned i,limit;
    int ok,expect_accept;
    if(argc!=3) return 42;
    expect_accept=strcmp(argv[1],"accept")==0 ||
                  strcmp(argv[1],"repeat")==0;
    limit=strcmp(argv[1],"overflow")==0 ? 1025u :
          strcmp(argv[1],"empty")==0 ? 0u :
          strcmp(argv[1],"repeat")==0 ? 2u : 19u;
    vh142_enable(); /* Retained synthetic v142 helper must still compile. */
    reg.pc=0x80010004u;reg.code=0xac010000u;
    vh142_capture(&reg,0x1f801810u,7u);
    vh147_enable();
    for(i=0;i<limit;i++) {
        reg.pc=0x80010004u+
               (strcmp(argv[1],"repeat")==0?0u:i*4u);
        vh147_capture(&reg,0x1f801810u,7u+i);
    }
    ok=vh147_write_receipt(argv[2]);
    return expect_accept?(ok==0?0:43):(ok!=0?0:44);
}
'''.lstrip()
    )


def run(compiler):
    with tempfile.TemporaryDirectory(prefix="vh147-native-",dir=ROOT) as tmp:
        root=Path(tmp)
        c=root/"bounded.c"
        binary=root/"bounded"
        c.write_text(native_test_source())
        p=subprocess.run([compiler,"-D_GNU_SOURCE","-std=c11","-O1",
            "-Wall","-Wextra","-Werror","-Wpedantic",
            "-fsanitize=undefined,bounds",str(c),"-o",str(binary)],
            capture_output=True,text=True,timeout=35,check=False)
        if p.returncode:
            raise Refused("v147 bounded native collector compilation refused")
        def invoke(mode,folder,nonce=CHALLENGE):
            env=dict(os.environ)
            if nonce is None:
                env.pop("VH144_RECEIPT_CHALLENGE_HEX",None)
            else:
                env["VH144_RECEIPT_CHALLENGE_HEX"]=nonce
            p=subprocess.run([str(binary),mode,str(folder)],
                env=env,capture_output=True,text=True,timeout=12,
                check=False)
            if p.returncode!=0 or p.stdout or p.stderr:
                raise Refused("v147 native bounded MMIO guard test refused")
        def create_dir(name):
            path=root/name
            path.mkdir(mode=0o700)
            path.chmod(0o700)
            return path
        positive=create_dir("positive")
        invoke("accept",positive)
        receipt=positive/"vh147-original-mips-events.jsonl"
        sidecar=positive/"vh144-run-challenge.hex"
        stage=positive/".vh147-private-mips-stage.jsonl"
        if (not receipt.is_file() or stage.exists()
                or receipt.stat().st_mode&0o777!=0o600
                or sidecar.read_bytes()!=CHALLENGE.encode()+b"\n"
                or sidecar.stat().st_mode&0o777!=0o600):
            raise Refused("v147 atomic protected native result incomplete")
        events=parse_exact_mmio_trace(read_private_exact_mmio_trace(receipt))
        if len(events)!=19:
            raise Refused("v147 native event count mismatch")
        original=read_private_exact_mmio_trace(receipt)
        invoke("refuse",positive)
        if read_private_exact_mmio_trace(receipt)!=original:
            raise Refused("v147 native receipt overwritten")
        repeat=create_dir("repeated")
        invoke("repeat",repeat)
        repeated=parse_exact_mmio_trace(read_private_exact_mmio_trace(
            repeat/"vh147-original-mips-events.jsonl"))
        if len(repeated)!=2 or repeated[0][0]!=repeated[1][0]:
            raise Refused("v147 repeated MIPS source PCs incorrectly rejected")
        for mode in ("overflow","empty"):
            output=create_dir(mode)
            invoke(mode,output)
            if ((output/"vh147-original-mips-events.jsonl").exists() or
                    (output/".vh147-private-mips-stage.jsonl").exists() or
                    (output/"vh144-run-challenge.hex").exists()):
                raise Refused("v147 incomplete/overflow trace published")
        invalid=create_dir("missing-challenge")
        invoke("refuse",invalid,nonce=None)
        if (invalid/"vh147-original-mips-events.jsonl").exists():
            raise Refused("v147 missing challenge accepted")
        alias=root/"alias"
        alias.symlink_to(positive,target_is_directory=True)
        invoke("refuse",alias)
        writable=create_dir("writable")
        writable.chmod(0o777)
        invoke("refuse",writable)
        writable.chmod(0o700)
    print("VH147_COMPILED_BOUNDED_NATIVE_PASS "
          "capacity=1024 generic=1 repeated_pc=1 overflow_refused=1 "
          "atomic_mode0600=1 no_overwrite=1 original_retail=0")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--cc",required=True)
    run(parser.parse_args().cc)
