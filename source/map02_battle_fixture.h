#ifndef VH_MAP02_BATTLE_FIXTURE_H
#define VH_MAP02_BATTLE_FIXTURE_H

/*
 * Original, asset-free tactical encounter for Switch prototype validation.
 * NOT a reconstruction or verified replay of Vandal Hearts retail MAP02.
 * Header-only ISO C11 battle rules shared by native libnx and host tests.
 */
#include <string.h>

enum { VH_BW = 8, VH_BH = 6, VH_BUNITS = 4, VH_BALLIES = 2 };
enum { VH_BONGOING = 0, VH_BWIN = 1, VH_BLOSS = 2 };
enum { VH_BINVALID = 0, VH_BSELECT = 1, VH_BMOVE = 2,
       VH_BATTACK = 3, VH_BCANCEL = 4, VH_BEND = 5 };

typedef struct {
    int x, y, hp, acted;
} VhBattleUnit;

enum { VH_BEVENT_ENEMIES_DOWN = 1, VH_BEVENT_ALLIES_DOWN = 2 };
typedef struct {
    int when, result;
} VhBattleEvent;

typedef struct {
    unsigned char walls[VH_BH];          /* bit x of row y = blocked */
    VhBattleUnit spawn[VH_BUNITS];       /* ally 0..1, enemy 2..3 */
    int cursor_x, cursor_y;
    int move_range, attack_damage;
    VhBattleEvent events[2];             /* validated win and defeat */
    int event_count;
} VhBattleScenario;

#include "map02_encounter_data.h"
#include "map02_encounter_b_data.h"

enum { VH_BSCENARIOS = 2 };

static inline const VhBattleScenario *vh_bscenario_by_index(int index) {
    if (index == 0) return &VH_MAP02_DEFAULT_SCENARIO;
    if (index == 1) return &VH_MAP02_SECOND_SCENARIO;
    return 0;  /* untrusted scenario IDs fail closed */
}

typedef struct {
    VhBattleUnit units[VH_BUNITS]; /* 0-1 allies; 2-3 enemies */
    int cursor_x, cursor_y;
    int selected;                 /* -1 or allied unit index */
    int status;                   /* VH_BONGOING / WIN / LOSS */
    int turns_completed;
    int last_action;
    unsigned char walls[VH_BH];
    int move_range, attack_damage;
    VhBattleEvent events[2];
    int event_count;
} VhMap02Battle;

static inline int vh_btile_inside(int x, int y) {
    return x >= 0 && y >= 0 && x < VH_BW && y < VH_BH;
}

/* Backward-compatible default-layout query for legacy fixture tests. */
static inline int vh_bwall(int x, int y) {
    return vh_btile_inside(x, y) &&
           !!(VH_MAP02_DEFAULT_SCENARIO.walls[y] & (1u << x));
}

/* Active scenario's collision map, rather than hard-coded retail map tiles. */
static inline int vh_bwall_at(const VhMap02Battle *s, int x, int y) {
    return s && vh_btile_inside(x, y) &&
           !!(s->walls[y] & (1u << x));
}

/* Fail closed before mutating the active battle on invalid authored input. */
static inline int vh_bscenario_valid(const VhBattleScenario *cfg) {
    int i, j, seen_win = 0, seen_loss = 0;
    if (!cfg || !vh_btile_inside(cfg->cursor_x, cfg->cursor_y) ||
        cfg->move_range < 1 || cfg->move_range > 7 ||
        cfg->attack_damage < 1 || cfg->attack_damage > 20 ||
        cfg->event_count != 2)
        return 0;
    for (i = 0; i < VH_BUNITS; ++i) {
        const VhBattleUnit *u = &cfg->spawn[i];
        if (!vh_btile_inside(u->x, u->y) ||
            !!(cfg->walls[u->y] & (1u << u->x)) ||
            u->hp < 1 || u->hp > 20 || u->acted != 0)
            return 0;
        for (j = 0; j < i; ++j)
            if (u->x == cfg->spawn[j].x && u->y == cfg->spawn[j].y)
                return 0;
    }
    for (i = 0; i < cfg->event_count; ++i) {
        const VhBattleEvent *e = &cfg->events[i];
        if (e->when == VH_BEVENT_ENEMIES_DOWN && e->result == VH_BWIN)
            ++seen_win;
        else if (e->when == VH_BEVENT_ALLIES_DOWN && e->result == VH_BLOSS)
            ++seen_loss;
        else
            return 0;
    }
    return seen_win == 1 && seen_loss == 1;
}

