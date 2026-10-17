#include "vh81_event_jsonl.h"
#include "vh80_native_timeline.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>

int vh81_format_jsonl(char *output,size_t capacity) {
    unsigned int n=vh80_count(),prev=0,edges=0;
    size_t used=0;
    const vh80_event *events=vh80_events();
    if(!output || capacity==0 || vh80_dropped()!=0 || n==0 || n>4096u) return -1;
    output[0]='\0';
    for(unsigned int i=0;i<n;i++) {
        const vh80_event *e=&events[i];
        const char *kind;
        int written;
        if(e->sequence==0 || (i && (prev==UINT32_MAX || e->sequence!=prev+1))) return -1;
        prev=e->sequence;
        if(e->kind==VH80_VBLANK) { kind="vblank";edges++; }
        else if(e->kind==VH80_GP1_MMIO) kind="gp1_mmio";
        else if(e->kind==VH80_GPU_DMA2) kind="gpu_dma2_start";
        else return -1;
        if(used>=capacity) return -1;
        /* GPU DMA2 is an address, NOT an executed GP0 command. */
        written=snprintf(output+used,capacity-used,
          "{\"kind\":\"%s\",\"seq\":%u,\"value\":%u,\"cycle\":%u,\"frame\":%u}\n",
          kind,e->sequence,e->value,e->cycle,e->frame);
        if(written<0 || (size_t)written>=capacity-used) {
            output[0]='\0';
            return -1;
        }
        used+=(size_t)written;
    }
    if(edges<2 || used>INT_MAX) { output[0]='\0';return -1; }
    return (int)used;
}
