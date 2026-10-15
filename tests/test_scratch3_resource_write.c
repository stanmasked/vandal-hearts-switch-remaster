#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../source/scratch3_resource_write.h"

int main(void) {
    uint8_t *ram = calloc(VH_PS1_RAM_SIZE, 1);
    uint8_t scratch[VH_PS1_SCRATCH_SIZE] = {0};
    VhPs1MemoryView memory = {ram, VH_PS1_RAM_SIZE, scratch, sizeof scratch};
    const uint8_t fixture[] = {4, 0, 0, 0, 0, 'M', 'A', 'P'};
    const uint8_t resource[] = {'I', 'T', 'E', 'M'};
    VhMapUnitPhase phase;
    VhMapDecodeStatus decode;
    size_t written = 0;
    uint8_t *input, *output;
    const size_t span = VH_PS1_RAM_SIZE -
                 (size_t)(VH_MAP_OUTPUT_ADDR - VH_PS1_RAM_BASE);
    assert(ram);
    input = vh_ps1_memory_span(&memory, VH_MAP_INPUT_ADDR, sizeof fixture);
    output = vh_ps1_memory_span(&memory, VH_MAP_OUTPUT_ADDR, 8);
    assert(input && output);
    memcpy(input, fixture, sizeof fixture);
    vh_map_unit_phase_init(&phase, 2);
    assert(vh_map_unit_phase_reload(&phase, &memory, sizeof fixture, 32,
                                   &decode, &written) == VH_MAP_LOAD_OK);
    assert(vh_map_unit_phase_can_read_map(&phase));

    assert(vh_scratch3_resource_write(&phase, &memory, 0, NULL, 4)
           == VH_SCRATCH3_WRITE_INVALID_ARGUMENT);
    assert(vh_map_unit_phase_can_read_map(&phase));
    assert(memcmp(output, "MAP", 3) == 0);
    assert(vh_scratch3_resource_write(&phase, &memory, span, resource, 1)
           == VH_SCRATCH3_WRITE_OUT_OF_RANGE);
    assert(vh_map_unit_phase_can_read_map(&phase));
    assert(vh_scratch3_resource_write(&phase, &memory, SIZE_MAX, resource, 4)
           == VH_SCRATCH3_WRITE_OUT_OF_RANGE);
    assert(vh_map_unit_phase_can_read_map(&phase));

    assert(vh_scratch3_resource_write(&phase, &memory, 0, NULL, 0)
           == VH_SCRATCH3_WRITE_OK);
    assert(vh_map_unit_phase_can_read_map(&phase));
    assert(vh_scratch3_resource_write(&phase, &memory,
                       VH_MAP_NORMAL_UNIT_OFFSET, resource, sizeof resource)
           == VH_SCRATCH3_WRITE_OK);
    assert(vh_map_unit_phase_can_read_map(&phase));
    assert(vh_scratch3_resource_write(&phase, &memory, 0,
                                      resource, sizeof resource)
           == VH_SCRATCH3_WRITE_OK);
    assert(!vh_map_unit_phase_can_read_map(&phase));
    assert(memcmp(output, resource, sizeof resource) == 0);

    /* The failed write leaves an already invalid map invalid; only a
     * successful checked reload may restore the map consumer's lease. */
    assert(vh_scratch3_resource_write(&phase, &memory, span, resource, 2)
           == VH_SCRATCH3_WRITE_OUT_OF_RANGE);
    assert(!vh_map_unit_phase_can_read_map(&phase));
    assert(vh_map_unit_phase_reload(&phase, &memory, sizeof fixture, 32,
                                   &decode, &written) == VH_MAP_LOAD_OK);
    assert(memcmp(output, "MAP", 3) == 0);
    assert(vh_map_unit_phase_can_read_map(&phase));

    vh_map_unit_phase_init(&phase, 39);
    assert(vh_map_unit_phase_reload(&phase, &memory, sizeof fixture, 32,
                                   &decode, &written) == VH_MAP_LOAD_OK);
    assert(vh_scratch3_resource_write(&phase, &memory,
                         VH_MAP_NORMAL_UNIT_OFFSET, resource, sizeof resource)
           == VH_SCRATCH3_WRITE_OK);
    assert(!vh_map_unit_phase_can_read_map(&phase));
    assert(vh_map_unit_phase_reload(&phase, &memory, sizeof fixture, 32,
                                   &decode, &written) == VH_MAP_LOAD_OK);
    assert(vh_scratch3_resource_write(&phase, &memory,
                         VH_MAP_39_UNIT_OFFSET, resource, sizeof resource)
           == VH_SCRATCH3_WRITE_OK);
    assert(vh_map_unit_phase_can_read_map(&phase));

    memory.ram_size = VH_MAP_OUTPUT_ADDR - VH_PS1_RAM_BASE;
    assert(vh_scratch3_resource_write(&phase, &memory, 0, resource, 1)
           == VH_SCRATCH3_WRITE_OUT_OF_RANGE);
    assert(vh_map_unit_phase_can_read_map(&phase));
    /* A synthetic resource can be copied within the same scratch3 area.
     * The overlapping ranges exercise memmove rather than unsafe memcpy. */
    memory.ram_size = VH_PS1_RAM_SIZE;
    memcpy(output, "ABCDEFGH", 8);
    assert(vh_map_unit_phase_reload(&phase, &memory, sizeof fixture, 32,
                                   &decode, &written) == VH_MAP_LOAD_OK);
    memcpy(output, "ABCDEFGH", 8);
    assert(vh_scratch3_resource_write(&phase, &memory, 2, output, 6)
           == VH_SCRATCH3_WRITE_OK);
    assert(memcmp(output, "ABABCDEF", 8) == 0);
    assert(!vh_map_unit_phase_can_read_map(&phase));

    free(ram);
    puts("Scratch3 resource write tests passed.");
    return 0;
}
