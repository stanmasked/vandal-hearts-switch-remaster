#ifndef VH_MAP02_RANGED8_H
#define VH_MAP02_RANGED8_H

/*
 * Optional original-data-free archer action for expanded second arena only.
 * Native caller must gate this command by scene == 1. The legacy MAP02
 * engine and ordinary A/B selection, movement and adjacent attack remain
 * untouched; no retail game stats or skills are reconstructed here.
 */
#include "map02_battle8.h"

enum { VH_B8_ARCHER_SLOT = 0, VH_B8_BOW_MIN_RANGE = 2,
       VH_B8_BOW_MAX_RANGE = 3, VH_B8_BOW_DAMAGE = 2 };

/* Ray cast along a cardinal grid line. Intermediate walls and living
 * actors block the arrow. Destination must contain the named living foe.
 * No diagonal attacks, friendly fire, hidden slots or off-map shots. */
static inline int vh_b8_clear_shot(const VhBattle8 *battle,
                                    int shooter, int victim, int max_range) {
    const VhRoster8 *r;
    const VhBattleUnit *src, *dst;
    int length, dx, dy, x, y, step;
    if (!battle || battle->status != VH_BONGOING ||
        shooter != VH_B8_ARCHER_SLOT ||
        !vh_r8_active(&battle->roster, shooter) ||
        !vh_r8_active(&battle->roster, victim) ||
        victim < VH_R8_SIDE_CAP ||
        victim >= VH_R8_SIDE_CAP + battle->roster.enemy_count ||
        max_range < VH_B8_BOW_MIN_RANGE || max_range > VH_B8_BOW_MAX_RANGE)
        return 0;
    r = &battle->roster;
    src = &r->units[shooter];
    dst = &r->units[victim];
    if (!vh_balive(src) || !vh_balive(dst) || src->acted ||
        !vh_btile_inside(src->x, src->y) ||
        !vh_btile_inside(dst->x, dst->y))
        return 0;
    if (src->x != dst->x && src->y != dst->y) return 0;
    length = vh_bdistance(src->x, src->y, dst->x, dst->y);
    if (length < VH_B8_BOW_MIN_RANGE || length > max_range) return 0;
    dx = dst->x > src->x ? 1 : dst->x < src->x ? -1 : 0;
    dy = dst->y > src->y ? 1 : dst->y < src->y ? -1 : 0;
    x = src->x;
    y = src->y;
    for (step = 1; step < length; ++step) {
        x += dx;
        y += dy;
        if (!vh_btile_inside(x, y) ||
            (r->walls[y] & (1u << x)) ||
            vh_r8_occupant(r, x, y) != -1)
            return 0;
    }
    return 1;
}

/* A B-button shot at a ranged enemy, while the first ally is selected.
 * Illegal shots NEVER mutate selection, health, flags or last action. */
static inline int vh_b8_shoot(VhBattle8 *battle) {
    int victim, shooter;
    if (!battle || battle->status != VH_BONGOING)
        return VH_BINVALID;
    shooter = battle->selected;
    victim = vh_r8_occupant(&battle->roster,
                             battle->roster.cursor_x,
                             battle->roster.cursor_y);
    if (!vh_b8_clear_shot(battle, shooter, victim,
                          VH_B8_BOW_MAX_RANGE))
        return VH_BINVALID;
    battle->roster.units[victim].hp -= VH_B8_BOW_DAMAGE;
    battle->roster.units[shooter].acted = 1;
    battle->selected = -1;
    battle->status = vh_r8_result(&battle->roster);
    return battle->last_action = VH_BATTACK;
}

#endif /* VH_MAP02_RANGED8_H */
