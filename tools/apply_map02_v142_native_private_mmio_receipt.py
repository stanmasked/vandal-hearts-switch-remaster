#!/usr/bin/env python3
"""Capture native interpreter MMIO events in a LOCAL 0600 receipt.

Only the exact self-authored v129 MIPS EXE and locked v140 opt-in test are
eligible. A private receipt is recorded in a caller-controlled 0700 directory
after the existing genuine PCSX interpreter has executed all SW instructions.
Neither the event values nor paths enter console, public GitHub artifacts, or
the reports. This is not yet a general original-game trace attestation.
"""
from __future__ import annotations

from pathlib import Path

from .apply_map02_v140_mmio_effects import (
    apply as apply_v140,expected_actual_mmio,
    patch_synthetic_oracle as v140_oracle,
)
from .apply_map02_v139_mips_word_stages import (
    codeword_expectations,modify_oracle as v139_oracle,
)
from .apply_map02_v138_interpreter_pc import modified_native_oracle
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v129_four_vblank_exe import build


def native_private_receipt_code():
    """Compiled C observer: private in-memory buffer and protected atomic leaf."""
    return r'''
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#ifndef O_NOFOLLOW
#error VH142_REQUIRES_POSIX_NOFOLLOW
#endif
#ifndef O_DIRECTORY
#error VH142_REQUIRES_POSIX_DIRECTORY_FDS
#endif
#ifndef O_CLOEXEC
#error VH142_REQUIRES_CLOEXEC
#endif

#define VH142_EXPECTED_EVENTS 19u
#define VH142_RECEIPT_NAME "vh142-interpreter-mmio.jsonl"
typedef struct {
    u32 pc,word,address,value;
} vh142_event;
static vh142_event vh142_events[VH142_EXPECTED_EVENTS];
static unsigned vh142_active,vh142_count,vh142_bad;

void vh142_enable(void) {
    vh142_count=0u; vh142_bad=0u; vh142_active=1u;
}
static void vh142_capture(psxRegisters *regs,u32 address,u32 value) {
    unsigned physical=address&0x1fffffffu;
    if(!vh142_active) return;
    switch(physical) {
      case 0x1f8010a0u: case 0x1f8010a4u: case 0x1f8010a8u:
      case 0x1f8010f0u: case 0x1f801810u: case 0x1f801814u:
        break;
      default: return;
    }
    if(vh142_count>=VH142_EXPECTED_EVENTS ||
       (regs->pc&3u) || ((regs->code>>26)!=0x2bu)) {
        vh142_bad++;
        return;
    }
    vh142_events[vh142_count].pc=regs->pc-4u;
    vh142_events[vh142_count].word=regs->code;
    vh142_events[vh142_count].address=address;
    vh142_events[vh142_count].value=value;
    vh142_count++;
}
static int vh142_write_all(int fd,const char *line,size_t bytes) {
    size_t used=0u;
    while(used<bytes) {
        ssize_t n=write(fd,line+used,bytes-used);
        if(n<0 && errno==EINTR) continue;
        if(n<=0) return -1;
        used+=(size_t)n;
    }
    return 0;
}
int vh142_write_receipt(const char *private_dir,unsigned corrupt_claim) {
    int dirfd=-1,fd=-1,ok=-1,created=0;
    unsigned i;
    struct stat st;
    char line[240];
    vh142_active=0u;
    if(private_dir==NULL || private_dir[0]=='\0' ||
       vh142_bad!=0u || vh142_count!=VH142_EXPECTED_EVENTS)
        return -1;
    /* CI and the private operator must supply an owned, pre-created 0700
     * directory with no symlinked ancestors. O_NOFOLLOW closes the last
     * directory and receipt-leaf symlink cases; never overwrite receipts. */
    dirfd=open(private_dir,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(dirfd<0 || fstat(dirfd,&st)!=0 ||
       !S_ISDIR(st.st_mode) || st.st_uid!=geteuid() ||
       (st.st_mode&0777)!=0700) goto cleanup;
    fd=openat(dirfd,VH142_RECEIPT_NAME,
              O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd<0) goto cleanup;
    created=1;
    if(fstat(fd,&st)!=0 || !S_ISREG(st.st_mode) ||
       st.st_uid!=geteuid() || st.st_nlink!=1u ||
       (st.st_mode&0777)!=0600) goto cleanup;
    for(i=0;i<VH142_EXPECTED_EVENTS;i++) {
        int count;
        u32 word=vh142_events[i].word;
        /* Negative control corrupts the private receipt only, never the
         * executed program, CPU state, GPU command or native MIPS probe. */
        if(corrupt_claim && i==2u) word^=1u;
        count=snprintf(line,sizeof(line),
           "{\"address\":%u,\"pc\":%u,\"schema\":\"vh.map02.private-exact-mmio-claim.v1\","
           "\"seq\":%u,\"value\":%u,\"word\":%u}\n",
           (unsigned)vh142_events[i].address,
           (unsigned)vh142_events[i].pc,i,
           (unsigned)vh142_events[i].value,(unsigned)word);
        if(count<=0 || (size_t)count>=sizeof(line) ||
           vh142_write_all(fd,line,(size_t)count)!=0) goto cleanup;
    }
    if(fsync(fd)!=0 || fstat(fd,&st)!=0 ||
       !S_ISREG(st.st_mode) || st.st_nlink!=1u ||
       st.st_uid!=geteuid() || (st.st_mode&0777)!=0600)
        goto cleanup;
    ok=0;
cleanup:
    if(fd>=0 && close(fd)!=0) ok=-1;
    if(ok!=0 && created && dirfd>=0)
        (void)unlinkat(dirfd,VH142_RECEIPT_NAME,0);
    if(dirfd>=0 && close(dirfd)!=0) ok=-1;
    return ok;
}
'''


