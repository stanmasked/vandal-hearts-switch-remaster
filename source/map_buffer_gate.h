#ifndef VH_MAP_BUFFER_GATE_H
#define VH_MAP_BUFFER_GATE_H

/*
 * Preliminary boundary for a future map decompressor integration.
 * Only validates memory ownership and the four-byte little-endian input
 * length header. The original decompressor has no output-capacity argument:
 * this gate MUST NOT be treated as proof its writes are bounded.
 */
#include <stddef.h>
#include <stdint.h>
#include "ps1_memory_view.h"

#define VH_MAP_INPUT_ADDR UINT32_C(0x801317c0)
#define VH_MAP_OUTPUT_ADDR UINT32_C(0x80180210)
/* Address distance is NOT a proven game-file size or decoded capacity. */
#define VH_MAP_INPUT_OUTPUT_GAP ((size_t)(VH_MAP_OUTPUT_ADDR - VH_MAP_INPUT_ADDR))

typedef struct VhMapBuffers {
    const uint8_t *compressed;
    size_t compressed_length;
    uint8_t *output;
    size_t output_capacity;
} VhMapBuffers;

/* Caller must supply a verified output limit, never inferred from a PS1
 * address offset. No output bytes are written by this function. */
static inline int vh_map_buffers_prepare(const VhPs1MemoryView *mem,
                                         size_t input_available,
                                         size_t output_capacity,
                                         VhMapBuffers *result) {
    uint8_t *prefix;
    uint32_t declared;
    uint8_t *input;
    uint8_t *output;

    if (result == NULL) return 0;
    result->compressed = NULL;
    result->compressed_length = 0;
    result->output = NULL;
    result->output_capacity = 0;
    if (input_available < 4 || output_capacity == 0) return 0;

    prefix = vh_ps1_memory_span(mem, VH_MAP_INPUT_ADDR, 4);
    if (prefix == NULL) return 0;
    declared = (uint32_t)prefix[0] |
               ((uint32_t)prefix[1] << 8) |
               ((uint32_t)prefix[2] << 16) |
               ((uint32_t)prefix[3] << 24);
    /* Upstream takes signed s32 len, so reject unrepresentable lengths. */
    if (declared == 0 || declared > INT32_MAX ||
        (size_t)declared > input_available - 4) return 0;
    /* Conservative integration contract: the four-byte header plus input
     * payload must end before output begins. The upstream game may reuse
     * memory over time; this standalone adapter forbids live overlap. */
    if ((size_t)declared > VH_MAP_INPUT_OUTPUT_GAP - 4) return 0;
    input = vh_ps1_memory_span(mem, VH_MAP_INPUT_ADDR + 4, declared);
    output = vh_ps1_memory_span(mem, VH_MAP_OUTPUT_ADDR, output_capacity);
    if (input == NULL || output == NULL) return 0;
    result->compressed = input;
    result->compressed_length = declared;
    result->output = output;
    result->output_capacity = output_capacity;
    return 1;
}

#endif
