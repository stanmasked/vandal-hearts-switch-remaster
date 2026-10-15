#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "../source/map_unit_phase.h"

int main(void) {
    uint8_t *ram = calloc(VH_PS1_RAM_SIZE, 1);
    uint8_t scratch[VH_PS1_SCRATCH_SIZE] = {0};
    VhPs1MemoryView memory = {ram, VH_PS1_RAM_SIZE, scratch, sizeof scratch};
    const uint8_t map_fixture[] = {4, 0, 0, 0, 0, 'M', 'A', 'P'};
    uint8_t *input, *map;
    VhMapUnitPhase phase;
    VhMapDecodeStatus decode;
    size_t written = 999;
    assert(ram != NULL);
    input = vh_ps1_memory_span(&memory, VH_MAP_INPUT_ADDR, sizeof map_fixture);
    map = vh_ps1_memory_span(&memory, VH_MAP_OUTPUT_ADDR, 4);
    assert(input && map);
    memcpy(input, map_fixture, sizeof map_fixture);
    vh_map_unit_phase_init(&phase, 2);
    assert(!vh_map_unit_phase_can_read_map(&phase));
    assert(vh_map_unit_phase_reload(&phase, &memory, sizeof map_fixture,
                                   32, &decode, &written) == VH_MAP_LOAD_OK);
    assert(written == 3 && vh_map_unit_phase_can_read_map(&phase));
    assert(memcmp(map, "MAP", 3) == 0);

    /* An actual unit loader would write its file into this same scratch3
     * allocation; this test mimics only the overwrite and phase transition. */
    vh_map_unit_phase_stage_units(&phase);
    memcpy(map, "UNIT", 4);
    assert(!vh_map_unit_phase_can_read_map(&phase));

    input[0] = 0xff; input[1] = 0xff; input[2] = 0xff; input[3] = 0xff;
    assert(vh_map_unit_phase_reload(&phase, &memory, sizeof map_fixture,
                                   32, &decode, &written)
           == VH_MAP_LOAD_PREFLIGHT_FAILED);
    assert(!vh_map_unit_phase_can_read_map(&phase));
    assert(memcmp(map, "UNIT", 4) == 0);

    memcpy(input, map_fixture, sizeof map_fixture);
    assert(vh_map_unit_phase_reload(&phase, &memory, sizeof map_fixture,
                                   32, &decode, &written) == VH_MAP_LOAD_OK);
    assert(vh_map_unit_phase_can_read_map(&phase));
    assert(memcmp(map, "MAP", 3) == 0);
    assert(map[3] == 'T'); /* Successful map reload writes only 3 bytes. */

    vh_map_unit_phase_init(&phase, 39);
    assert(phase.map_number == 39 && !vh_map_unit_phase_can_read_map(&phase));
    assert(vh_map_unit_phase_reload(&phase, &memory, sizeof map_fixture,
                                   VH_MAP_39_UNIT_OFFSET, &decode, &written)
           == VH_MAP_LOAD_OK);
    assert(vh_map_unit_phase_can_read_map(&phase));
    vh_map_unit_phase_stage_units(&phase);
    assert(!vh_map_unit_phase_can_read_map(&phase));
    free(ram);
    puts("Map/unit shared scratch phase tests passed.");
    return 0;
}
