#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "../source/unit_accumulate.h"

static void put32(uint8_t *p, uint32_t n) {
    p[0] = (uint8_t)n; p[1] = (uint8_t)(n >> 8);
    p[2] = (uint8_t)(n >> 16); p[3] = (uint8_t)(n >> 24);
}

int main(void) {
    uint8_t *ram = calloc(VH_PS1_RAM_SIZE, 1);
    uint8_t scratch[VH_PS1_SCRATCH_SIZE] = {0};
    VhPs1MemoryView memory = {ram, VH_PS1_RAM_SIZE, scratch, sizeof scratch};
    VhUnitFileLayout layout;
    uint8_t *file, *normal, *special;
    size_t cursor = 0;
    assert(ram);
    file = vh_ps1_memory_span(&memory, VH_MAP_OUTPUT_ADDR, 64);
    normal = vh_ps1_memory_span(&memory,
                    VH_MAP_OUTPUT_ADDR + (uint32_t)VH_MAP_NORMAL_UNIT_OFFSET, 40);
    special = vh_ps1_memory_span(&memory,
                    VH_MAP_OUTPUT_ADDR + (uint32_t)VH_MAP_39_UNIT_OFFSET, 40);
    assert(file && normal && special);

    memset(file, 0, 64);
    file[2] = 2; /* first sheet is 8 bytes, second is 12 */
    put32(file + 4, 8);
    put32(file + 8, 12);
    put32(file + 12, 8);
    memcpy(file + 16, "ABCD", 4);
    put32(file + 20, 8); /* inner size smaller than outer span */
    memcpy(file + 24, "EFGH", 4);
    assert(vh_unit_file_layout(file, 32, &layout));
    memset(normal, 0x7b, 40);

    assert(vh_unit_append_sheet(&memory, 2, &layout, 32, 0, 16, &cursor)
           == VH_UNIT_APPEND_OK);
    assert(cursor == 8);
    assert(memcmp(normal, file + 12, 8) == 0);
    assert(normal[8] == 0x7b);

    /* Appending sheet one would copy eight bytes; reject one byte short
     * without mutating cursor or the destination at its current end. */
    assert(vh_unit_append_sheet(&memory, 2, &layout, 32, 1, 15, &cursor)
           == VH_UNIT_APPEND_OUT_OF_RANGE);
    assert(cursor == 8 && normal[8] == 0x7b);
    assert(vh_unit_append_sheet(&memory, 2, &layout, 32, 1, 16, &cursor)
           == VH_UNIT_APPEND_OK);
    assert(cursor == 16);
    assert(memcmp(normal + 8, file + 20, 8) == 0);
    assert(normal[16] == 0x7b);

    assert(vh_unit_append_sheet(&memory, 2, &layout, 32, 0, 16, &cursor)
           == VH_UNIT_APPEND_OUT_OF_RANGE);
    assert(cursor == 16);
    assert(vh_unit_append_sheet(&memory, 2, &layout, 32, 2, 40, &cursor)
           == VH_UNIT_APPEND_INVALID_ARGUMENT);
    assert(vh_unit_append_sheet(NULL, 2, &layout, 32, 0, 40, &cursor)
           == VH_UNIT_APPEND_INVALID_ARGUMENT);
    assert(vh_unit_append_sheet(&memory, 2, &layout, 32, 0, 40, NULL)
           == VH_UNIT_APPEND_INVALID_ARGUMENT);

    /* Tampering with staging data after parsing must be detected at copy
     * time, even when its original layout was accepted. */
    cursor = 0;
    put32(file + 12, 16);
    assert(vh_unit_append_sheet(&memory, 2, &layout, 32, 0, 40, &cursor)
           == VH_UNIT_APPEND_INVALID_SHEET);
    assert(cursor == 0);
    put32(file + 12, 8);
    assert(vh_unit_append_sheet(&memory, 2, &layout, 19, 0, 40, &cursor)
           == VH_UNIT_APPEND_INVALID_SHEET);
    assert(cursor == 0);

    /* Scene 39 accumulates at a different scratch3 offset. */
    memset(special, 0x2a, 40);
    assert(vh_unit_append_sheet(&memory, 39, &layout, 32, 0, 40, &cursor)
           == VH_UNIT_APPEND_OK);
    assert(cursor == 8 && memcmp(special, file + 12, 8) == 0);
    assert(normal[0] == 8); /* normal-map accumulation is undisturbed */
    assert(special[8] == 0x2a);

    /* A too-short backing memory view rejects copy without modifying the
     * published accumulation cursor or previously copied bytes. */
    memory.ram_size = (size_t)(VH_MAP_OUTPUT_ADDR - VH_PS1_RAM_BASE) +
                      VH_MAP_39_UNIT_OFFSET + 7;
    assert(vh_unit_append_sheet(&memory, 39, &layout, 32, 0, 40, &cursor)
           == VH_UNIT_APPEND_OUT_OF_RANGE);
    assert(cursor == 8 && special[8] == 0x2a);
    free(ram);
    puts("Unit accumulation gate tests passed.");
    return 0;
}
