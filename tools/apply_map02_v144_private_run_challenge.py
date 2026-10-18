#!/usr/bin/env python3
"""Bind a *synthetic* native MIPS receipt to a fresh operator challenge.

Adds an exclusive, fsync'ed 0600 challenge sidecar to v143's private
atomically published receipt. Both files are created by the same native
PSCX interpreter process; no challenge is printed to CI logs. An external,
independently retained challenge lets a private verifier reject accidental
replay and cross-run mixups, NOT authenticate an adversarial producer.

The original MIPS program and GPU/DMA/Unai/VBlank logic are unmodified.
"""
from __future__ import annotations
from pathlib import Path
from .apply_map02_v143_atomic_private_receipt import (
    apply as apply_v143,native_atomic_private_receipt_code,
)
from .apply_map02_v69_pcsx_rearmed import once


def native_challenge_bound_receipt_code():
    source=native_atomic_private_receipt_code()
    source=once(source,
        "#include <errno.h>\n",
        "#include <errno.h>\n#include <stdlib.h>\n",
        "explicit challenge environment lookup header")
    source=once(source,
        '#define VH143_STAGING_NAME ".vh143-private-mmio-staging.jsonl"\n',
        '#define VH143_STAGING_NAME ".vh143-private-mmio-staging.jsonl"\n'
        '#define VH144_CHALLENGE_NAME "vh144-run-challenge.hex"\n',
        "additional private-only challenge leaf")
    function=r'''
/* A 128-bit fresh independent operator challenge, rendered as exactly
 * 32 lowercase hexadecimal bytes. Do not create reusable weak defaults. */
static int vh144_write_challenge(int dirfd,const char *hex,int *created) {
    int fd=-1,ok=-1;
    struct stat st;
    size_t i;
    if(hex==NULL || strnlen(hex,34u)!=32u || created==NULL)
        return -1;
    for(i=0;i<32u;i++)
        if(!((hex[i]>='0' && hex[i]<='9') ||
             (hex[i]>='a' && hex[i]<='f')))
            return -1;
    fd=openat(dirfd,VH144_CHALLENGE_NAME,
              O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd<0) return -1;
    *created=1;
    if(fstat(fd,&st)!=0 || !S_ISREG(st.st_mode) ||
       st.st_uid!=geteuid() || st.st_nlink!=1u ||
       (st.st_mode&0777)!=0600 ||
       vh142_write_all(fd,hex,32u)!=0 ||
       vh142_write_all(fd,"\n",1u)!=0 || fsync(fd)!=0)
        goto done;
    ok=0;
done:
    if(close(fd)!=0) ok=-1;
    return ok;
}

'''
    source=once(source,
        "int vh142_write_receipt(const char *private_dir,unsigned corrupt_claim) {\n",
        function+"int vh142_write_receipt(const char *private_dir,unsigned corrupt_claim) {\n",
        "challenge binder before atomic receipt writer")
    source=once(source,
        "    int dirfd=-1,fd=-1,ok=-1,staged=0,published=0;\n",
        "    int dirfd=-1,fd=-1,ok=-1,staged=0,published=0,challenge_created=0;\n"
        '    const char *fresh_hex=getenv("VH144_RECEIPT_CHALLENGE_HEX");\n',
        "unique output lifecycle for challenge")
    source=once(source,
        "    if(close(fd)!=0) { fd=-1; goto cleanup; }\n    fd=-1;\n"
        "    /* linkat fails with EEXIST if a final receipt already exists.\n",
        "    if(close(fd)!=0) { fd=-1; goto cleanup; }\n    fd=-1;\n"
        "    /* Write and fsync the fresh run challenge *before* publishing\n"
        "     * the fully fsynced receipt. A final file therefore never\n"
        "     * appears without a completed private challenge sidecar. */\n"
        "    if(vh144_write_challenge(dirfd,fresh_hex,&challenge_created)!=0)\n"
        "        goto cleanup;\n"
        "    /* linkat fails with EEXIST if a final receipt already exists.\n",
        "publish only after complete challenge sidecar")
    source=once(source,
        "    if(ok!=0 && published)\n"
        "        (void)unlinkat(dirfd,VH142_RECEIPT_NAME,0);\n"
        "    if(staged) (void)unlinkat(dirfd,VH143_STAGING_NAME,0);\n",
        "    if(ok!=0 && published)\n"
        "        (void)unlinkat(dirfd,VH142_RECEIPT_NAME,0);\n"
        "    if(ok!=0 && challenge_created)\n"
        "        (void)unlinkat(dirfd,VH144_CHALLENGE_NAME,0);\n"
        "    if(staged) (void)unlinkat(dirfd,VH143_STAGING_NAME,0);\n",
        "cleanup only our newly created sidecar")
    return source


def patch_native_challenge_writer(source):
    return once(source,native_atomic_private_receipt_code(),
                native_challenge_bound_receipt_code(),
                "v144 private run challenge paired with atomic receipt")


def apply(root:Path):
    prior=apply_v143(root)
    path=root.resolve()/"libpcsxcore/psxmem.c"
    path.write_text(patch_native_challenge_writer(path.read_text()))
    return dict(prior,
        v144_native_fresh_challenge_required=True,
        v144_private_challenge_record_mode="0600",
        v144_receipt_published_only_after_challenge_fsync=True,
        v144_challenge_replay_refused_by_separate_verifier=True,
        original_retail_MAP02_executed=False,
        physical_ps1_equivalence_proven=False,
        nintendo_switch_hd_parity_proven=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
