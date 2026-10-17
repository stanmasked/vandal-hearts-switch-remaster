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
        else if(e->kind==VH83_GP0_UNAI_HANDLED) kind="gp0_unai_handled";
        else if(e->kind==VH84_UNAI_SAMPLE_DELTA) kind="unai_sample_delta";
        else if(e->kind==VH85_UNAI_STORE_COUNT) kind="unai_store_count";
        else if(e->kind==VH85_UNAI_SAME_STORE_COUNT) kind="unai_same_store_count";
        else if(e->kind==VH86_A0_STORES) kind="gpulib_a0_store_count";
        else if(e->kind==VH86_A0_SAME) kind="gpulib_a0_same_count";
        else if(e->kind==VH86_COPY_STORES) kind="gpulib_copy_store_count";
        else if(e->kind==VH86_COPY_SAME) kind="gpulib_copy_same_count";
        else if(e->kind==VH87_OVERLAP_STORES) kind="gpulib_overlap_store_count";
        else if(e->kind==VH87_OVERLAP_SAME) kind="gpulib_overlap_same_count";
        else if(e->kind==VH87_MASK_UPLOAD_STORES) kind="gpulib_mask_upload_store_count";
        else if(e->kind==VH87_MASK_UPLOAD_SAME) kind="gpulib_mask_upload_same_count";
        else if(e->kind==VH87_WRAP_STORES) kind="gpulib_wrap_store_count";
        else if(e->kind==VH87_WRAP_SAME) kind="gpulib_wrap_same_count";
        else if(e->kind==VH88_ASYNC_QUEUED) kind="async_dma_queued";
        else if(e->kind==VH88_ASYNC_COMPLETED) kind="async_dma_completed";
        else if(e->kind==VH88_ASYNC_STORES) kind="async_dma_store_count";
        else if(e->kind==VH88_ASYNC_SAME) kind="async_dma_same_count";
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
