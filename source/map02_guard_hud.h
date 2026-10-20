#ifndef VH_MAP02_GUARD_HUD_H
#define VH_MAP02_GUARD_HUD_H

/*
 * Pure display contract for the optional second-arena guard. No game-state
 * mutations or retail content. An unavailable/finished guard never claims
 * to protect the team. Displays the previous block for one player phase.
 */
#include "map02_guard8.h"

enum {
    VH_GHUD_HIDDEN = 0,
    VH_GHUD_UNAVAILABLE = 1,
    VH_GHUD_READY = 2,
    VH_GHUD_SPENT = 3,
    VH_GHUD_ARMED = 4,
    VH_GHUD_BLOCKED = 5,
    VH_GHUD_FINISHED = 6
};

static inline int vh_b8_guard_hud_state(const VhBattle8 *battle,
                                        const VhGuard8 *guard, int scene) {
    if (!battle || !guard || scene != 1) return VH_GHUD_HIDDEN;
    if (battle->status != VH_BONGOING) return VH_GHUD_FINISHED;
    if (!vh_r8_active(&battle->roster, VH_B8_GUARD_SLOT) ||
        !vh_balive(&battle->roster.units[VH_B8_GUARD_SLOT]))
        return VH_GHUD_UNAVAILABLE;
    if (guard->active) return VH_GHUD_ARMED;
    if (guard->absorbed_last_turn == VH_B8_GUARD_REDUCTION)
        return VH_GHUD_BLOCKED;
    if (battle->roster.units[VH_B8_GUARD_SLOT].acted)
        return VH_GHUD_SPENT;
    return VH_GHUD_READY;
}

static inline const char *vh_b8_guard_hud_label(int state) {
    switch (state) {
    case VH_GHUD_UNAVAILABLE: return "GUARD UNAVAILABLE";
    case VH_GHUD_READY: return "GUARD READY";
    case VH_GHUD_SPENT: return "GUARD SPENT";
    case VH_GHUD_ARMED: return "GUARD ARMED -1 HP";
    case VH_GHUD_BLOCKED: return "GUARD BLOCKED 1 HP";
    case VH_GHUD_FINISHED: return "GUARD FINISHED";
    default: return "";
    }
}

#endif /* VH_MAP02_GUARD_HUD_H */
