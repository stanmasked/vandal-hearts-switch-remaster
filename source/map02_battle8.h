#ifndef VH_MAP02_BATTLE8_H
#define VH_MAP02_BATTLE8_H

/*
 * Portable eight-slot tactical turn engine for independently authored fixtures.
 * This is deliberately opt-in: source/main.c continues using VhMap02Battle.
 * No retail Vandal Hearts MAP02 data, characters, or copyrighted assets.
 */
#include "map02_roster8.h"

typedef struct {
    VhRoster8 roster; /* allies 0..3, enemies 4..7 */
    int selected;    /* -1 when nothing selected, otherwise active ally slot */
    int move_range, attack_damage;
    int status;      /* VH_BONGOING, VH_BWIN, VH_BLOSS */
    int turns_completed, last_action;
} VhBattle8;

static inline int vh_b8_init(VhBattle8 *out, const VhRoster8 *authored,
                             int move_range, int attack_damage) {
    VhBattle8 staged = {0};
    if (!out || !vh_r8_valid(authored) ||
        move_range < 1 || move_range > 7 ||
        attack_damage < 1 || attack_damage > 20)
        return 0;
    staged.roster = *authored;
    staged.selected = -1;
    staged.move_range = move_range;
    staged.attack_damage = attack_damage;
    staged.status = VH_BONGOING;
    *out = staged;
    return 1;
}

/* A bounded 8x6 breadth-first route. Exactly one named occupied target may
 * be entered by the search; it is never a legal destination for a move.
 * Other living actors obstruct the path, independent of faction. */
static inline int vh_b8_path(const VhBattle8 *s, int mover, int tx, int ty,
                             int allowed_target, int *step_x, int *step_y) {
    int dist[VH_BW * VH_BH], previous[VH_BW * VH_BH];
    int queue[VH_BW * VH_BH], head = 0, tail = 0;
    static const int dx[4] = {0, -1, 1, 0};
    static const int dy[4] = {-1, 0, 0, 1};
    int start, end, i;
    const VhRoster8 *r;
    const VhBattleUnit *unit;
    if (!s) return -1;
    r = &s->roster;
    if (!vh_r8_active(r, mover) || !vh_balive(&r->units[mover]) ||
        !vh_btile_inside(tx, ty) ||
        (r->walls[ty] & (1u << tx)))
        return -1;
    unit = &r->units[mover];
    if (!vh_btile_inside(unit->x, unit->y)) return -1;
    start = unit->y * VH_BW + unit->x;
    end = ty * VH_BW + tx;
    for (i = 0; i < VH_BW * VH_BH; ++i) {
        dist[i] = -1;
        previous[i] = -1;
    }
    queue[tail++] = start;
    dist[start] = 0;
    while (head < tail) {
        const int cell = queue[head++];
        const int cx = cell % VH_BW, cy = cell / VH_BW;
        int direction;
        if (cell == end) break;
        for (direction = 0; direction < 4; ++direction) {
            const int x = cx + dx[direction], y = cy + dy[direction];
            int next, occupant;
            if (!vh_btile_inside(x, y) ||
                (r->walls[y] & (1u << x)))
                continue;
            next = y * VH_BW + x;
            if (dist[next] >= 0) continue;
            occupant = vh_r8_occupant(r, x, y);
            if (occupant >= 0 && occupant != mover &&
                !(next == end && occupant == allowed_target))
                continue;
            previous[next] = cell;
            dist[next] = dist[cell] + 1;
            queue[tail++] = next;
        }
    }
    if (dist[end] < 0) return -1;
    if (step_x && step_y) {
        int next = end;
        while (previous[next] >= 0 && previous[next] != start)
            next = previous[next];
        *step_x = next % VH_BW;
        *step_y = next / VH_BW;
    }
    return dist[end];
}

