#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "../source/cd_scratch3_gate.h"

int main(void) {
    uint8_t *ram = calloc(VH_PS1_RAM_SIZE, 1);
    uint8_t scratch[VH_PS1_SCRATCH_SIZE] = {0};
    VhPs1MemoryView mem = {ram, VH_PS1_RAM_SIZE, scratch, sizeof scratch};
    VhMapUnitPhase phase;
    const uint8_t map_file[] = {4, 0, 0, 0, 0, 'M', 'A', 'P'};
    const uint32_t source_address = VH_MAP_INPUT_ADDR + UINT32_C(0x200);
    const uint64_t available = VH_PS1_RAM_SIZE -
                               (uint64_t)(VH_MAP_OUTPUT_ADDR - VH_PS1_RAM_BASE);
    VhMapDecodeStatus decode;
    size_t written = 0;
    uint8_t *source, *input, *output;
    assert(ram);
    source = vh_ps1_memory_span(&mem, source_address, VH_CD_USER_SECTOR_BYTES * 2);
    input = vh_ps1_memory_span(&mem, VH_MAP_INPUT_ADDR, sizeof map_file);
    output = vh_ps1_memory_span(&mem, VH_MAP_OUTPUT_ADDR, 4);
    assert(source && input && output);
    memset(source, 0x5a, VH_CD_USER_SECTOR_BYTES * 2);
    memcpy(input, map_file, sizeof map_file);
    vh_map_unit_phase_init(&phase, 2);
    assert(vh_map_unit_phase_reload(&phase, &mem, sizeof map_file, 32,
                                   &decode, &written) == VH_MAP_LOAD_OK);
    assert(vh_map_unit_phase_can_read_map(&phase));

    assert(vh_cd_scratch3_transfer(&phase, &mem, VH_MAP_OUTPUT_ADDR,
                                  source_address, 0)
           == VH_SCRATCH3_WRITE_INVALID_ARGUMENT);
    assert(vh_map_unit_phase_can_read_map(&phase));
    assert(vh_cd_scratch3_transfer(&phase, &mem, VH_MAP_OUTPUT_ADDR - 1,
                                  source_address, 1)
           == VH_SCRATCH3_WRITE_OUT_OF_RANGE);
    assert(vh_map_unit_phase_can_read_map(&phase));
    assert(vh_cd_scratch3_transfer(&phase, &mem, VH_MAP_OUTPUT_ADDR,
                                  UINT32_C(0xffffffff), 1)
           == VH_SCRATCH3_WRITE_OUT_OF_RANGE);
    assert(vh_map_unit_phase_can_read_map(&phase));
    assert(vh_cd_scratch3_transfer(&phase, &mem, VH_MAP_OUTPUT_ADDR,
                                  source_address, SIZE_MAX)
           == VH_SCRATCH3_WRITE_OUT_OF_RANGE);
    assert(vh_map_unit_phase_can_read_map(&phase));
    assert(memcmp(output, "MAP", 3) == 0);

    assert(vh_cd_scratch3_transfer(&phase, &mem, VH_MAP_OUTPUT_ADDR,
                                  source_address, 2)
           == VH_SCRATCH3_WRITE_OK);
    assert(!vh_map_unit_phase_can_read_map(&phase));
    assert(output[0] == 0x5a && output[3] == 0x5a);

    memcpy(input, map_file, sizeof map_file);
    assert(vh_map_unit_phase_reload(&phase, &mem, sizeof map_file, 32,
                                   &decode, &written) == VH_MAP_LOAD_OK);
    assert(vh_map_unit_phase_can_read_map(&phase));
    assert(vh_cd_scratch3_transfer(&phase, &mem,
               VH_MAP_OUTPUT_ADDR + VH_MAP_NORMAL_UNIT_OFFSET,
               source_address, 1) == VH_SCRATCH3_WRITE_OK);
    assert(vh_map_unit_phase_can_read_map(&phase));
    assert((uint64_t)VH_MAP_NORMAL_UNIT_OFFSET + VH_CD_USER_SECTOR_BYTES < available);

    /* Length measured in sectors; a transfer crossing mapped RAM is denied
     * without changing a previously valid map lease. */
    assert(vh_cd_scratch3_transfer(&phase, &mem,
               VH_MAP_OUTPUT_ADDR + (uint32_t)(available - 1024),
               source_address, 1) == VH_SCRATCH3_WRITE_OUT_OF_RANGE);
    assert(vh_map_unit_phase_can_read_map(&phase));
    /* Logical asset payload sizes differ from sector-aligned transfers.
     * Only independently verified bytes may be copied by this helper. */
    {
        const size_t payload_sizes[] = {1, 16, 2047, 2048, 2049, 4096};
        const size_t sector_counts[] = {1, 1, 1, 1, 2, 2};
        for (size_t i = 0; i < sizeof payload_sizes / sizeof payload_sizes[0]; ++i) {
            const size_t logical = payload_sizes[i];
            memcpy(input, map_file, sizeof map_file);
            assert(vh_map_unit_phase_reload(&phase, &mem, sizeof map_file,
                                            32, &decode, &written)
                   == VH_MAP_LOAD_OK);
            assert(vh_map_unit_phase_can_read_map(&phase));
            memset(source, 0x31 + (int)i, VH_CD_USER_SECTOR_BYTES * 2);
            assert(vh_cd_scratch3_payload_copy(&phase, &mem,
                        VH_MAP_OUTPUT_ADDR, source_address,
                        sector_counts[i], logical) == VH_SCRATCH3_WRITE_OK);
            assert(!vh_map_unit_phase_can_read_map(&phase));
            assert(output[0] == (uint8_t)(0x31 + i));

            memcpy(input, map_file, sizeof map_file);
            assert(vh_map_unit_phase_reload(&phase, &mem, sizeof map_file,
                                            32, &decode, &written)
                   == VH_MAP_LOAD_OK);
            assert(vh_cd_scratch3_payload_copy(&phase, &mem,
                        VH_MAP_OUTPUT_ADDR, source_address,
                        1, VH_CD_USER_SECTOR_BYTES + 1)
                   == VH_SCRATCH3_WRITE_OUT_OF_RANGE);
            assert(vh_map_unit_phase_can_read_map(&phase));
            assert(memcmp(output, "MAP", 3) == 0);
        }
        assert(vh_cd_scratch3_payload_copy(&phase, &mem,
                   VH_MAP_OUTPUT_ADDR, source_address, 1, 0)
               == VH_SCRATCH3_WRITE_INVALID_ARGUMENT);
        assert(vh_cd_scratch3_payload_copy(&phase, &mem,
                   VH_MAP_OUTPUT_ADDR, source_address, 0, 1)
               == VH_SCRATCH3_WRITE_INVALID_ARGUMENT);
        assert(vh_cd_scratch3_payload_copy(&phase, &mem,
                   VH_MAP_OUTPUT_ADDR, source_address, SIZE_MAX, 1)
               == VH_SCRATCH3_WRITE_OUT_OF_RANGE);
        assert(vh_cd_scratch3_payload_copy(&phase, &mem,
                   VH_MAP_OUTPUT_ADDR, UINT32_C(0xffffffff), 1, 1)
               == VH_SCRATCH3_WRITE_OUT_OF_RANGE);
        assert(vh_map_unit_phase_can_read_map(&phase));
    }

    free(ram);
    puts("CD scratch3 sector gate tests passed.");
    return 0;
}
