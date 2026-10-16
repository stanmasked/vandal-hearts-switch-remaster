/* v69 synthetic-only GPU plugin callback dispatch test.
 * Uses the ACTUAL adapter source, four fake callback functions, and an
 * isolated private event file; does not boot a PS1 game or draw pixels.
 */
#include "plugins.h"
#include "vh69_gpu_plugin_wrap.h"
#include <stdint.h>
#include <stdio.h>

GPUwriteData GPU_writeData;
GPUwriteDataMem GPU_writeDataMem;
GPUwriteStatus GPU_writeStatus;
GPUdmaChain GPU_dmaChain;

static unsigned int word_calls,mem_calls,status_calls,chain_calls;
static void CALLBACK fake_word(uint32_t word) {
    if(word==0xe6000003u)word_calls++;
}
static void CALLBACK fake_mem(uint32_t *words,int n) {
    if(words && n==2 && words[0]==0xe6000001u)mem_calls++;
}
static void CALLBACK fake_status(uint32_t word) {
    if(word==0x01000000u)status_calls++;
}
static long CALLBACK fake_chain(uint32_t *ram,uint32_t address,
                                uint32_t *next,int32_t *last) {
    if(ram && address==0x6000u && next && last) {
        chain_calls++;
        *next=0xffffffu;
        *last=4;
    }
    return 17;
}
int main(void) {
    uint32_t words[2]={0xe6000001u,0x12345678u};
    uint32_t addr=0; int32_t last=0;
    GPU_writeData=fake_word;
    GPU_writeDataMem=fake_mem;
    GPU_writeStatus=fake_status;
    GPU_dmaChain=fake_chain;
    vh69_gpu_wrap_loaded_plugin();
    GPU_writeData(0xe6000003u);
    GPU_writeDataMem(words,2);
    GPU_writeStatus(0x01000000u);
    long value=GPU_dmaChain(words,0x6000u,&addr,&last);
    if(value!=17 || addr!=0xffffffu || last!=4)return 1;
    if(word_calls!=1 || mem_calls!=1 || status_calls!=1 || chain_calls!=1)
        return 2;
    puts("PASS_V69_SYNTHETIC_PLUGIN_DISPATCH");
    return 0;
}
