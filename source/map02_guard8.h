#ifndef VH_MAP02_GUARD8_H
#define VH_MAP02_GUARD8_H

/*
 * Independent asset-free support action: ally 3 (slot 2) issues a team-wide one-hit shield
 * against the first enemy attack of the next opponent phase.
 * This opt-in rule is wired only for optional expanded arena B.
 * Unarmed battle8, legacy MAP02, and existing archer/medic remain unchanged.
 */
#include "map02_battle8.h"

enum {
    VH_B8_GUARD_SLOT = 2,
    VH_B8_GUARD_REDUCTION = 1,
    VH_BGUARD = 7
};

typedef struct {
    int active;
    int absorbed_last_turn;
} VhGuard8;

static inline void vh_b8_guard_reset(VhGuard8 *guard) {
    if (!guard) return;
    guard->active = 0;
    guard->absorbed_last_turn = 0;
}

/* Selection of the living third ally and B on the same tile.
 * Rejecting a stance MUST NOT modify any battle or guard state. */
static inline int vh_b8_guard_action(VhBattle8 *battle, VhGuard8 *guard) {
    const VhRoster8 *r;
    const VhBattleUnit *actor;
    if (!battle || !guard || guard->active ||
        battle->status != VH_BONGOING ||
        battle->selected != VH_B8_GUARD_SLOT ||
        !vh_r8_active(&battle->roster, VH_B8_GUARD_SLOT))
        return VH_BINVALID;
    r = &battle->roster;
    actor = &r->units[VH_B8_GUARD_SLOT];
    if (!vh_balive(actor) || actor->acted ||
        r->cursor_x != actor->x || r->cursor_y != actor->y)
        return VH_BINVALID;
    battle->roster.units[VH_B8_GUARD_SLOT].acted = 1;
    battle->selected = -1;
    guard->active = 1;
    guard->absorbed_last_turn = 0;
    return battle->last_action = VH_BGUARD;
}

/*
 * Unmodified deterministic enemy targeting/pathfinding, except one
 * guaranteed point of reduction against the first attacked ally.
 * Guard expires after this ONE enemy phase, including a no-hit phase.
 * Without an armed guard, defer exactly to the verified original AI.
 */
static inline int vh_b8_end_turn_guarded(VhBattle8 *battle, VhGuard8 *guard) {
    VhRoster8 *r;
    int enemy, absorbed = 0;
    if (!battle || !guard || battle->status != VH_BONGOING)
        return VH_BINVALID;
    if (!guard->active) {
        const int result = vh_b8_end_turn(battle);
        if (result != VH_BINVALID) guard->absorbed_last_turn = 0;
        return result;
    }
    if (!vh_r8_active(&battle->roster, VH_B8_GUARD_SLOT) ||
        !vh_balive(&battle->roster.units[VH_B8_GUARD_SLOT]) ||
        battle->attack_damage <= VH_B8_GUARD_REDUCTION ||
        !battle->roster.units[VH_B8_GUARD_SLOT].acted)
        return VH_BINVALID;
    r = &battle->roster;
    battle->selected = -1;
    for (enemy = VH_R8_SIDE_CAP;
         enemy < VH_R8_SIDE_CAP + r->enemy_count; ++enemy) {
        int hero, closest = -1, shortest = VH_BW * VH_BH + 1;
        int sx = -1, sy = -1;
        VhBattleUnit *foe = &r->units[enemy];
        if (!vh_balive(foe)) continue;
        for (hero = 0; hero < r->ally_count; ++hero) {
            int distance;
            if (!vh_balive(&r->units[hero])) continue;
            distance = vh_b8_path(battle, enemy,
                                  r->units[hero].x, r->units[hero].y,
                                  hero, 0, 0);
            if (distance >= 0 && distance < shortest) {
                shortest = distance;
                closest = hero;
            }
        }
        if (closest < 0) continue;
        if (shortest == 1) {
            int damage = battle->attack_damage;
            if (!absorbed) {
                damage -= VH_B8_GUARD_REDUCTION;
                absorbed = VH_B8_GUARD_REDUCTION;
            }
            if (!vh_r8_attack(r, enemy, closest, damage))
                return VH_BINVALID;
            battle->status = vh_r8_result(r);
            if (battle->status != VH_BONGOING) break;
        } else if (shortest > 1 &&
                   vh_b8_path(battle, enemy,
                              r->units[closest].x, r->units[closest].y,
                              closest, &sx, &sy) > 1 &&
                   vh_r8_occupant(r, sx, sy) == -1) {
            foe->x = sx;
            foe->y = sy;
            foe->acted = 1;
        }
    }
    ++battle->turns_completed;
    vh_r8_reset_actions(r, 0);
    vh_r8_reset_actions(r, 1);
    guard->active = 0;
    guard->absorbed_last_turn = absorbed;
    return battle->last_action = VH_BEND;
}

#endif /* VH_MAP02_GUARD8_H */
