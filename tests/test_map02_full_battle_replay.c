/*
 * Complete five-turn asset-free MAP02 tactical victory by REAL public
 * selection/move/attack/end-turn APIs, from the unmodified fixture spawn.
 * No teleporting units, forcibly changing HP or injecting end conditions.
 *
 * This is the original Switch-prototype encounter, NOT retail MAP02.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_battle_fixture.h"

typedef struct {
    VhMap02Battle state;
    int enemy_hp, ally_hp, phase;
} ReplayFrame;

static void select_at(VhMap02Battle *s, int ally) {
    assert(ally >= 0 && ally < VH_BALLIES);
    assert(vh_balive(&s->units[ally]) && !s->units[ally].acted);
    s->cursor_x = s->units[ally].x;
    s->cursor_y = s->units[ally].y;
    assert(vh_bchoose(s) == VH_BSELECT);
    assert(s->selected == ally);
}

static void move_ally(VhMap02Battle *s, int ally, int x, int y) {
    const int previous_turns = s->turns_completed;
    select_at(s, ally);
    s->cursor_x = x;
    s->cursor_y = y;
    assert(vh_bchoose(s) == VH_BMOVE);
    assert(s->units[ally].x == x && s->units[ally].y == y);
    assert(s->units[ally].acted && s->selected == -1);
    assert(s->turns_completed == previous_turns);
}

static void attack_foe(VhMap02Battle *s, int ally, int foe) {
    const int old_hp = s->units[foe].hp;
    const int old_x = s->units[ally].x;
    const int old_y = s->units[ally].y;
    assert(foe >= VH_BALLIES && foe < VH_BUNITS);
    assert(old_hp > 0);
    select_at(s, ally);
    s->cursor_x = s->units[foe].x;
    s->cursor_y = s->units[foe].y;
    assert(vh_bchoose(s) == VH_BATTACK);
    assert(s->units[foe].hp == old_hp - 1);
    assert(s->units[ally].x == old_x && s->units[ally].y == old_y);
    assert(s->units[ally].acted);
    assert(s->selected == -1);
}

static void finish_player_turn(VhMap02Battle *s, int expected_turn) {
    assert(s->status == VH_BONGOING);
    assert(s->turns_completed == expected_turn - 1);
    assert(vh_bend_turn(s) == VH_BEND);
    assert(s->turns_completed == expected_turn);
    assert(!s->units[0].acted && !s->units[1].acted);
    assert(s->selected == -1);
}

static ReplayFrame record(const VhMap02Battle *s, int phase) {
    ReplayFrame frame;
    memset(&frame, 0, sizeof(frame));
    frame.state = *s;
    frame.phase = phase;
    frame.enemy_hp = (s->units[2].hp > 0 ? s->units[2].hp : 0) +
                     (s->units[3].hp > 0 ? s->units[3].hp : 0);
    frame.ally_hp = (s->units[0].hp > 0 ? s->units[0].hp : 0) +
                    (s->units[1].hp > 0 ? s->units[1].hp : 0);
    return frame;
}

static void assert_living_occupancy(const VhMap02Battle *s) {
    int i;
    for (i = 0; i < VH_BUNITS; ++i) {
        const VhBattleUnit *u = &s->units[i];
        if (!vh_balive(u)) continue;
        assert(vh_btile_inside(u->x, u->y));
        assert(!vh_bwall(u->x, u->y));
        assert(vh_boccupant(s, u->x, u->y, -1) == i);
    }
}

static void run_full_battle(ReplayFrame history[6]) {
    VhMap02Battle s;
    vh_binit(&s);
    assert(s.status == VH_BONGOING && s.turns_completed == 0);
    history[0] = record(&s, 0);

    /* Turn 1: two heroes approach each side of the authored stone wall. */
    move_ally(&s, 0, 1, 0);
    move_ally(&s, 1, 3, 4);
    finish_player_turn(&s, 1);
    assert_living_occupancy(&s);
    history[1] = record(&s, 1);

    /* Turn 2: both allies make legal two-tile BFS moves. */
    move_ally(&s, 0, 3, 0);
    move_ally(&s, 1, 4, 5);
    finish_player_turn(&s, 2);
    assert_living_occupancy(&s);
    history[2] = record(&s, 2);

    /* Turn 3: ally 1 attacks the second opponent; ally 0 waits. */
    attack_foe(&s, 1, 3);
    finish_player_turn(&s, 3);
    assert_living_occupancy(&s);
    history[3] = record(&s, 3);

    /* Turn 4: one hit on enemy 2, final hit on enemy 3. */
    attack_foe(&s, 0, 2);
    attack_foe(&s, 1, 3);
    assert(!vh_balive(&s.units[3]) && vh_balive(&s.units[2]));
    finish_player_turn(&s, 4);
    assert_living_occupancy(&s);
    history[4] = record(&s, 4);

    /* Turn 5: last legitimate melee strike wins without mutating HP. */
    attack_foe(&s, 0, 2);
    assert(s.status == VH_BWIN);
    assert(!vh_balive(&s.units[2]) && !vh_balive(&s.units[3]));
    assert(vh_bchoose(&s) == VH_BINVALID);
    assert(vh_bend_turn(&s) == VH_BINVALID);
    assert(s.turns_completed == 4); /* victory before the fifth enemy phase */
    assert_living_occupancy(&s);
    history[5] = record(&s, 5);
    assert(history[5].enemy_hp == 0);
    assert(history[5].ally_hp > 0);
    assert(history[0].enemy_hp == 4);

    /* The exact game controller 'Y' reset path uses vh_binit(). */
    vh_binit(&s);
    assert(memcmp(&s, &history[0].state, sizeof(s)) == 0);
}

int main(void) {
    ReplayFrame a[6], b[6];
    int i;
    memset(a, 0, sizeof(a));
    memset(b, 0, sizeof(b));
    run_full_battle(a);
    run_full_battle(b);
    for (i = 0; i < 6; ++i) {
        assert(a[i].phase == i && b[i].phase == i);
        assert(memcmp(&a[i], &b[i], sizeof(a[i])) == 0);
        if (i < 5) assert(a[i].state.status == VH_BONGOING);
    }
    assert(a[3].enemy_hp == 3); /* two enemies alive, one wounded */
    assert(a[4].enemy_hp == 1); /* one enemy left */
    assert(a[5].enemy_hp == 0); /* full five-turn battle won */
    puts("VH_MAP02_FULL_BATTLE_REPLAY_PASS turns=5 controlled_moves=4 "
         "melee_attacks=4 enemy_phases=4 victory=1 resets=2 "
         "deterministic=1 original_retail=0");
    return 0;
}
