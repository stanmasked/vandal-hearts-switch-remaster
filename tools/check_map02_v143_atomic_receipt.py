#!/usr/bin/env python3
"""Compile and test the REAL patched native private receipt C writer.

Checks atomic publication, O_EXCL collision behavior, symlink ancestors,
untrusted permissions and noncanonical paths. Standalone C tests do not
claim that retail or source-authored MIPS actually executed: the separate
pinned PCSX ReARMed workflow supplies the latter evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

from .apply_map02_v143_atomic_private_receipt import (
    native_atomic_private_receipt_code,
)
from .verify_map02_v141_private_original_mmio_claims import (
    read_private_exact_mmio_trace,parse_exact_mmio_trace,
)

ROOT=Path(__file__).resolve().parents[1]


def sample_c():
    return (
        "#include <stdint.h>\n"
        "#include <string.h>\n"
        "typedef uint32_t u32;\n"
        "typedef struct psxRegisters {u32 pc;u32 code;} psxRegisters;\n"
        +native_atomic_private_receipt_code()+r"""
int main(int argc,char **argv) {
    unsigned i;
    psxRegisters r={0};
    int result;
    if(argc!=3) return 40;
    vh142_enable();
    for(i=0;i<VH142_EXPECTED_EVENTS;i++) {
        r.pc=0x80010004u+4u*i;
        r.code=0xac010000u; /* self-authored synthetic SW */
        vh142_capture(&r,0x1f801810u,0x02000000u+i);
    }
    result=vh142_write_receipt(argv[2],0u);
    if(strcmp(argv[1],"accept")==0) return result==0?0:42;
    if(strcmp(argv[1],"refuse")==0) return result!=0?0:43;
    return 44;
}
""")


def run(compiler):
    with tempfile.TemporaryDirectory(prefix="vh143-test-",dir=ROOT) as tmp:
        root=Path(tmp)
        c=root/"receipt.c"
        executable=root/"receipt"
        c.write_text(sample_c())
        build=subprocess.run([
            compiler,"-D_GNU_SOURCE","-std=c11","-O1","-Wall","-Wextra",
            "-Wpedantic","-Werror","-fsanitize=undefined,bounds",
            str(c),"-o",str(executable)],
            capture_output=True,text=True,timeout=30,check=False)
        if build.returncode:
            raise ValueError("VH143_NATIVE_ATOMIC_WRITER_COMPILE_REFUSED")
        def invoke(mode,path):
            result=subprocess.run([str(executable),mode,str(path)],
                                  capture_output=True,text=True,
                                  timeout=10,check=False)
            if result.returncode!=0 or result.stdout or result.stderr:
                raise ValueError("VH143_NATIVE_PRIVATE_PATH_GUARD_REFUSED")
        target=root/"controlled"
        target.mkdir(mode=0o700)
        target.chmod(0o700)
        finale=target/"vh142-interpreter-mmio.jsonl"
        stage=target/".vh143-private-mmio-staging.jsonl"
        # The new receipt appears ONLY after all 19 events are complete.
        invoke("accept",target)
        if stage.exists() or not finale.is_file() or finale.stat().st_mode&0o777!=0o600:
            raise ValueError("VH143_PARTIAL_OR_WRONG_MODE_RECEIPT_REFUSED")
        raw=read_private_exact_mmio_trace(finale)
        events=parse_exact_mmio_trace(raw)
        if len(events)!=19:
            raise ValueError("VH143_INCOMPLETE_NATIVE_EVENT_JOURNAL_REFUSED")
        digest=hashlib.sha256(raw).hexdigest()
        # A second run cannot overwrite nor modify the existing file.
        invoke("refuse",target)
        if hashlib.sha256(read_private_exact_mmio_trace(finale)).hexdigest()!=digest:
            raise ValueError("VH143_RECEIPT_OVERWRITE_REFUSED")
        # Any incomplete/stale staging leaf refuses the operation.
        staged=root/"staging"
        staged.mkdir(mode=0o700)
        (staged/stage.name).write_bytes(b"collision")
        invoke("refuse",staged)
        if (staged/finale.name).exists():
            raise ValueError("VH143_STALE_STAGE_PUBLISHED_REFUSED")
        # Every path ancestor must be a real, non-symlink directory.
        link=root/"alias"
        link.symlink_to(target,target_is_directory=True)
        invoke("refuse",link)
        safe=root/"physical"
        safe.mkdir(mode=0o700)
        inner=safe/"inner"
        inner.mkdir(mode=0o700)
        alias=root/"symlinked-parent"
        alias.symlink_to(safe,target_is_directory=True)
        invoke("refuse",alias/"inner")
        if (inner/finale.name).exists():
            raise ValueError("VH143_SYMLINKED_PARENT_PUBLISHED_REFUSED")
        # Reject group/world-writable intermediates even with a safe leaf.
        exposed=root/"mutable"
        exposed.mkdir(mode=0o700)
        child=exposed/"owned"
        child.mkdir(mode=0o700)
        exposed.chmod(0o777)
        invoke("refuse",child)
        if (child/finale.name).exists():
            raise ValueError("VH143_MUTABLE_PARENT_PUBLISHED_REFUSED")
        exposed.chmod(0o700)
        # Never accept string traversal aliases or relative paths.
        for bad in (
            str(target)+"/",
            str(root)+"/./controlled",
            str(root)+"/x/../controlled",
            str(root)+"//controlled",
            "controlled",
            "/",
        ):
            invoke("refuse",bad)
        # A preexisting, maliciously symlinked final file cannot be
        # overwritten; fixed staging leaf is also protected.
        blocked=root/"protected-final"
        blocked.mkdir(mode=0o700)
        (blocked/finale.name).symlink_to(finale)
        invoke("refuse",blocked)
        if hashlib.sha256(read_private_exact_mmio_trace(finale)).hexdigest()!=digest:
            raise ValueError("VH143_SYMLINK_LEAF_REWRITTEN_REFUSED")
        if (blocked/stage.name).exists():
            raise ValueError("VH143_STALE_TEMPFILE_LEAK_REFUSED")
    print("VH143_COMPILED_ATOMIC_PRIVATE_RECEIPT_PASS "
          "events=19 atomic_publish=1 full_ancestor_nofollow=1 "
          "overwrite_refused=1 writable_ancestor_refused=1 "
          "symlink_and_stale_stage_refused=1 original_retail=0")


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--cc",required=True)
    run(p.parse_args().cc)
