#!/usr/bin/env python3
"""Compile the exact native challenge-binding C writer under sanitizers."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

from .apply_map02_v143_atomic_private_receipt import native_atomic_private_receipt_code
from .apply_map02_v144_private_run_challenge import native_challenge_bound_receipt_code
from .check_map02_v143_atomic_receipt import sample_c
from .verify_map02_v141_private_original_mmio_claims import (
    read_private_exact_mmio_trace,parse_exact_mmio_trace,
)

ROOT=Path(__file__).resolve().parents[1]
GOOD="1d4f78a2e3b04c569ab87d2015ef0c36"


def sample_challenge_c():
    original=sample_c()
    before=native_atomic_private_receipt_code()
    if original.count(before)!=1:
        raise ValueError("original native C writer fixture changed")
    return original.replace(before,native_challenge_bound_receipt_code())


def run(compiler):
    with tempfile.TemporaryDirectory(prefix="vh144-native-",dir=ROOT) as tmp:
        root=Path(tmp)
        source=root/"binding.c"
        exe=root/"binding"
        source.write_text(sample_challenge_c())
        result=subprocess.run(
            [compiler,"-D_GNU_SOURCE","-std=c11","-O1",
             "-Wall","-Wextra","-Wpedantic","-Werror",
             "-fsanitize=bounds,undefined",
             str(source),"-o",str(exe)],
            capture_output=True,text=True,timeout=30,check=False)
        if result.returncode:
            raise ValueError("VH144_NATIVE_CHALLENGE_BINDER_COMPILE_REFUSED")
        def invoke(mode,dirname,challenge):
            env=dict(os.environ)
            if challenge is None:
                env.pop("VH144_RECEIPT_CHALLENGE_HEX",None)
            else:
                env["VH144_RECEIPT_CHALLENGE_HEX"]=challenge
            r=subprocess.run([str(exe),mode,str(dirname)],
                             capture_output=True,text=True,check=False,
                             timeout=12,env=env)
            if r.returncode!=0 or r.stdout or r.stderr:
                raise ValueError("VH144_NATIVE_CHALLENGE_BINDER_EXECUTION_REFUSED")

        def directory(name):
            p=root/name
            p.mkdir(mode=0o700)
            p.chmod(0o700)
            return p
        name="vh142-interpreter-mmio.jsonl"
        challenge_name="vh144-run-challenge.hex"
        good=directory("good")
        invoke("accept",good,GOOD)
        receipt=good/name
        sidecar=good/challenge_name
        if (not receipt.is_file() or not sidecar.is_file()
                or receipt.stat().st_mode&0o777!=0o600
                or sidecar.stat().st_mode&0o777!=0o600
                or sidecar.read_bytes()!=GOOD.encode()+b"\n"
                or len(parse_exact_mmio_trace(
                    read_private_exact_mmio_trace(receipt)))!=19
                or (good/".vh143-private-mmio-staging.jsonl").exists()):
            raise ValueError("VH144_NATIVE_CHALLENGE_AND_RECEIPT_MISMATCH")
        before=read_private_exact_mmio_trace(receipt)
        invoke("refuse",good,GOOD)
        if read_private_exact_mmio_trace(receipt)!=before:
            raise ValueError("VH144_EXISTING_RECEIPT_OVERWRITTEN")

        # Missing / malformed challenges refuse before final publication.
        invalid=[
            None,"",GOOD.upper(),GOOD[:-1],GOOD+"0",
            "x"*32,"0"*31+"z","0"*31+" ","0"*31+"-",
        ]
        for i,bad in enumerate(invalid):
            d=directory("bad-"+str(i))
            invoke("refuse",d,bad)
            if ((d/name).exists() or (d/challenge_name).exists() or
                    (d/".vh143-private-mmio-staging.jsonl").exists()):
                raise ValueError("VH144_INVALID_CHALLENGE_PUBLISHED")

        # Existing sidecar symlink and file must not be replaced.
        blocked=directory("existing-sidecar")
        (blocked/challenge_name).symlink_to(sidecar)
        invoke("refuse",blocked,GOOD)
        if (blocked/name).exists():
            raise ValueError("VH144_SIDECAR_EXISTENCE_COLLISION_ACCEPTED")
        unsafe=directory("unsafe-parent")
        nested=unsafe/"dir"
        nested.mkdir(mode=0o700)
        unsafe.chmod(0o777)
        invoke("refuse",nested,GOOD)
        unsafe.chmod(0o700)
        alias=root/"alias"
        alias.symlink_to(good,target_is_directory=True)
        invoke("refuse",alias,GOOD)

    print("VH144_COMPILED_CHALLENGE_NATIVE_PASS "
          "events=19 challenge_bits=128 atomic_receipt=1 "
          "missing_and_malformed_refused=1 sidecar_replay_refused=1 "
          "unsafe_parent_refused=1 original_retail=0")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--cc",required=True)
    run(parser.parse_args().cc)
