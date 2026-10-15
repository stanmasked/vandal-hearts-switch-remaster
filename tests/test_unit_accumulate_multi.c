#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../source/unit_accumulate.h"

static void write32(uint8_t *p, uint32_t n) {
    p[0] = (uint8_t)n; p[1] = (uint8_t)(n >> 8);
    p[2] = (uint8_t)(n >> 16); p[3] = (uint8_t)(n >> 24);
}

/* Staging a new UNIT file replaces the scratch3 base, while previously
 * accumulated sheets remain at the offset selected for this map.
 * A new layout MUST be parsed for each file. All data here is synthetic. */
static void stage_one(uint8_t *base, size_t size, uint32_t copied,
                      char marker) {
    assert(size >= 24 && copied >= 4 && copied <= 12);
    memset(base, 0, size);
    base[2] = 1;
    write32(base + 4, 12);
    write32(base + 8, copied);
    memset(base + 12, marker, copied - 4);
}

static void run_scene(unsigned scene) {
    uint8_t *ram = calloc(VH_PS1_RAM_SIZE, 1);
    uint8_t scratch[VH_PS1_SCRATCH_SIZE] = {0};
    VhPs1MemoryView mem = {ram, VH_PS1_RAM_SIZE, scratch, sizeof scratch};
    VhUnitFileLayout layout;
    const size_t limit = 24;
    size_t cursor = 0;
    uint8_t *stage, *dest;
    size_t start = vh_map_capacity_before_units(scene);
    assert(ram);
    stage = vh_ps1_memory_span(&mem, VH_MAP_OUTPUT_ADDR, 32);
    dest = vh_ps1_memory_span(&mem,
             VH_MAP_OUTPUT_ADDR + (uint32_t)start, limit + 8);
    assert(stage && dest);
    memset(dest, 0xc7, limit + 8);

    stage_one(stage, 32, 8, 'A');
    assert(vh_unit_file_layout(stage, 32, &layout));
    assert(vh_unit_append_sheet(&mem, scene, &layout, 32, 0,
                                limit, &cursor) == VH_UNIT_APPEND_OK);
    assert(cursor == 8 && memcmp(dest + 4, "AAAA", 4) == 0);

    stage_one(stage, 32, 12, 'B');
    assert(vh_unit_file_layout(stage, 32, &layout));
    assert(vh_unit_append_sheet(&mem, scene, &layout, 32, 0,
                                limit, &cursor) == VH_UNIT_APPEND_OK);
    assert(cursor == 20 && memcmp(dest + 12, "BBBBBBBB", 8) == 0);

    /* Third file is individually well-formed, but cannot fit into the
     * remaining 4 bytes. Neither cursor nor previous sheets may change. */
    stage_one(stage, 32, 8, 'C');
    assert(vh_unit_file_layout(stage, 32, &layout));
    assert(vh_unit_append_sheet(&mem, scene, &layout, 32, 0,
                                limit, &cursor) == VH_UNIT_APPEND_OUT_OF_RANGE);
    assert(cursor == 20);
    assert(memcmp(dest + 4, "AAAA", 4) == 0);
    assert(memcmp(dest + 12, "BBBBBBBB", 8) == 0);
    assert(dest[20] == 0xc7 && dest[limit] == 0xc7);

    /* Different-file success can fill exactly the remaining capacity. */
    stage_one(stage, 32, 4, 'D');
    assert(vh_unit_file_layout(stage, 32, &layout));
    assert(vh_unit_append_sheet(&mem, scene, &layout, 32, 0,
                                limit, &cursor) == VH_UNIT_APPEND_OK);
    assert(cursor == limit && dest[limit] == 0xc7);
    assert(memcmp(dest + 4, "AAAA", 4) == 0);
    assert(memcmp(dest + 12, "BBBBBBBB", 8) == 0);
    /* The preceding accumulator is not erased by staging new files. */

    /* Even a valid fourth source cannot append beyond this capacity. */
    stage_one(stage, 32, 8, 'E');
    assert(vh_unit_file_layout(stage, 32, &layout));
    assert(vh_unit_append_sheet(&mem, scene, &layout, 32, 0,
                                limit, &cursor) == VH_UNIT_APPEND_OUT_OF_RANGE);
    assert(cursor == limit && dest[limit] == 0xc7);
    free(ram);
}

int main(void) {
    run_scene(2);
    run_scene(39);
    puts("Multi-file unit accumulation tests passed.");
    return 0;
}
