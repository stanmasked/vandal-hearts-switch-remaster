#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../source/map_unit_boundary.h"

int main(void) {
    uint8_t *ram = calloc(VH_PS1_RAM_SIZE, 1);
    uint8_t scratch[VH_PS1_SCRATCH_SIZE] = {0};
    VhPs1MemoryView memory = {ram, VH_PS1_RAM_SIZE, scratch, sizeof scratch};
    VhMapDecodeStatus decode;
    VhMapLoadStatus result;
    size_t written;
    const uint8_t fixture[] = {4, 0, 0, 0, 0, 'M', 'A', 'P'};
    uint8_t *input, *output;
    assert(ram != NULL);
    input = vh_ps1_memory_span(&memory, VH_MAP_INPUT_ADDR, sizeof fixture);
    output = vh_ps1_memory_span(&memory, VH_MAP_OUTPUT_ADDR,
                                VH_MAP_39_UNIT_OFFSET + 1);
    assert(input && output);
    assert(vh_map_capacity_before_units(0) == 0x2db80u);
    assert(vh_map_capacity_before_units(39) == 0x3a300u);
    assert(vh_map_capacity_before_units(40) == 0x2db80u);
    memcpy(input, fixture, sizeof fixture);

    for (unsigned map = 0; map <= 40; ++map) {
        size_t limit = vh_map_capacity_before_units(map);
        memset(output, 0x5a, VH_MAP_39_UNIT_OFFSET + 1);
        result = vh_map_load_before_units(&memory, map, sizeof fixture,
                                          limit, &decode, &written);
        assert(result == VH_MAP_LOAD_OK && decode == VH_MAP_DECODE_OK);
        assert(written == 3 && memcmp(output, "MAP", 3) == 0);
        assert(output[limit] == 0x5a);

        memset(output, 0x5a, VH_MAP_39_UNIT_OFFSET + 1);
        result = vh_map_load_before_units(&memory, map, sizeof fixture,
                                          limit + 1, &decode, &written);
        assert(result == VH_MAP_LOAD_PREFLIGHT_FAILED);
        assert(decode == VH_MAP_DECODE_INVALID_ARGUMENT && written == 0);
        assert(output[0] == 0x5a && output[limit] == 0x5a);
    }

    /* Normal maps refuse the larger map 39 capacity. */
    result = vh_map_load_before_units(&memory, 1, sizeof fixture,
                    VH_MAP_39_UNIT_OFFSET, &decode, &written);
    assert(result == VH_MAP_LOAD_PREFLIGHT_FAILED && written == 0);
    result = vh_map_load_before_units(&memory, 39, sizeof fixture,
                    0, &decode, &written);
    assert(result == VH_MAP_LOAD_PREFLIGHT_FAILED && written == 0);
    free(ram);
    puts("Conservative map/unit memory boundary tests passed.");
    return 0;
}
