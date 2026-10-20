#ifndef VH_MAP02_MEDIC8_H
#define VH_MAP02_MEDIC8_H

/*
 * Opt-in support ability for ally slot 1 in the SECOND independent arena.
 * Caller MUST require scene==1. Original authored fixtures, melee, archer
 * rules and legacy four-slot MAP02 gameplay are not changed.
 */
#include "map02_battle8.h"

enum {
    VH_B8_MEDIC_SLOT = 1,
    VH_B8_HEAL_AMOUNT = 2,
    VH_B8_HEAL_HP_CAP = 3,
    VH_BHEAL = 6
};

/* Only living, previously injured adjacent allied units may be healed.
 * No revives, range extensions, self-heal, enemy heal, extra HP, actions
 * after victory/loss, or repeated actions in the same player phase.
 * All invalid commands are strictly non-mutating. */
static inline int vh_b8_can_heal(const VhBattle8 *battle,
                                  int healer, int patient) {
    const VhRoster8 *r;
    const VhBattleUnit *src, *dst;
    if (!battle || battle->status != VH_BONGOING ||
        healer != VH_B8_MEDIC_SLOT ||
        !vh_r8_active(&battle->roster, healer) ||
        !vh_r8_active(&battle->roster, patient) ||
        patient < 0 || patient >= battle->roster.ally_count ||
        patient == healer)
        return 0;
    r = &battle->roster;
    src = &r->units[healer];
    dst = &r->units[patient];
    if (!vh_balive(src) || !vh_balive(dst) || src->acted ||
        dst->hp >= VH_B8_HEAL_HP_CAP || dst->hp < 1 ||
        !vh_btile_inside(src->x, src->y) ||
        !vh_btile_inside(dst->x, dst->y) ||
        vh_bdistance(src->x, src->y, dst->x, dst->y) != 1)
        return 0;
    return 1;
}

static inline int vh_b8_heal(VhBattle8 *battle) {
    int healer, target, restored;
    if (!battle || battle->status != VH_BONGOING)
        return VH_BINVALID;
    healer = battle->selected;
    target = vh_r8_occupant(&battle->roster,
                            battle->roster.cursor_x,
                            battle->roster.cursor_y);
    if (!vh_b8_can_heal(battle, healer, target))
        return VH_BINVALID;
    restored = VH_B8_HEAL_HP_CAP - battle->roster.units[target].hp;
    if (restored > VH_B8_HEAL_AMOUNT) restored = VH_B8_HEAL_AMOUNT;
    battle->roster.units[target].hp += restored;
    battle->roster.units[healer].acted = 1;
    battle->selected = -1;
    return battle->last_action = VH_BHEAL;
}

#endif /* VH_MAP02_MEDIC8_H */
