#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "../source/scene_map_order.h"


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
    puts("Scene map order gate tests passed.");
    return 0;
}
