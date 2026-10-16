/* v69 PCSX GPU plugin callback dispatch audit.
 * Intentionally logs callback *entry and return*, never GPU rasterisation.
 * Opt-in private 0600 callback log. No GPU source content or textures.
 */
#define _GNU_SOURCE 1
#include "plugins.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>

static GPUwriteData orig_word;
static GPUwriteDataMem orig_mem;
static GPUdmaChain orig_chain;
static GPUwriteStatus orig_status;
static FILE *trace_file;
static unsigned long long tick;

static void vh69_close(void) {
    if(trace_file) { fflush(trace_file); fclose(trace_file); trace_file=0; }
}
static int vh69_start(void) {
    if(trace_file)return 0;
    const char *path=getenv("VH_MAP02_V69_CALLBACK_LOG");
    if(!path || !path[0])return -1;
    int fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);
    if(fd<0)return -1;
    trace_file=fdopen(fd,"w");
    if(!trace_file){close(fd);return -1;}
    atexit(vh69_close);
    tick=1;
    return 0;
}
static void event(const char *api,const char *stage) {
    if(trace_file) {
        fprintf(trace_file,
            "{\"kind\":\"GPU_PLUGIN_CALLBACK\",\"seq\":%llu,"
            "\"api\":\"%s\",\"stage\":\"%s\"}\n",tick++,api,stage);
        fflush(trace_file);
    }
}
static void CALLBACK wrapped_writeData(uint32_t word) {
    event("writeData","enter");
    orig_word(word);
    event("writeData","return");
}
static void CALLBACK wrapped_writeDataMem(uint32_t *words,int count) {
    event("writeDataMem","enter");
    orig_mem(words,count);
    event("writeDataMem","return");
}
static void CALLBACK wrapped_writeStatus(uint32_t word) {
    event("writeStatus","enter");
    orig_status(word);
    event("writeStatus","return");
}
static long CALLBACK wrapped_dmaChain(uint32_t *ram,uint32_t addr,
                                     uint32_t *next,int32_t *last) {
    event("dmaChain","enter");
    long answer=orig_chain(ram,addr,next,last);
    event("dmaChain","return");
    return answer;
}
void vh69_gpu_wrap_loaded_plugin(void) {
    /* No file, no wrappers; default runtime behavior unchanged. */
    if(vh69_start()!=0)return;
    if(GPU_writeData==wrapped_writeData)return;
    if(!GPU_writeData||!GPU_writeDataMem||!GPU_writeStatus||!GPU_dmaChain)return;
    orig_word=GPU_writeData;
    orig_mem=GPU_writeDataMem;
    orig_status=GPU_writeStatus;
    orig_chain=GPU_dmaChain;
    GPU_writeData=wrapped_writeData;
    GPU_writeDataMem=wrapped_writeDataMem;
    GPU_writeStatus=wrapped_writeStatus;
    GPU_dmaChain=wrapped_dmaChain;
    event("bind","complete");
}
/* Independent synthetic harness may reset just these pointers. */