static inline int vh_balive(const VhBattleUnit *unit) {
    return unit->hp > 0;
}

static inline int vh_boccupant(const VhMap02Battle *s, int x, int y,
                               int ignore) {
    int i;
    for (i = 0; i < VH_BUNITS; ++i)
        if (i != ignore && vh_balive(&s->units[i]) &&
            s->units[i].x == x && s->units[i].y == y)
            return i;
    return -1;
}

static inline int vh_bdistance(int x, int y, int xx, int yy) {
    int dx = x > xx ? x - xx : xx - x;
    int dy = y > yy ? y - yy : yy - y;
    return dx + dy;
}

/*
 * Bounded breadth-first search: occupancy and solid terrain are respected.
 * An occupied destination may be made reachable ONLY for the named target
 * of an enemy path (enemy still stops on the preceding unoccupied tile).
 */
static inline int vh_bpath(const VhMap02Battle *s, int mover, int tx, int ty,
                           int allowed_target, int *step_x, int *step_y) {
    int dist[VH_BW * VH_BH], previous[VH_BW * VH_BH];
    int queue[VH_BW * VH_BH], head = 0, tail = 0;
    static const int dx[4] = {0, -1, 1, 0};
    static const int dy[4] = {-1, 0, 0, 1};
    int i, start, end, px, py;
    const VhBattleUnit *u;
    if (!s || mover < 0 || mover >= VH_BUNITS ||
        !vh_balive(&s->units[mover]) || !vh_btile_inside(tx, ty) ||
        vh_bwall_at(s, tx, ty))
        return -1;
    u = &s->units[mover];
    if (!vh_btile_inside(u->x, u->y)) return -1;
    start = u->y * VH_BW + u->x;
    end = ty * VH_BW + tx;
    for (i = 0; i < VH_BW * VH_BH; ++i) {
        dist[i] = -1;
        previous[i] = -1;
    }
    queue[tail++] = start;
    dist[start] = 0;
    while (head < tail) {
        int cell = queue[head++], cx = cell % VH_BW, cy = cell / VH_BW;
        int dir;
        if (cell == end) break;
        for (dir = 0; dir < 4; ++dir) {
            const int nx = cx + dx[dir], ny = cy + dy[dir];
            int occ, index;
            if (!vh_btile_inside(nx, ny) || vh_bwall_at(s, nx, ny)) continue;
            index = ny * VH_BW + nx;
            if (dist[index] >= 0) continue;
            occ = vh_boccupant(s, nx, ny, mover);
            if (occ >= 0 && !(index == end && occ == allowed_target))
                continue;
            dist[index] = dist[cell] + 1;
            previous[index] = cell;
            queue[tail++] = index;
        }
    }
    if (dist[end] < 0) return -1;
    if (step_x && step_y) {
        int next = end;
        while (previous[next] >= 0 && previous[next] != start)
            next = previous[next];
        px = next % VH_BW;
        py = next / VH_BW;
        *step_x = px;
        *step_y = py;
    }
    return dist[end];
}

static inline int vh_binit_scenario(VhMap02Battle *s,
                                    const VhBattleScenario *cfg) {
    if (!s || !vh_bscenario_valid(cfg)) return 0;
    memset(s, 0, sizeof(*s));
    memcpy(s->units, cfg->spawn, sizeof(s->units));
    memcpy(s->walls, cfg->walls, sizeof(s->walls));
    memcpy(s->events, cfg->events, sizeof(s->events));
    s->event_count = cfg->event_count;
    s->move_range = cfg->move_range;
    s->attack_damage = cfg->attack_damage;
    s->cursor_x = cfg->cursor_x;
    s->cursor_y = cfg->cursor_y;
    s->selected = -1;
    return 1;
}

static inline int vh_binit_index(VhMap02Battle *s, int index) {
    const VhBattleScenario *data = vh_bscenario_by_index(index);
    return data && vh_binit_scenario(s, data);
}

static inline void vh_binit(VhMap02Battle *s) {
    (void)vh_binit_index(s, 0);
}

