#include <assert.h>
#include <stdio.h>
#include "../source/scene_map_order.h"

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
    puts("Scene map order gate tests passed.");
    return 0;
}
