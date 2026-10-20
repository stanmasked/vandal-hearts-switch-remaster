#ifndef VH_MAP02_ROSTER8_VARIANTS_H
#define VH_MAP02_ROSTER8_VARIANTS_H

/*
 * Independent, asset-free Switch 4x4 / 3x3 / 1x4 tactical demonstrations.
 * 4x4 remains the default for all previously proved NeXium routes.
 * Neither approved authored legacy map is modified.
 */
#include "map02_battle8.h"
#include "map02_roster8_smoke_data.h"

enum { VH_R8_VARIANTS = 3 };

static inline const char *vh_r8_variant_label(int variant) {
    switch (variant) {
    case 0: return "ROSTER 4 VS 4";
    case 1: return "ROSTER 3 VS 3";
    case 2: return "ROSTER 1 VS 4";
    default: return "INVALID ROSTER";
    }
}

/* Produce a fresh validated roster, never mutating the destination on
 * invalid input. Clear absent actors entirely to prevent ghost slots. */
static inline int vh_r8_variant(VhRoster8 *out, int variant) {
    VhRoster8 stage = VH_MAP02_ROSTER8_SMOKE;
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

static inline int vh_b8_init_variant(VhBattle8 *out, int variant) {
    VhRoster8 stage;
    if (!out || !vh_r8_variant(&stage, variant)) return 0;
    return vh_b8_init(out, &stage, 2, 2);
}

#endif /* VH_MAP02_ROSTER8_VARIANTS_H */
