#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "../source/map_buffer_gate.h"

int main(void) {
    uint8_t *ram = calloc(VH_PS1_RAM_SIZE, 1);
    uint8_t scratch[VH_PS1_SCRATCH_SIZE] = {0};
    VhPs1MemoryView memory = {ram, VH_PS1_RAM_SIZE, scratch, sizeof(scratch)};
    VhMapBuffers buffers;
    uint8_t *input;
    assert(ram != NULL);
    input = vh_ps1_memory_span(&memory, VH_MAP_INPUT_ADDR, 8);
    assert(input != NULL);
    input[0] = 4; input[1] = 0; input[2] = 0; input[3] = 0;
    input[4] = 0x11; input[5] = 0x22; input[6] = 0x33; input[7] = 0x44;

    assert(vh_map_buffers_prepare(&memory, 8, 64, &buffers));
    assert(buffers.compressed == input + 4);
    assert(buffers.compressed_length == 4);
    assert(buffers.output == ram + 0x180210);
    assert(buffers.output_capacity == 64);
    assert(buffers.output[0] == 0);
    assert(!vh_map_buffers_prepare(&memory, 7, 64, &buffers));
    assert(buffers.output == NULL && buffers.compressed == NULL);
    assert(!vh_map_buffers_prepare(&memory, 3, 64, &buffers));
    assert(!vh_map_buffers_prepare(&memory, 8, 0, &buffers));
    assert(!vh_map_buffers_prepare(&memory, 8, VH_PS1_RAM_SIZE, &buffers));
    assert(!vh_map_buffers_prepare(&memory, 8, 64, NULL));

    input[0] = 0xff; input[1] = 0xff; input[2] = 0xff; input[3] = 0xff;
    assert(!vh_map_buffers_prepare(&memory, 8, 64, &buffers));
    input[0] = 0; input[1] = 0; input[2] = 0; input[3] = 0;
    assert(!vh_map_buffers_prepare(&memory, 8, 64, &buffers));
    input[0] = 4;
    memory.ram_size = 0x140000;
    assert(!vh_map_buffers_prepare(&memory, 8, 64, &buffers));
    free(ram);
    puts("Map buffer preflight tests passed.");
    return 0;
}
