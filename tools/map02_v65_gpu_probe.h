/* v65 PS1 GPU observation hook protocol — C11 reference producer.
 *
 * This header only formats event lines. Integrate its calls at an
 * instrumented emulator's actual GP1 MMIO-write and GP0 DMA-submit
 * hooks, passing the *actual submitted ordered GP0 words*.
 * A call from test code is NOT evidence of a real PS1 capture.
 *
 * Do NOT log proprietary gameplay from an emulator into public CI.
 */
#ifndef VH_MAP02_V65_GPU_PROBE_H
#define VH_MAP02_V65_GPU_PROBE_H
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

static int vh65_probe_begin(FILE *out, const char *source_class) {
    if (!out || !source_class) return -1;
    if (strcmp(source_class, "synthetic") != 0 &&
        strcmp(source_class, "user-supplied-unverified") != 0) return -1;
    return fprintf(out,
        "{\"kind\":\"CAPTURE_BEGIN\",\"schema\":\"map02-v65-local-gpu-probe-jsonl-v1\","
        "\"source_class\":\"%s\",\"clock\":\"producer-monotonic-counter\","
        "\"initial_state\":\"power-on-assumed\"}\n",source_class)<0 ? -1 : 0;
}

static int vh65_probe_gp1_write(FILE *out, uint64_t tick, unsigned int before_frame,
                                uint32_t word) {
    if (!out) return -1;
    return fprintf(out,
        "{\"kind\":\"GP1_WRITE\",\"tick\":%llu,\"before_frame\":%u,\"word\":%u}\n",
        (unsigned long long)tick,before_frame,(unsigned int)word)<0 ? -1 : 0;
}

static int vh65_probe_dma2_submit(FILE *out, uint64_t tick, unsigned int frame,
                                  uint32_t head, const uint32_t *words,size_t count) {
    if (!out || !words || count==0 || count>65536u) return -1;
    if (fprintf(out,
        "{\"kind\":\"GP0_DMA2\",\"tick\":%llu,\"frame\":%u,"
        "\"head\":%u,\"words\":[",
        (unsigned long long)tick,frame,(unsigned int)head)<0) return -1;
    for (size_t i=0;i<count;i++) {
        if (fprintf(out,"%s%u",i ? "," : "",(unsigned int)words[i])<0)
            return -1;
    }
    return fputs("]}\n",out)==EOF ? -1 : 0;
}
#endif
