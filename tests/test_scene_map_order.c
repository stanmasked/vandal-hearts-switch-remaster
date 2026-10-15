#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "../source/scene_map_order.h"
#include "../source/scratch3_resource_write.h"


/* Exercise the actual checked map loader through the scene setup gate.
 * A flag alone is not sufficient proof of a successful reload. */
static void test_checked_setup_handoff(void) {
    uint8_t *ram = calloc(VH_PS1_RAM_SIZE, 1);
    uint8_t scratch[VH_PS1_SCRATCH_SIZE] = {0};
    VhPs1MemoryView memory = {ram, VH_PS1_RAM_SIZE, scratch, sizeof scratch};
    const uint8_t fixture[] = {4, 0, 0, 0, 0, 'M', 'A', 'P'};
    const uint8_t invalid[] = {3, 0, 0, 0, 0x02, 'X', 0x00};
    const unsigned scenes[] = {0, 39, 61, 88};
    VhMapDecodeStatus decode;
    VhMapLoadStatus status;
    VhMapUnitPhase phase;
    VhSceneMapOrder order;
    uint8_t *input, *output;
    size_t written = 999;

    assert(ram != NULL);
    input = vh_ps1_memory_span(&memory, VH_MAP_INPUT_ADDR, sizeof fixture);
    output = vh_ps1_memory_span(&memory, VH_MAP_OUTPUT_ADDR, 8);
    assert(input && output);

    for (size_t i = 0; i < sizeof scenes / sizeof scenes[0]; ++i) {
        unsigned scene = scenes[i];
        vh_map_unit_phase_init(&phase, scene);
        order = vh_scene_map_order(scene, VH_SCENE_STATE_4);
        assert(!vh_scene_map_ready_for_setup(&order, &phase));

        memcpy(input, fixture, sizeof fixture);
        status = vh_map_unit_phase_reload(&phase, &memory, sizeof fixture,
                                          32, &decode, &written);
        assert(status == VH_MAP_LOAD_OK && written == 3);
        assert(vh_scene_map_ready_for_setup(&order, &phase));

        /* Unit staging clobbers scratch3 map bytes and invalidates its view. */
        vh_map_unit_phase_stage_units(&phase);
        memcpy(output, "UNIT", 4);
        assert(!vh_scene_map_ready_for_setup(&order, &phase));

        /* A decode failure must not grant access to these stale unit bytes. */
        memcpy(input, invalid, sizeof invalid);
        written = 999;
        status = vh_map_unit_phase_reload(&phase, &memory, sizeof invalid,
                                          32, &decode, &written);
        assert(status == VH_MAP_LOAD_DECODE_FAILED);
        assert(decode == VH_MAP_DECODE_TRUNCATED && written == 0);
        assert(memcmp(output, "UNIT", 4) == 0);
        assert(!vh_scene_map_ready_for_setup(&order, &phase));

        /* Actual successful reload makes setup safe once again. */
        memcpy(input, fixture, sizeof fixture);
        status = vh_map_unit_phase_reload(&phase, &memory, sizeof fixture,
                                          32, &decode, &written);
        assert(status == VH_MAP_LOAD_OK && written == 3);
        assert(memcmp(output, "MAP", 3) == 0);
        assert(vh_scene_map_ready_for_setup(&order, &phase));
    }

    /* STATE_16 / ordinary scene omits a map reload: only a previously valid,
     * still-unmodified map can be handed off to SetupField. */
    order = vh_scene_map_order(0, VH_SCENE_STATE_16);
    vh_map_unit_phase_init(&phase, 0);
    assert(order.requires_existing_map);
    assert(!vh_scene_map_ready_for_setup(&order, &phase));
    memcpy(input, fixture, sizeof fixture);
    assert(vh_map_unit_phase_reload(&phase, &memory, sizeof fixture,
                                     32, &decode, &written) == VH_MAP_LOAD_OK);
    assert(vh_scene_map_ready_for_setup(&order, &phase));
    vh_map_unit_phase_stage_units(&phase);
    assert(!vh_scene_map_ready_for_setup(&order, &phase));

    free(ram);
}


/* Model the shared PS1 scratch3 lifecycle with address-validated copies
 * from scratch1, without using host-only raw resource pointers. This
 * checks the scene handoff contract, not upstream engine integration. */
