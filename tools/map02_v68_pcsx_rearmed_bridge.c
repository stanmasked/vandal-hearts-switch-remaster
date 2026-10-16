#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
/* v66 opt-in, local-only, source-level PCSX ReARMed GPU probe bridge.
 *
 * Single-threaded diagnostic path. This is a PRE-SUBMISSION snapshot of
 * emulator RAM at psxDma2() just before GPU_dmaChain(), not proof of GPU
 * plugin consumption. No proprietary data is included in repository.
 * Host opt-in: export VH_MAP02_V66_PCSX_LOG=/private/probe.jsonl.
 * The output is sensitive: restrict permissions and keep it local.
 */
#include "vh66_gpu_probe_bridge.h"
#include "vh65_gpu_probe.h"

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define VH66_RAM_BYTES (2u*1024u*1024u)
#define VH66_MAX_NODES 4096u
#define VH66_MAX_WORDS 65536u

static FILE *vh66_file;
static int vh66_initialized;
static int vh66_failed;
static unsigned int vh66_frame;
static uint64_t vh66_tick;

static void vh66_finish(void) {
    if (vh66_file) {
        fflush(vh66_file);
        fclose(vh66_file);
        vh66_file=NULL;
    }
}
static int vh66_open(void) {
    if (vh66_initialized) return vh66_file && !vh66_failed ? 0:-1;
    vh66_initialized=1;
    const char *path=getenv("VH_MAP02_V66_PCSX_LOG");
    if (!path || !*path) return -1;  /* no opt-in, never create data */
    int fd=open(path,O_WRONLY|O_CREAT|O_EXCL,0600);
    if (fd<0) return -1;
    vh66_file=fdopen(fd,"w");
    if (!vh66_file) {close(fd);return -1;}
    if (vh65_probe_begin(vh66_file,"user-supplied-unverified")) {
        vh66_finish();
        return -1;
    }
    atexit(vh66_finish);
    vh66_tick=1;
    return 0;
}
static int vh66_fail(void) {
    vh66_failed=1;
    if (vh66_file) {
        /* Unsupported data MUST make the v65 JSONL consumer refuse,
         * rather than silently omitting an instruction/GP1 write. */
        fputs("{\"kind\":\"CAPTURE_UNSUPPORTED_OR_TRUNCATED\"}\n",vh66_file);
        fflush(vh66_file);
    }
    return -1;
}
static uint32_t vh66_le32(const unsigned char *data) {
    return (uint32_t)data[0]|((uint32_t)data[1]<<8)|
           ((uint32_t)data[2]<<16)|((uint32_t)data[3]<<24);
}
/* GP0 MMIO write observed at psxHwWrite32 (0x1f801810),
 * immediately before the original GPU_writeData(value). This is
 * the CPU-side port write, not proof of GPU-plugin consumption.
 */
int vh68_pcsx_gp0_mmio_observe(uint32_t word) {
    if (vh66_open()) return -1;
    if (fprintf(vh66_file,
            "{\\"kind\\":\\"GP0_MMIO\\",\\"tick\\":%llu,"
            "\\"frame\\":%u,\\"word\\":%u}\\n",
            (unsigned long long)vh66_tick++,vh66_frame,
            (unsigned int)word)<0)
        return vh66_fail();
    return 0;
}
int vh66_pcsx_gp1_observe(uint32_t word) {
    if (vh66_open()) return -1;
    /* All GP1 writes are recorded. The v65 consumer refuses anything
     * beyond GP1(00)/(01) or more than one before one DMA frame. */
    if (vh65_probe_gp1_write(vh66_file,vh66_tick++,vh66_frame,word))
        return vh66_fail();
    return 0;
}
/* v67: private, immutable per-submission 2 MiB RAM version. */
static int vh67_snapshot_frame(const unsigned char *ram,unsigned int frame) {
    const char *directory=getenv("VH_MAP02_V67_SNAPSHOT_DIR");
    if (!directory || !*directory) return 0;
    int dirfd=open(directory,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
    if(dirfd<0) return -1;
    struct stat info;
    if (fstat(dirfd,&info)!=0 || !S_ISDIR(info.st_mode) ||
        (info.st_mode&077)!=0 || info.st_uid!=geteuid()) {
        close(dirfd);return -1;
    }
    char filename[40];
    if(snprintf(filename,sizeof(filename),"frame-%06u.ram",frame)<=0) {
        close(dirfd);return -1;
    }
    int fd=openat(dirfd,filename,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);
    close(dirfd);
    if(fd<0)return -1;
    size_t remaining=VH66_RAM_BYTES;
    const unsigned char *cursor=ram;
    while(remaining>0) {
        ssize_t wrote=write(fd,cursor,remaining);
        if(wrote<=0) {
            close(fd);
            return -1;
        }
        remaining-=(size_t)wrote;
        cursor+=wrote;
    }
    if(close(fd)!=0)return -1;
    return 0;
}

int vh66_pcsx_dma2_observe(const unsigned char *ram,uint32_t head) {
    if (vh66_open()) return -1;
    if (!ram || (head&3) || head>=VH66_RAM_BYTES) return vh66_fail();
    /* Freeze pre-submit memory before later frames can mutate the same
     * addresses; snapshots are private by default and never published. */
    if(vh67_snapshot_frame(ram,vh66_frame))return vh66_fail();
    uint32_t words[VH66_MAX_WORDS];
    uint32_t seen[VH66_MAX_NODES];
    size_t nodes=0,count=0;
    uint32_t ptr=head;
    while (1) {
        if ((ptr&3) || ptr>=VH66_RAM_BYTES-3 || nodes>=VH66_MAX_NODES)
            return vh66_fail();
        for (size_t k=0;k<nodes;k++) if(seen[k]==ptr)return vh66_fail();
        seen[nodes++]=ptr;
        uint32_t tag=vh66_le32(ram+ptr);
        size_t n=(size_t)(tag>>24);
        uint32_t next=tag&0xffffffu;
        if (n>(VH66_RAM_BYTES-ptr-4)/4 || n>VH66_MAX_WORDS-count)
            return vh66_fail();
        for(size_t i=0;i<n;i++) words[count++]=vh66_le32(ram+ptr+4+4*i);
        /* This v65-compatible scope supports the explicit FFFFFF
         * terminator. Other valid hardware 0x8xxxxx terminators are
         * unsupported until the v60 strict parser also supports them.
         */
        if(next==0xffffffu)break;
        if(next>=VH66_RAM_BYTES)return vh66_fail();
        ptr=next;
    }
    if (!count || vh65_probe_dma2_submit(vh66_file,vh66_tick++,vh66_frame,
                                         head,words,count))
        return vh66_fail();
    vh66_frame++;
    return 0;
}
