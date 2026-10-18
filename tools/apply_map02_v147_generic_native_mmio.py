#!/usr/bin/env python3
"""Bounded, source-agnostic native MIPS GPU/DMA capture, tested synthetic-only.

This stage removes v142's fixed 19-event buffer *for the independent v147
observer only*, retaining all older diagnostics. Every psxMemWrite32 callback
can append a GPU/DMA SW; repeated PCs are allowed. Exceeding the 1024-event
ceiling refuses publication, never silently truncates. v147 is enabled only
inside an explicitly opted-in v129 synthetic PCSX flow in public CI.
Separate offline v141 code allows local/private original EXE/ELF correlation;
retail execution itself has NOT been enabled or confirmed by this stage.
"""
from __future__ import annotations
from pathlib import Path

from .apply_map02_v144_private_run_challenge import apply as apply_v144
from .apply_map02_v69_pcsx_rearmed import once


def native_generic_capture_code():
    return r'''
/* Generic MIPS SW observer: no hardcoded source PC/order/word/value.
 * SOURCE CHECKS are performed by the independent private v141 reader.
 * Bounded 1024 events with an explicit overflow refusal; never truncate. */
#define VH147_MAX_EVENTS 1024u
#define VH147_FINAL_NAME "vh147-original-mips-events.jsonl"
#define VH147_STAGE_NAME ".vh147-private-mips-stage.jsonl"
static vh142_event vh147_events[VH147_MAX_EVENTS];
static unsigned vh147_active,vh147_count,vh147_bad;

void vh147_enable(void) {
    vh147_active=1u; vh147_count=0u; vh147_bad=0u;
}
static void vh147_capture(psxRegisters *regs,u32 address,u32 value) {
    unsigned physical=address&0x1fffffffu;
    if(!vh147_active) return;
    switch(physical) {
      case 0x1f8010a0u: case 0x1f8010a4u: case 0x1f8010a8u:
      case 0x1f8010f0u: case 0x1f801810u: case 0x1f801814u:
        break;
      default: return;
    }
    if(vh147_count>=VH147_MAX_EVENTS ||
       (regs->pc&3u)!=0u || ((regs->code>>26)!=0x2bu)) {
        vh147_bad++;
        return;
    }
    vh147_events[vh147_count].pc=regs->pc-4u;
    vh147_events[vh147_count].word=regs->code;
    vh147_events[vh147_count].address=address;
    vh147_events[vh147_count].value=value;
    vh147_count++;
}
/* Independent fresh output dir; never share v142's directory or names.
 * Only publish complete, fsync'ed, no-follow 0600 JSONL. Retain no
 * untrusted path, GPU value or private hash in native stdout. */
int vh147_write_receipt(const char *private_dir) {
    int dirfd=-1,fd=-1,staged=0,published=0,challenge_created=0,ok=-1;
    unsigned i;
    struct stat before,after;
    char line[240];
    const char *challenge=getenv("VH144_RECEIPT_CHALLENGE_HEX");
    vh147_active=0u;
    if(vh147_bad!=0u || vh147_count==0u ||
       vh147_count>VH147_MAX_EVENTS) return -1;
    dirfd=vh143_open_verified_directory(private_dir);
    if(dirfd<0) return -1;
    fd=openat(dirfd,VH147_STAGE_NAME,
              O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd<0) goto finish;
    staged=1;
    if(fstat(fd,&before)!=0 || !S_ISREG(before.st_mode) ||
       before.st_uid!=geteuid() || before.st_nlink!=1u ||
       (before.st_mode&0777)!=0600) goto finish;
    for(i=0;i<vh147_count;i++) {
        int count=snprintf(line,sizeof(line),
            "{\"address\":%u,\"pc\":%u,"
            "\"schema\":\"vh.map02.private-exact-mmio-claim.v1\","
            "\"seq\":%u,\"value\":%u,\"word\":%u}\n",
            (unsigned)vh147_events[i].address,
            (unsigned)vh147_events[i].pc,i,
            (unsigned)vh147_events[i].value,
            (unsigned)vh147_events[i].word);
        if(count<=0 || (size_t)count>=sizeof(line) ||
           vh142_write_all(fd,line,(size_t)count)!=0) goto finish;
    }
    if(fsync(fd)!=0 || fstat(fd,&after)!=0 ||
       after.st_dev!=before.st_dev || after.st_ino!=before.st_ino ||
       after.st_nlink!=1u || after.st_uid!=geteuid() ||
       (after.st_mode&0777)!=0600) goto finish;
    if(close(fd)!=0) {fd=-1;goto finish;}
    fd=-1;
    if(vh144_write_challenge(dirfd,challenge,&challenge_created)!=0)
        goto finish;
    if(linkat(dirfd,VH147_STAGE_NAME,dirfd,VH147_FINAL_NAME,0)!=0)
        goto finish;
    published=1;
    if(fstatat(dirfd,VH147_FINAL_NAME,&after,AT_SYMLINK_NOFOLLOW)!=0 ||
       !S_ISREG(after.st_mode) || after.st_dev!=before.st_dev ||
       after.st_ino!=before.st_ino || after.st_nlink!=2u ||
       after.st_uid!=geteuid() || (after.st_mode&0777)!=0600)
        goto finish;
    if(unlinkat(dirfd,VH147_STAGE_NAME,0)!=0) goto finish;
    staged=0;
    if(fsync(dirfd)!=0) goto finish;
    ok=0;
finish:
    if(fd>=0 && close(fd)!=0) ok=-1;
    if(ok!=0 && published)
        (void)unlinkat(dirfd,VH147_FINAL_NAME,0);
    if(ok!=0 && challenge_created)
        (void)unlinkat(dirfd,VH144_CHALLENGE_NAME,0);
    if(staged) (void)unlinkat(dirfd,VH147_STAGE_NAME,0);
    if(close(dirfd)!=0) ok=-1;
    return ok;
}
unsigned vh147_event_count(void) {return vh147_count;}
'''