static inline void vh_b8_cursor(VhBattle8 *s, int dx, int dy) {
    int x, y;
    if (!s || s->status != VH_BONGOING) return;
    x = s->roster.cursor_x + dx;
    y = s->roster.cursor_y + dy;
    if (vh_btile_inside(x, y)) {
        s->roster.cursor_x = x;
        s->roster.cursor_y = y;
    }
}

static inline int vh_b8_cancel(VhBattle8 *s) {
    if (!s || s->status != VH_BONGOING || s->selected < 0)
        return VH_BINVALID;
    s->selected = -1;
    return s->last_action = VH_BCANCEL;
}

static inline int vh_b8_choose(VhBattle8 *s) {
    VhRoster8 *r;
    int occ, actor, distance;
    if (!s || s->status != VH_BONGOING) return VH_BINVALID;
    r = &s->roster;
    occ = vh_r8_occupant(r, r->cursor_x, r->cursor_y);
    if (s->selected < 0) {
        if (occ >= 0 && occ < r->ally_count &&
            !r->units[occ].acted) {
            s->selected = occ;
            return s->last_action = VH_BSELECT;
        }
        return VH_BINVALID;
    }
    actor = s->selected;
    if (actor < 0 || actor >= r->ally_count ||
        !vh_balive(&r->units[actor]) || r->units[actor].acted)
        return VH_BINVALID;
    if (occ >= VH_R8_SIDE_CAP &&
        occ < VH_R8_SIDE_CAP + r->enemy_count &&
        vh_r8_attack(r, actor, occ, s->attack_damage)) {
        s->selected = -1;
        s->status = vh_r8_result(r);
        return s->last_action = VH_BATTACK;
    }
    if (occ >= 0) return VH_BINVALID;
    distance = vh_b8_path(s, actor, r->cursor_x, r->cursor_y, -1, 0, 0);
    if (distance < 1 || distance > s->move_range)
        return VH_BINVALID;
    r->units[actor].x = r->cursor_x;
    r->units[actor].y = r->cursor_y;
    r->units[actor].acted = 1;
    s->selected = -1;
    return s->last_action = VH_BMOVE;
}

/* One action per living opponent: attack adjacent nearest reachable ally
 * or advance a single free tile towards that ally. Deceased and padded
 * units cannot act. Deterministic ties use the lower allied slot index. */
static inline int vh_b8_end_turn(VhBattle8 *s) {
    VhRoster8 *r;
    int enemy;
    if (!s || s->status != VH_BONGOING) return VH_BINVALID;
    r = &s->roster;
    s->selected = -1;
    for (enemy = VH_R8_SIDE_CAP;
         enemy < VH_R8_SIDE_CAP + r->enemy_count; ++enemy) {
        int hero, closest = -1, shortest = VH_BW * VH_BH + 1;
        int sx = -1, sy = -1;
        VhBattleUnit *foe = &r->units[enemy];
        if (!vh_balive(foe)) continue;
        for (hero = 0; hero < r->ally_count; ++hero) {
            int distance;
            if (!vh_balive(&r->units[hero])) continue;
            distance = vh_b8_path(s, enemy, r->units[hero].x,
                                  r->units[hero].y, hero, 0, 0);
            if (distance >= 0 && distance < shortest) {
                shortest = distance;
                closest = hero;
            }
        }
        if (closest < 0) continue;
        if (shortest == 1) {
            if (!vh_r8_attack(r, enemy, closest, s->attack_damage))
                return VH_BINVALID;
            s->status = vh_r8_result(r);
            if (s->status != VH_BONGOING) break;
        } else if (shortest > 1 &&
                   vh_b8_path(s, enemy, r->units[closest].x,
                              r->units[closest].y, closest,
                              &sx, &sy) > 1 &&
                   vh_r8_occupant(r, sx, sy) == -1) {
            foe->x = sx;
            foe->y = sy;
            foe->acted = 1;
        }
    }
    ++s->turns_completed;
    vh_r8_reset_actions(r, 0);
    vh_r8_reset_actions(r, 1);
    return s->last_action = VH_BEND;
}

#endif /* VH_MAP02_BATTLE8_H */
