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

    /* Multi-resource staging in the real shared scratch3 view:
     * portraits -> texture data -> units -> map restoration.
     * No map consumer may read from this lease between conflicting writes.
     * This is deliberately synthetic; original loaders are not linked. */
    {
        const uint8_t portrait[] = {'P', 'O', 'R', 'T'};
        const uint8_t texture[] = {'T', 'E', 'X', '0'};
        const uint8_t unit[] = {'U', 'N', 'I', 'T'};
        const uint8_t broken[] = {3, 0, 0, 0, 0x02, 'X', 0x00};
        const uint8_t *resources[] = {portrait, texture, unit};

        vh_map_unit_phase_init(&phase, 2);
        memcpy(input, fixture, sizeof fixture);
        assert(vh_map_unit_phase_reload(&phase, &memory, sizeof fixture, 32,
                                       &decode, &written) == VH_MAP_LOAD_OK);
        assert(vh_map_unit_phase_can_read_map(&phase));
        for (size_t i = 0; i < sizeof resources / sizeof resources[0]; ++i) {
            assert(vh_scratch3_resource_write(&phase, &memory, 0,
                              resources[i], 4) == VH_SCRATCH3_WRITE_OK);
            assert(!vh_map_unit_phase_can_read_map(&phase));
            assert(memcmp(output, resources[i], 4) == 0);
            /* Rejected writes cannot silently restore the map lease. */
            assert(vh_scratch3_resource_write(&phase, &memory,
                                 span, resources[i], 4)
                   == VH_SCRATCH3_WRITE_OUT_OF_RANGE);
            assert(!vh_map_unit_phase_can_read_map(&phase));
            assert(memcmp(output, resources[i], 4) == 0);
        }
        memcpy(input, broken, sizeof broken);
        written = 999;
        assert(vh_map_unit_phase_reload(&phase, &memory, sizeof broken, 32,
                                       &decode, &written)
               == VH_MAP_LOAD_DECODE_FAILED);
        assert(decode == VH_MAP_DECODE_TRUNCATED && written == 0);
        assert(!vh_map_unit_phase_can_read_map(&phase));
        assert(memcmp(output, unit, 4) == 0);

        memcpy(input, fixture, sizeof fixture);
        assert(vh_map_unit_phase_reload(&phase, &memory, sizeof fixture, 32,
                                       &decode, &written) == VH_MAP_LOAD_OK);
        assert(vh_map_unit_phase_can_read_map(&phase));
        assert(written == 3 && memcmp(output, "MAP", 3) == 0);

        /* A subsequent texture write re-invalidates a restored map. */
        assert(vh_scratch3_resource_write(&phase, &memory, 0,
                           texture, sizeof texture) == VH_SCRATCH3_WRITE_OK);
        assert(!vh_map_unit_phase_can_read_map(&phase));
    }

    /* Variable offsets/sizes around the conservative unit-data boundary.
     * The first byte before the boundary can alias map data. The first
     * byte at/after it cannot invalidate this particular map view. */
    {
        const unsigned maps[] = {2, 39};
        const size_t lengths[] = {1, 2, 4, 16, 64, 256};
        uint8_t payload[256];
        for (size_t i = 0; i < sizeof payload; ++i)
            payload[i] = (uint8_t)(i ^ 0xa5u);
        for (size_t m = 0; m < sizeof maps / sizeof maps[0]; ++m) {
            size_t boundary = vh_map_capacity_before_units(maps[m]);
            for (size_t l = 0; l < sizeof lengths / sizeof lengths[0]; ++l) {
                size_t count = lengths[l];
                vh_map_unit_phase_init(&phase, maps[m]);
                memcpy(input, fixture, sizeof fixture);
                assert(vh_map_unit_phase_reload(&phase, &memory,
                            sizeof fixture, 32, &decode, &written)
                       == VH_MAP_LOAD_OK);
                assert(vh_scratch3_resource_write(&phase, &memory,
                            boundary, payload, count)
                       == VH_SCRATCH3_WRITE_OK);
                assert(vh_map_unit_phase_can_read_map(&phase));
                assert(memcmp(output, "MAP", 3) == 0);

                /* Overlaps the final byte of the conservative map range. */
                assert(vh_scratch3_resource_write(&phase, &memory,
                            boundary - 1, payload, count)
                       == VH_SCRATCH3_WRITE_OK);
                assert(!vh_map_unit_phase_can_read_map(&phase));

                /* A late rejected write must leave output untouched. */
                memcpy(input, fixture, sizeof fixture);
                assert(vh_map_unit_phase_reload(&phase, &memory,
                            sizeof fixture, 32, &decode, &written)
                       == VH_MAP_LOAD_OK);
                assert(vh_map_unit_phase_can_read_map(&phase));
                assert(vh_scratch3_resource_write(&phase, &memory,
                            span - count + 1, payload, count)
                       == VH_SCRATCH3_WRITE_OUT_OF_RANGE);
                assert(vh_map_unit_phase_can_read_map(&phase));
                assert(memcmp(output, "MAP", 3) == 0);
            }
        }
        /* An exact end-of-RAM write is legal; one additional byte is not. */
        assert(vh_scratch3_resource_write(&phase, &memory,
                    span - sizeof payload, payload, sizeof payload)
               == VH_SCRATCH3_WRITE_OK);
        assert(vh_map_unit_phase_can_read_map(&phase));
        assert(vh_scratch3_resource_write(&phase, &memory,
                    span - sizeof payload + 1, payload, sizeof payload)
               == VH_SCRATCH3_WRITE_OUT_OF_RANGE);
        assert(vh_map_unit_phase_can_read_map(&phase));
    }

    free(ram);
    puts("Scratch3 resource write tests passed.");
    return 0;
}
