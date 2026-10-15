#ifndef VH_SCENE_MAP_ORDER_H
#define VH_SCENE_MAP_ORDER_H

/* Synthetic interpretation of State_EventScene secondary==4 from pinned
 * src/core/main.c lines 368-434. No real game transition is intercepted.
 * STATE_25 is converted into STATE_4 before the unit loading check.
 */
#include <stddef.h>
#include "map_unit_phase.h"

enum {
    VH_SCENE_STATE_4 = 4,
    VH_SCENE_STATE_16 = 16,
    VH_SCENE_STATE_25 = 25
};

typedef struct VhSceneMapOrder {
    unsigned effective_primary;
    unsigned stages_units;
    unsigned special_map_loads;
    unsigned general_map_loads;
    unsigned requires_existing_map;
} VhSceneMapOrder;

static inline VhSceneMapOrder vh_scene_map_order(unsigned scene,
                                                 unsigned primary) {
    VhSceneMapOrder result;
    result.effective_primary = primary == VH_SCENE_STATE_25
        ? VH_SCENE_STATE_4 : primary;
    result.stages_units = result.effective_primary == VH_SCENE_STATE_4;
    result.special_map_loads = scene == 39 || scene == 61 || scene == 88;
    result.general_map_loads = result.effective_primary != VH_SCENE_STATE_16;
    result.requires_existing_map =
        !result.special_map_loads && !result.general_map_loads;
    return result;
}

/* Guard only the handoff from scene setup to the map consumer. Callers must
 * explicitly stage units and successfully reload map data in source order. */
static inline int vh_scene_map_ready_for_setup(
    const VhSceneMapOrder *order, const VhMapUnitPhase *phase) {
    return order && phase && vh_map_unit_phase_can_read_map(phase);
}

#endif
