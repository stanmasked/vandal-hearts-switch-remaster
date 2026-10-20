#ifndef VH_MAP02_ROSTER8_VARIANTS_H
#define VH_MAP02_ROSTER8_VARIANTS_H

/*
 * Independent, asset-free Switch 4x4 / 3x3 / 1x4 tactical demonstrations.
 * 4x4 remains the default for all previously proved NeXium routes.
 * Neither approved authored legacy map is modified.
 */
#include "map02_battle8.h"
#include "map02_roster8_smoke_data.h"
#include "map02_roster8_second_data.h"

enum { VH_R8_VARIANTS = 3, VH_R8_SCENES = 2 };

static inline const char *vh_r8_variant_label(int variant) {
    switch (variant) {
    case 0: return "ROSTER 4 VS 4";
    case 1: return "ROSTER 3 VS 3";
    case 2: return "ROSTER 1 VS 4";
    default: return "INVALID ROSTER";
    }
}

/* Each scene and capacity combination is an independently reset state.
 * Invalid scene/variant selection never changes an existing battle. */
static inline int vh_r8_scene_variant(VhRoster8 *out, int scene, int variant) {
    VhRoster8 stage;
    if (scene < 0 || scene >= VH_R8_SCENES) return 0;
    stage = scene == 0 ? VH_MAP02_ROSTER8_SMOKE : VH_MAP02_ROSTER8_SECOND;
    const VhBattleUnit empty = {0, 0, 0, 0};
    int i;
    if (!out || variant < 0 || variant >= VH_R8_VARIANTS)
        return 0;
    if (variant == 1) {
        stage.ally_count = 3;
        stage.enemy_count = 3;
        stage.units[3] = empty;
        stage.units[7] = empty;
    } else if (variant == 2) {
        stage.ally_count = 1;
        for (i = 1; i < VH_R8_SIDE_CAP; ++i)
            stage.units[i] = empty;
    }
    if (!vh_r8_valid(&stage)) return 0;
    *out = stage;
    return 1;
}

static inline int vh_r8_variant(VhRoster8 *out, int variant) {
    return vh_r8_scene_variant(out, 0, variant);
}

static inline int vh_b8_init_scene_variant(VhBattle8 *out,
                                           int scene, int variant) {
    VhRoster8 stage;
    if (!out || !vh_r8_scene_variant(&stage, scene, variant)) return 0;
    return vh_b8_init(out, &stage, 2, 2);
}

static inline int vh_b8_init_variant(VhBattle8 *out, int variant) {
    return vh_b8_init_scene_variant(out, 0, variant);
}

#endif /* VH_MAP02_ROSTER8_VARIANTS_H */