def patch_native_observer(src):
    src=once(src,
        "void vh140_mmio_enable(unsigned mutate_expected) {\n",
        native_private_receipt_code()+
        "void vh140_mmio_enable(unsigned mutate_expected) {\n",
        "v142 protected host-local native receipt writer")
    src=once(src,
        "    if(vh140_active) vh140_mmio_observe(addr,value);\n",
        "    if(vh142_active) vh142_capture(regs,addr,value);\n"
        "    if(vh140_active) vh140_mmio_observe(addr,value);\n",
        "v142 actual MIPS SW MMIO receipt capture before v140 value checks")
    return src


def patch_native_oracle(src):
    src=once(src,
        "        extern void vh140_mmio_enable(unsigned mutate_expected);\n",
        "        extern void vh140_mmio_enable(unsigned mutate_expected);\n"
        "        extern void vh142_enable(void);\n"
        "        extern int vh142_write_receipt(const char *,unsigned);\n",
        "private v142 native MIPS callback ABI")
    src=once(src,
        "        if(vh140_value_capture && !vh139_word_capture){\n",
        '        if(vh142_private_receipt && !vh140_value_capture){\n'
        '            SysPrintf("VH142_MODE_REFUSED\\n");\n'
        '            ClosePlugins();SysClose();menu_finish();plat_finish();return 52;\n'
        '        }\n'
        "        if(vh140_value_capture && !vh139_word_capture){\n",
        "new v142 receipt requires whole source-bound v138-140 CPU witness")
    src=once(src,
        "        if(vh140_value_capture) vh140_mmio_enable(vh140_corrupt_value);\n",
        "        if(vh140_value_capture) vh140_mmio_enable(vh140_corrupt_value);\n"
        "        if(vh142_private_receipt) vh142_enable();\n",
        "native receipt active only after synthetic EXE has been checked")
    guard=r'''            if(vh142_private_receipt){
                const char *private_receipt_dir=getenv("VH142_PRIVATE_RECEIPT_DIR");
                if(vh142_write_receipt(private_receipt_dir,
                                     vh142_corrupt_receipt)!=0){
                    SysPrintf("VH142_PRIVATE_RECEIPT_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 52;
                }
                SysPrintf("VH142_NATIVE_PRIVATE_RECEIPT_PASS"
                          " events=19 source=synthetic emulator=pcsx original_retail=0\n");
            }
'''
    src=once(src,
        '            if(vh140_value_capture){\n',
        guard+'            if(vh140_value_capture){\n',
        "native bound receipt written only after all four real CPU stages")
    return src


def apply(root:Path):
    prior=apply_v140(root)
    events,words,prefixes=codeword_expectations()
    values=expected_actual_mmio()
    if len(events)!=19 or len(words)!=19 or len(values)!=19 or prefixes!=(7,11,15,19):
        raise ValueError("v142 only allows pinned source-authored MIPS program")
    code=root.resolve()/"libpcsxcore/psxmem.c"
    frontend=root.resolve()/"frontend/main.c"
    source=patch_native_observer(code.read_text())
    main=frontend.read_text()
    main=once(main,
        "\tint vh140_corrupt_value = 0;\n",
        "\tint vh140_corrupt_value = 0;\n"
        "\tint vh142_private_receipt = 0;\n"
        "\tint vh142_corrupt_receipt = 0;\n",
        "native source-only receipt flags")
    main=once(main,
        '\t\telse if (!strcmp(argv[i], "--vh140-mmio-values"))\n',
        '\t\telse if (!strcmp(argv[i], "--vh142-private-receipt"))\n'
        '\t\t\tvh142_private_receipt=1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh142-corrupt-receipt"))\n'
        '\t\t\tvh142_corrupt_receipt=1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh140-mmio-values"))\n',
        "opt-in private receipt and adversarial receipt-only mutation")
    _,stops,_,_,wait=build()
    original=v140_oracle(v139_oracle(
        modified_native_oracle(stops,wait,len(events)),len(events)))
    modified=patch_native_oracle(original)
    main=once(main,original,modified,
        "single existing v140 source-authored native MIPS oracle")
    code.write_text(source)
    frontend.write_text(main)
    return dict(prior,
        v142_actual_native_synthetic_mmio_receipt=True,
        v142_event_count=19,
        v142_created_leaf_mode="0600",
        v142_receipt_canonical_order_and_native_runtime=True,
        v142_corruption_changes_receipt_only=True,
        v142_original_retail_execution_verified=False,
        v142_original_map02_rendering_verified=False,
        v142_nintendo_switch_gpu_parity_verified=False)


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pcsx_checkout",type=Path)
    print(apply(parser.parse_args().pcsx_checkout))