def patch_generic_memory(source):
    source=once(source,
        "void vh140_mmio_enable(unsigned mutate_expected) {\n",
        native_generic_capture_code()+
        "void vh140_mmio_enable(unsigned mutate_expected) {\n",
        "inject separate bounded generic MIPS SW observer into real interpreter")
    return once(source,
        "    if(vh142_active) vh142_capture(regs,addr,value);\n",
        "    if(vh147_active) vh147_capture(regs,addr,value);\n"
        "    if(vh142_active) vh142_capture(regs,addr,value);\n",
        "capture arbitrary observed MIPS GPU/DMA SW before synthetic classifier")


def patch_generic_frontend(source):
    source=once(source,
        "\tint vh142_corrupt_receipt = 0;\n",
        "\tint vh142_corrupt_receipt = 0;\n"
        "\tint vh147_generic_trace = 0;\n",
        "separate generic native trace opt-in flag")
    source=once(source,
        '\t\telse if (!strcmp(argv[i], "--vh142-private-receipt"))\n',
        '\t\telse if (!strcmp(argv[i], "--vh147-bounded-mmio"))\n'
        '\t\t\tvh147_generic_trace=1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh142-private-receipt"))\n',
        "explicit generic native MMIO recorder CLI switch")
    source=once(source,
        "        extern void vh142_enable(void);\n",
        "        extern void vh142_enable(void);\n"
        "        extern void vh147_enable(void);\n"
        "        extern int vh147_write_receipt(const char *);\n"
        "        extern unsigned vh147_event_count(void);\n",
        "v147 observer and bounded writer ABI")
    source=once(source,
        "        if(vh142_private_receipt && !vh140_value_capture){\n",
        '        if(vh147_generic_trace && !vh142_private_receipt){\n'
        '            SysPrintf("VH147_MODE_REFUSED\\n");\n'
        '            ClosePlugins();SysClose();menu_finish();plat_finish();return 53;\n'
        '        }\n'
        "        if(vh142_private_receipt && !vh140_value_capture){\n",
        "synthetic-only safe activation initially requires v142 runtime witness")
    source=once(source,
        "        if(vh142_private_receipt) vh142_enable();\n",
        "        if(vh142_private_receipt) vh142_enable();\n"
        "        if(vh147_generic_trace) vh147_enable();\n",
        "generic MIPS store recorder enabled before actual interpreted stage")
    source=once(source,
        "            if(vh142_private_receipt){\n",
        '            if(vh147_generic_trace){\n'
        '                if(vh147_write_receipt(getenv("VH147_PRIVATE_TRACE_DIR"))!=0){\n'
        '                    SysPrintf("VH147_GENERIC_MMIO_REFUSED\\n");\n'
        '                    ClosePlugins();SysClose();menu_finish();plat_finish();return 53;\n'
        '                }\n'
        '                SysPrintf("VH147_NATIVE_BOUNDED_MMIO_PASS"\n'
        '                          " events=%u source=synthetic original_retail=0\\n",\n'
        '                          vh147_event_count());\n'
        '            }\n'
        "            if(vh142_private_receipt){\n",
        "seal generic runtime receipt after four original synthetic CPU stages")
    return source


def apply(root:Path):
    previous=apply_v144(root)
    core=root.resolve()/"libpcsxcore/psxmem.c"
    front=root.resolve()/"frontend/main.c"
    core.write_text(patch_generic_memory(core.read_text()))
    front.write_text(patch_generic_frontend(front.read_text()))
    return dict(previous,
        v147_bounded_generic_interpreter_mmio_observer=True,
        v147_capacity=1024,
        v147_repeated_mips_pc_supported=True,
        v147_overflow_publication_refused=True,
        v147_separate_private_atomic_receipt=True,
        v147_original_retail_runtime_opt_in_enabled=False,
        v147_original_retail_runtime_executed=False,
        v147_original_map02_rendered=False,
        v147_nintendo_switch_parity_proven=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