static void test_addressed_resource_scene_handoff(void) {
    uint8_t *ram = calloc(VH_PS1_RAM_SIZE, 1);
    uint8_t scratch[VH_PS1_SCRATCH_SIZE] = {0};
    VhPs1MemoryView memory = {ram, VH_PS1_RAM_SIZE, scratch, sizeof scratch};
    const uint8_t fixture[] = {4, 0, 0, 0, 0, 'M', 'A', 'P'};
    const uint8_t invalid[] = {3, 0, 0, 0, 0x02, 'X', 0x00};
    const size_t sizes[] = {16, 64, 256};
    const unsigned scenes[] = {2, 39};
    const uint32_t resource_addr = VH_MAP_INPUT_ADDR + UINT32_C(0x100);
    uint8_t *input, *resource, *map;
    VhMapUnitPhase phase;
    VhSceneMapOrder order;
    VhMapDecodeStatus decode;
    size_t written = 999;
    assert(ram);
    input = vh_ps1_memory_span(&memory, VH_MAP_INPUT_ADDR, sizeof fixture);
    resource = vh_ps1_memory_span(&memory, resource_addr, 256);
    map = vh_ps1_memory_span(&memory, VH_MAP_OUTPUT_ADDR, 4);
    assert(input && resource && map);
    for (size_t m = 0; m < sizeof scenes / sizeof scenes[0]; ++m) {
        unsigned scene = scenes[m];
        vh_map_unit_phase_init(&phase, scene);
        order = vh_scene_map_order(scene, VH_SCENE_STATE_4);
        memcpy(input, fixture, sizeof fixture);
        assert(vh_map_unit_phase_reload(&phase, &memory, sizeof fixture, 32,
                                       &decode, &written) == VH_MAP_LOAD_OK);
        assert(vh_scene_map_ready_for_setup(&order, &phase));

        for (size_t k = 0; k < sizeof sizes / sizeof sizes[0]; ++k) {
            for (size_t j = 0; j < sizes[k]; ++j)
                resource[j] = (uint8_t)(j + k + 1);
            assert(vh_scratch3_resource_copy_ps1(&phase, &memory,
                       resource_addr, 0, sizes[k]) == VH_SCRATCH3_WRITE_OK);
            assert(!vh_scene_map_ready_for_setup(&order, &phase));
            assert(memcmp(map, resource, 4) == 0);
            /* Failed copy must preserve map-invalid state and resident bytes. */
            assert(vh_scratch3_resource_copy_ps1(&phase, &memory,
                       UINT32_C(0xffffffff), 0, sizes[k])
                   == VH_SCRATCH3_WRITE_OUT_OF_RANGE);
            assert(!vh_scene_map_ready_for_setup(&order, &phase));
            assert(memcmp(map, resource, 4) == 0);
        }
        memcpy(input, invalid, sizeof invalid);
        assert(vh_map_unit_phase_reload(&phase, &memory, sizeof invalid,
                                       32, &decode, &written)
               == VH_MAP_LOAD_DECODE_FAILED);
        assert(!vh_scene_map_ready_for_setup(&order, &phase));
        memcpy(input, fixture, sizeof fixture);
        assert(vh_map_unit_phase_reload(&phase, &memory, sizeof fixture,
                                       32, &decode, &written) == VH_MAP_LOAD_OK);
        assert(written == 3 && memcmp(map, "MAP", 3) == 0);
        assert(vh_scene_map_ready_for_setup(&order, &phase));
    }

    /* STATE_16 omits the general map reload. A later resource copy must
     * revoke its prior map view even though no scene loader is requested. */
    order = vh_scene_map_order(2, VH_SCENE_STATE_16);
    vh_map_unit_phase_init(&phase, 2);
    memcpy(input, fixture, sizeof fixture);
    assert(vh_map_unit_phase_reload(&phase, &memory, sizeof fixture,
                                   32, &decode, &written) == VH_MAP_LOAD_OK);
    assert(vh_scene_map_ready_for_setup(&order, &phase));
    assert(vh_scratch3_resource_copy_ps1(&phase, &memory,
               resource_addr, 0, 16) == VH_SCRATCH3_WRITE_OK);
    assert(!vh_scene_map_ready_for_setup(&order, &phase));
    free(ram);
}

int main(void) {
    VhMapUnitPhase phase;
    VhSceneMapOrder order;
    unsigned scenes[] = {0, 39, 61, 88};
    for (size_t i = 0; i < sizeof scenes / sizeof scenes[0]; ++i) {
        order = vh_scene_map_order(scenes[i], VH_SCENE_STATE_4);
        assert(order.stages_units && order.general_map_loads);
        assert(order.special_map_loads == (scenes[i] != 0));
        vh_map_unit_phase_init(&phase, scenes[i]);
        vh_map_unit_phase_stage_units(&phase);
        assert(!vh_scene_map_ready_for_setup(&order, &phase));
        /* Synthetic successful map load commits the phase. */
        phase.map_valid = 1;
        assert(vh_scene_map_ready_for_setup(&order, &phase));
    }
    order = vh_scene_map_order(0, VH_SCENE_STATE_25);
    assert(order.effective_primary == VH_SCENE_STATE_4);
    assert(order.stages_units && order.general_map_loads);

    order = vh_scene_map_order(0, VH_SCENE_STATE_16);
    assert(!order.stages_units && !order.special_map_loads);
    assert(!order.general_map_loads && order.requires_existing_map);
    vh_map_unit_phase_init(&phase, 0);
    assert(!vh_scene_map_ready_for_setup(&order, &phase));
    phase.map_valid = 1;
    assert(vh_scene_map_ready_for_setup(&order, &phase));

    order = vh_scene_map_order(39, VH_SCENE_STATE_16);
    assert(!order.stages_units && order.special_map_loads);
    assert(!order.general_map_loads && !order.requires_existing_map);
    vh_map_unit_phase_init(&phase, 39);
    assert(!vh_scene_map_ready_for_setup(&order, &phase));
    phase.map_valid = 1;
    assert(vh_scene_map_ready_for_setup(&order, &phase));

    assert(!vh_scene_map_ready_for_setup(NULL, &phase));
    assert(!vh_scene_map_ready_for_setup(&order, NULL));
    test_checked_setup_handoff();
    test_addressed_resource_scene_handoff();
    puts("Scene map order gate tests passed.");
    return 0;
}
