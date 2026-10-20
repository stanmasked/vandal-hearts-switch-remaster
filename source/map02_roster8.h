#ifndef VH_MAP02_ROSTER8_H
#define VH_MAP02_ROSTER8_H

/*
 * Stage after MAP02 variable 1..2 rosters: an opt-in 4+4 roster contract.
 * Legacy VhBattleScenario/VhMap02Battle layouts are NOT modified.
 * This is a portable roster/battle-state foundation, not yet the libnx
 * gameplay path, full 8-unit turn AI, or retail Vandal Hearts content.
 */
#include "map02_battle_fixture.h"
#include <string.h>

enum { VH_R8_SIDE_CAP = 4, VH_R8_CAPACITY = 8, VH_R8_INVALID_STATUS = -1 };

typedef struct {
    VhBattleUnit units[VH_R8_CAPACITY]; /* allies [0,4), enemies [4,8) */
    unsigned char walls[VH_BH];
    int ally_count, enemy_count;
    int cursor_x, cursor_y;
} VhRoster8;

static inline int vh_r8_index(int side, int position) {
    if (side < 0 || side > 1 || position < 0 ||
        position >= VH_R8_SIDE_CAP) return -1;
    return side * VH_R8_SIDE_CAP + position;
}

static inline int vh_r8_active(const VhRoster8 *r, int slot) {
    if (!r || slot < 0 || slot >= VH_R8_CAPACITY) return 0;
    if (slot < VH_R8_SIDE_CAP) return slot < r->ally_count;
    return slot - VH_R8_SIDE_CAP < r->enemy_count;
}

/* Checks an authored, fresh spawn only (HP 1..20 and acted=0).
 * Zero padding is mandatory; validation precedes mutations. */
static inline int vh_r8_valid(const VhRoster8 *r) {
    int i, j;
    if (!r || r->ally_count < 1 || r->ally_count > VH_R8_SIDE_CAP ||
        r->enemy_count < 1 || r->enemy_count > VH_R8_SIDE_CAP ||
        !vh_btile_inside(r->cursor_x, r->cursor_y))
        return 0;
    for (i = 0; i < VH_R8_CAPACITY; ++i) {
        const VhBattleUnit *u = &r->units[i];
        if (!vh_r8_active(r, i)) {
            if (u->x != 0 || u->y != 0 || u->hp != 0 || u->acted != 0)
                return 0;
            continue;
        }
        if (!vh_btile_inside(u->x, u->y) ||
            (r->walls[u->y] & (1u << u->x)) ||
            u->hp < 1 || u->hp > 20 || u->acted != 0)
            return 0;
        for (j = 0; j < i; ++j)
            if (vh_r8_active(r, j) &&
                r->units[j].x == u->x && r->units[j].y == u->y)
                return 0;
    }
    return r->cursor_x == r->units[0].x &&
           r->cursor_y == r->units[0].y;
}

/* Canonical translation; do not change the approved 4-slot source data. */
static inline int vh_r8_from_legacy(VhRoster8 *out,
                                    const VhBattleScenario *scenario) {
    VhRoster8 candidate = {0};
    int i;
    if (!out || !vh_bscenario_valid(scenario)) return 0;
    candidate.ally_count = scenario->ally_count;
    candidate.enemy_count = scenario->enemy_count;
    candidate.cursor_x = scenario->cursor_x;
    candidate.cursor_y = scenario->cursor_y;
    memcpy(candidate.walls, scenario->walls, sizeof(candidate.walls));
    for (i = 0; i < candidate.ally_count; ++i)
        candidate.units[i] = scenario->spawn[i];
    for (i = 0; i < candidate.enemy_count; ++i)
        candidate.units[VH_R8_SIDE_CAP + i] =
            scenario->spawn[VH_BALLIES + i];
    if (!vh_r8_valid(&candidate)) return 0;
    *out = candidate;
    return 1;
}

/* The following operations are deliberately limited to portable
 * adjacent-combat-state tests. The real legacy pathfinding, enemy AI and
 * Switch NRO UI continue using VhMap02Battle until a later integration. */
static inline int vh_r8_occupant(const VhRoster8 *r, int x, int y) {
    int i;
    if (!r || !vh_btile_inside(x, y)) return -1;
    for (i = 0; i < VH_R8_CAPACITY; ++i)
        if (vh_r8_active(r, i) && vh_balive(&r->units[i]) &&
            r->units[i].x == x && r->units[i].y == y)
            return i;
    return -1;
}

static inline int vh_r8_alive(const VhRoster8 *r, int side) {
    int i, result = 0;
    if (!r || side < 0 || side > 1) return 0;
    for (i = side * VH_R8_SIDE_CAP; i < (side + 1) * VH_R8_SIDE_CAP; ++i)
        if (vh_r8_active(r, i) && vh_balive(&r->units[i])) ++result;
    return result;
}

static inline int vh_r8_result(const VhRoster8 *r) {
    if (!r) return VH_R8_INVALID_STATUS;
    if (!vh_r8_alive(r, 0)) return VH_BLOSS;
    if (!vh_r8_alive(r, 1)) return VH_BWIN;
    return VH_BONGOING;
}

/* Reject forged/hidden slots, friendly fire, repeat actions, and distance
 * greater than one. Return 1 only for a real legal adjacent attack. */
static inline int vh_r8_attack(VhRoster8 *r, int attacker, int victim,
                               int damage) {
    if (!r || !vh_r8_active(r, attacker) ||
        !vh_r8_active(r, victim) || damage < 1 || damage > 20 ||
        (attacker < VH_R8_SIDE_CAP) == (victim < VH_R8_SIDE_CAP) ||
        !vh_balive(&r->units[attacker]) ||
        !vh_balive(&r->units[victim]) || r->units[attacker].acted ||
        vh_bdistance(r->units[attacker].x, r->units[attacker].y,
                     r->units[victim].x, r->units[victim].y) != 1)
        return 0;
    r->units[victim].hp -= damage;
    r->units[attacker].acted = 1;
    return 1;
}

static inline void vh_r8_reset_actions(VhRoster8 *r, int side) {
    int i;
    if (!r || side < 0 || side > 1) return;
    for (i = 0; i < VH_R8_SIDE_CAP; ++i) {
        const int slot = vh_r8_index(side, i);
        if (vh_r8_active(r, slot)) r->units[slot].acted = 0;
    }
}

#endif /* VH_MAP02_ROSTER8_H */
