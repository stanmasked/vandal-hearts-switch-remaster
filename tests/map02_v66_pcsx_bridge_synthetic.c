/* v66: synthetic invocation of REAL PCSX probe bridge implementation.
 * Not a running PCSX emulator. No proprietary media or retail bytes.
 */
#include "vh66_gpu_probe_bridge.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RAM_BYTES (2u*1024u*1024u)

static int parse_u32(const char *s,uint32_t *value) {
    char *end=NULL;
    unsigned long v=strtoul(s,&end,0);
    if(!s[0] || !end || *end || v>0xfffffffful)return -1;
    *value=(uint32_t)v;
    return 0;
}

int main(int argc,char **argv) {
    if(argc!=7) {
        fputs("usage: v66_bridge_test RAM BASE HEAD0 HEAD1 HEAD2 HEAD3\n",stderr);
        return 2;
    }
    uint32_t base,heads[4];
    if(parse_u32(argv[2],&base) || base>=RAM_BYTES)return 2;
    for(int i=0;i<4;i++)if(parse_u32(argv[3+i],&heads[i]))return 2;
    FILE *fp=fopen(argv[1],"rb");
    if(!fp)return 2;
    if(fseek(fp,0,SEEK_END)!=0){fclose(fp);return 2;}
    long len=ftell(fp);
    if(len<=0 || (size_t)len>RAM_BYTES-base){fclose(fp);return 2;}
    rewind(fp);
    unsigned char *ram=(unsigned char*)calloc(1,RAM_BYTES);
    if(!ram){fclose(fp);return 2;}
    if(fread(ram+base,1,(size_t)len,fp)!=(size_t)len) {
        free(ram);fclose(fp);return 2;
    }
    fclose(fp);
    for(unsigned i=0;i<4;i++) {
        if(i==2 && vh66_pcsx_gp1_observe(0))return 1;
        if(i==3 && vh66_pcsx_gp1_observe(0x01000000u))return 1;
        if(vh66_pcsx_dma2_observe(ram,heads[i]))return 1;
    }
    free(ram);
    return 0;
}
