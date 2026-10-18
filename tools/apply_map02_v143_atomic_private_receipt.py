#!/usr/bin/env python3
"""Atomic publication of v142's actual-interpreter private MMIO receipts.

A 0600 final receipt must never become visible before ALL 19 MIPS SW events
have been completely written and fsync'ed. Walk every ancestor via dirfd and
O_NOFOLLOW, refusing symlinks, traversal and group/world-writable ancestors.
The self-authored v129 PS-X CPU/GPU/DMA program remains entirely unchanged.
This is a private provenance-safety improvement, not original MAP02 proof.
"""
from __future__ import annotations
from pathlib import Path

from .apply_map02_v142_native_private_mmio_receipt import (
    apply as apply_v142,native_private_receipt_code,
)
from .apply_map02_v69_pcsx_rearmed import once


def native_atomic_private_receipt_code():
    return r'''
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#ifndef O_NOFOLLOW
#error VH143_REQUIRES_POSIX_NOFOLLOW
#endif
#ifndef O_DIRECTORY
#error VH143_REQUIRES_POSIX_DIRECTORY_FDS
#endif
#ifndef O_CLOEXEC
#error VH143_REQUIRES_CLOEXEC
#endif
#ifndef AT_SYMLINK_NOFOLLOW
#error VH143_REQUIRES_LINK_INSPECTION
#endif

#define VH142_EXPECTED_EVENTS 19u
#define VH142_RECEIPT_NAME "vh142-interpreter-mmio.jsonl"
#define VH143_STAGING_NAME ".vh143-private-mmio-staging.jsonl"
#define VH143_MAX_PRIVATE_PATH 4096u
#define VH143_MAX_COMPONENT 255u
typedef struct {u32 pc,word,address,value;} vh142_event;
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
        vh142_bad++; return;
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

/* Start at the kernel's root directory descriptor. No string-concatenated
 * path access after this point, no symlinks at any path component, and no
 * mutable group/world-writable ancestor. Never enter "." or "..". */
static int vh143_open_verified_directory(const char *path) {
    int fd=-1,next=-1;
    const char *at;
    struct stat st;
    size_t length;
    if(path==NULL || path[0]!='/' ||
       (length=strnlen(path,VH143_MAX_PRIVATE_PATH+1u))<2u ||
       length>VH143_MAX_PRIVATE_PATH) return -1;
    fd=open("/",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(fd<0) return -1;
    at=path+1;
    for(;;) {
        const char *end=strchr(at,'/');
        size_t count=end?(size_t)(end-at):strlen(at);
        char component[VH143_MAX_COMPONENT+1u];
        unsigned last=(end==NULL);
        if(count==0u || count>VH143_MAX_COMPONENT ||
           (count==1u && at[0]=='.') ||
           (count==2u && at[0]=='.' && at[1]=='.'))
            goto refused;
        memcpy(component,at,count);
        component[count]='\0';
        next=openat(fd,component,
                    O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
        if(next<0 || fstat(next,&st)!=0 || !S_ISDIR(st.st_mode))
            goto refused;
        if(last) {
            /* The final output directory belongs only to this account. */
            if(st.st_uid!=geteuid() || (st.st_mode&0777)!=0700)
                goto refused;
        } else {
            /* Ancestors must be root-owned or owned by this account,
             * and none may be mutable by group or other users. */
            if((st.st_uid!=0 && st.st_uid!=geteuid()) ||
               (st.st_mode&0022)!=0)
                goto refused;
        }
        if(close(fd)!=0) { fd=-1; goto refused; }
        fd=next;
        next=-1;
        if(last) return fd;
        at=end+1;
    }
refused:
    if(next>=0) (void)close(next);
    if(fd>=0) (void)close(fd);
    return -1;
}

/* Stage fully, fsync data, atomically publish with linkat(EEXIST-safe),
 * remove staging leaf, fsync directory. Incomplete final files are never
 * published. Fixed exclusive staging name ensures concurrent writers fail
 * closed rather than racing a shared rename. */
int vh142_write_receipt(const char *private_dir,unsigned corrupt_claim) {
    int dirfd=-1,fd=-1,ok=-1,staged=0,published=0;
    unsigned i;
    struct stat st,final_st;
    char line[240];
    vh142_active=0u;
    if(vh142_bad!=0u || vh142_count!=VH142_EXPECTED_EVENTS)
        return -1;
    dirfd=vh143_open_verified_directory(private_dir);
    if(dirfd<0) return -1;
    fd=openat(dirfd,VH143_STAGING_NAME,
              O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd<0) goto cleanup;
    staged=1;
    if(fstat(fd,&st)!=0 || !S_ISREG(st.st_mode) ||
       st.st_uid!=geteuid() || st.st_nlink!=1u ||
       (st.st_mode&0777)!=0600) goto cleanup;
    for(i=0;i<VH142_EXPECTED_EVENTS;i++) {
        int count;
        u32 word=vh142_events[i].word;
        if(corrupt_claim && i==2u) word^=1u; /* receipt only */
        count=snprintf(line,sizeof(line),
           "{\"address\":%u,\"pc\":%u,\"schema\":\"vh.map02.private-exact-mmio-claim.v1\","
           "\"seq\":%u,\"value\":%u,\"word\":%u}\n",
           (unsigned)vh142_events[i].address,
           (unsigned)vh142_events[i].pc,i,
           (unsigned)vh142_events[i].value,(unsigned)word);
        if(count<=0 || (size_t)count>=sizeof(line) ||
           vh142_write_all(fd,line,(size_t)count)!=0) goto cleanup;
    }
    if(fsync(fd)!=0 || fstat(fd,&final_st)!=0 ||
       final_st.st_dev!=st.st_dev || final_st.st_ino!=st.st_ino ||
       final_st.st_nlink!=1u || final_st.st_uid!=geteuid() ||
       (final_st.st_mode&0777)!=0600) goto cleanup;
    if(close(fd)!=0) { fd=-1; goto cleanup; }
    fd=-1;
    /* linkat fails with EEXIST if a final receipt already exists.
     * No partial/truncated final name can be exposed. */
    if(linkat(dirfd,VH143_STAGING_NAME,
              dirfd,VH142_RECEIPT_NAME,0)!=0) goto cleanup;
    published=1;
    if(fstatat(dirfd,VH142_RECEIPT_NAME,&final_st,
               AT_SYMLINK_NOFOLLOW)!=0 ||
       !S_ISREG(final_st.st_mode) || final_st.st_dev!=st.st_dev ||
       final_st.st_ino!=st.st_ino || final_st.st_nlink!=2u ||
       final_st.st_uid!=geteuid() ||
       (final_st.st_mode&0777)!=0600) goto cleanup;
    if(unlinkat(dirfd,VH143_STAGING_NAME,0)!=0) goto cleanup;
    staged=0;
    if(fsync(dirfd)!=0) goto cleanup;
    ok=0;
cleanup:
    if(fd>=0 && close(fd)!=0) ok=-1;
    if(ok!=0 && published)
        (void)unlinkat(dirfd,VH142_RECEIPT_NAME,0);
    if(staged) (void)unlinkat(dirfd,VH143_STAGING_NAME,0);
    if(dirfd>=0 && close(dirfd)!=0) ok=-1;
    return ok;
}
'''


def patch_native_writer(source):
    return once(source,native_private_receipt_code(),
                native_atomic_private_receipt_code(),
                "v143 no-symlink directory traversal and atomic publication")


def apply(root:Path):
    previous=apply_v142(root)
    filename=root.resolve()/"libpcsxcore/psxmem.c"
    original=filename.read_text()
    improved=patch_native_writer(original)
    filename.write_text(improved)
    return dict(previous,
        v143_private_parent_symlinks_refused=True,
        v143_untrusted_mutable_ancestors_refused=True,
        v143_partial_final_receipt_never_published=True,
        v143_linkat_no_overwrite_atomic_publication=True,
        v143_data_and_directory_fsync_verified=True,
        original_retail_exe_executed=False,
        original_map02_frame_rendered=False,
        switch_hd_gpu_equivalence_proven=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