static inline void vh_bcursor(VhMap02Battle *s, int dx, int dy) {
    int nx, ny;
    if (!s || s->status != VH_BONGOING) return;
    nx = s->cursor_x + dx;
    ny = s->cursor_y + dy;
    if (vh_btile_inside(nx, ny)) {
        s->cursor_x = nx;
        s->cursor_y = ny;
    }
}

static inline void vh_bupdate_status(VhMap02Battle *s) {
    int allies, enemies, i;
    if (!s || s->status != VH_BONGOING) return;
    allies = vh_balive(&s->units[0]) + vh_balive(&s->units[1]);
    enemies = vh_balive(&s->units[2]) + vh_balive(&s->units[3]);
    for (i = 0; i < s->event_count; ++i) {
        if ((s->events[i].when == VH_BEVENT_ENEMIES_DOWN && enemies == 0) ||
            (s->events[i].when == VH_BEVENT_ALLIES_DOWN && allies == 0)) {
            s->status = s->events[i].result;
            return;
        }
    }
}

static inline int vh_bcancel(VhMap02Battle *s) {
    if (!s || s->selected < 0 || s->status != VH_BONGOING) return VH_BINVALID;
    s->selected = -1;
    return s->last_action = VH_BCANCEL;
}

static inline int vh_bchoose(VhMap02Battle *s) {
    int occ, src, dist;
    if (!s || s->status != VH_BONGOING) return VH_BINVALID;
    occ = vh_boccupant(s, s->cursor_x, s->cursor_y, -1);
    if (s->selected < 0) {
        if (occ >= 0 && occ < VH_BALLIES && !s->units[occ].acted) {
            s->selected = occ;
            return s->last_action = VH_BSELECT;
        }
        return VH_BINVALID;
    }
    src = s->selected;
    if (src < 0 || src >= VH_BALLIES ||
        !vh_balive(&s->units[src]) || s->units[src].acted)
        return VH_BINVALID;
    if (occ >= VH_BALLIES && vh_bdistance(s->units[src].x, s->units[src].y,
                                           s->cursor_x, s->cursor_y) == 1) {
        s->units[occ].hp -= s->attack_damage;
        s->units[src].acted = 1;
        s->selected = -1;
        vh_bupdate_status(s);
        return s->last_action = VH_BATTACK;
    }
    if (occ >= 0) return VH_BINVALID;
    dist = vh_bpath(s, src, s->cursor_x, s->cursor_y, -1, 0, 0);
    if (dist < 1 || dist > s->move_range) return VH_BINVALID;
    s->units[src].x = s->cursor_x;
    s->units[src].y = s->cursor_y;
    s->units[src].acted = 1;
    s->selected = -1;
    return s->last_action = VH_BMOVE;
}

static inline int vh_bend_turn(VhMap02Battle *s) {
    int enemy;
    if (!s || s->status != VH_BONGOING) return VH_BINVALID;
    s->selected = -1;
    for (enemy = VH_BALLIES; enemy < VH_BUNITS; ++enemy) {
        int hero, closest = -1, shortest = 1000;
        int step_x = -1, step_y = -1;
        VhBattleUnit *foe = &s->units[enemy];
        if (!vh_balive(foe)) continue;
        for (hero = 0; hero < VH_BALLIES; ++hero) {
            int d;
            if (!vh_balive(&s->units[hero])) continue;
            d = vh_bpath(s, enemy, s->units[hero].x, s->units[hero].y,
                         hero, 0, 0);
            if (d >= 0 && d < shortest) {
                shortest = d;
                closest = hero;
            }
        }
        if (closest < 0) continue;
        if (shortest == 1) {
            s->units[closest].hp -= s->attack_damage;
            vh_bupdate_status(s);
            if (s->status != VH_BONGOING) break;
        } else if (shortest > 1 && vh_bpath(s, enemy, s->units[closest].x,
                                           s->units[closest].y, closest,
                                           &step_x, &step_y) > 1 &&
                   vh_boccupant(s, step_x, step_y, enemy) < 0) {
            foe->x = step_x;
            foe->y = step_y;
        }
    }
    ++s->turns_completed;
    s->units[0].acted = 0;
    s->units[1].acted = 0;
    return s->last_action = VH_BEND;
}

#endif /* VH_MAP02_BATTLE_FIXTURE_H */
