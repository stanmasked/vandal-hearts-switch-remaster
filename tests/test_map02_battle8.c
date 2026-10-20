/* End-to-end host-only 4+4 tactical rules; existing Switch NRO unchanged. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_battle8.h"

static VhRoster8 adjacent(int count, int ally_hp, int enemy_hp) {
    VhRoster8 r = {0};
    int i;
    r.ally_count = count;
    r.enemy_count = count;
    for (i = 0; i < count; ++i) {
        r.units[i] = (VhBattleUnit){0, i, ally_hp, 0};
        r.units[4 + i] = (VhBattleUnit){1, i, enemy_hp, 0};
    }
    assert(vh_r8_valid(&r));
    return r;
}

static void attack(VhBattle8 *s, int ally, int enemy) {
    s->roster.cursor_x = s->roster.units[ally].x;
    s->roster.cursor_y = s->roster.units[ally].y;
    assert(vh_b8_choose(s) == VH_BSELECT);
    s->roster.cursor_x = s->roster.units[enemy].x;
    s->roster.cursor_y = s->roster.units[enemy].y;
    assert(vh_b8_choose(s) == VH_BATTACK);
}

static void four_allies_defeat_four_opponents(void) {
    VhRoster8 r = adjacent(4, 3, 1);
    VhBattle8 s;
    int i;
    assert(vh_b8_init(&s, &r, 2, 1));
    for (i = 0; i < 4; ++i) {
        attack(&s, i, 4 + i);
        assert(s.status == (i == 3 ? VH_BWIN : VH_BONGOING));
        assert(s.roster.units[i].acted);
        assert(!vh_balive(&s.roster.units[4 + i]));
    }
    assert(vh_b8_end_turn(&s) == VH_BINVALID);
}

static void four_opponents_defeat_four_allies(void) {
    VhRoster8 r = adjacent(4, 1, 3);
    VhBattle8 s;
    int i;
    assert(vh_b8_init(&s, &r, 2, 1));
    assert(vh_b8_end_turn(&s) == VH_BEND);
    assert(s.turns_completed == 1);
    assert(s.status == VH_BLOSS);
    for (i = 0; i < 4; ++i) {
        assert(!vh_balive(&s.roster.units[i]));
        assert(vh_balive(&s.roster.units[4 + i]));
    }
    assert(vh_b8_choose(&s) == VH_BINVALID);
}

static void one_ally_two_foes_no_premature_victory(void) {
    VhRoster8 r = adjacent(1, 3, 1);
    VhBattle8 s;
    r.enemy_count = 2;
    r.units[5] = (VhBattleUnit){1, 1, 1, 0};
    assert(vh_r8_valid(&r));
    assert(vh_b8_init(&s, &r, 2, 1));
    attack(&s, 0, 4);
    assert(s.status == VH_BONGOING);
    assert(vh_b8_end_turn(&s) == VH_BEND);
    assert(s.turns_completed == 1);
    assert(s.roster.units[0].acted == 0);
    assert(s.roster.units[5].x == 1 && s.roster.units[5].y == 0);
    attack(&s, 0, 5);
    assert(s.status == VH_BWIN);
}

static void enemy_path_and_defeat_across_turns(void) {
    VhRoster8 r = adjacent(2, 1, 2);
    VhBattle8 s;
    r.enemy_count = 1;
    r.units[5] = (VhBattleUnit){0, 0, 0, 0};
    assert(vh_r8_valid(&r));
    assert(vh_b8_init(&s, &r, 2, 1));
    assert(vh_b8_end_turn(&s) == VH_BEND);
    assert(!vh_balive(&s.roster.units[0]));
    assert(s.status == VH_BONGOING);
    while (s.status == VH_BONGOING && s.turns_completed < 8)
        assert(vh_b8_end_turn(&s) == VH_BEND);
    assert(s.status == VH_BLOSS);
    assert(s.turns_completed > 1 && s.turns_completed < 8);
    assert(!vh_balive(&s.roster.units[1]));
    assert(!vh_balive(&s.roster.units[5]));
}

static void blocked_route_and_real_movement(void) {
    VhRoster8 r = {0};
    VhBattle8 s, before;
    int steps;
    r.ally_count = 3;
    r.enemy_count = 3;
    r.units[0] = (VhBattleUnit){0, 2, 3, 0};
    r.units[1] = (VhBattleUnit){0, 4, 3, 0};
    r.units[2] = (VhBattleUnit){0, 5, 3, 0};
    r.units[4] = (VhBattleUnit){6, 2, 2, 0};
    r.units[5] = (VhBattleUnit){6, 4, 2, 0};
    r.units[6] = (VhBattleUnit){6, 5, 2, 0};
    r.cursor_y = 2;
    r.walls[1] = (1u << 3);
    r.walls[2] = (1u << 3);
    r.walls[3] = (1u << 3);
    assert(vh_r8_valid(&r));
    assert(vh_b8_init(&s, &r, 2, 1));
    steps = vh_b8_path(&s, 0, 6, 2, 4, NULL, NULL);
    assert(steps > s.move_range);
    assert(vh_b8_path(&s, 0, 3, 2, -1, NULL, NULL) == -1);
    assert(vh_b8_choose(&s) == VH_BSELECT);
    assert(vh_b8_cancel(&s) == VH_BCANCEL);
    assert(vh_b8_choose(&s) == VH_BSELECT);
    before = s;
    s.roster.cursor_x = 4;
    assert(vh_b8_choose(&s) == VH_BINVALID);
    assert(s.roster.units[0].x == before.roster.units[0].x);
    assert(s.roster.units[0].acted == before.roster.units[0].acted);
    s.roster.cursor_x = 2;
    assert(vh_b8_choose(&s) == VH_BMOVE);
    assert(s.roster.units[0].x == 2 && s.roster.units[0].y == 2);
    assert(s.roster.units[0].acted == 1);
    assert(vh_b8_end_turn(&s) == VH_BEND);
    assert(s.turns_completed == 1);
    assert(!s.roster.units[0].acted);
}

static void invalid_init_cannot_mutate_live_game(void) {
    VhRoster8 r = adjacent(3, 3, 2);
    VhBattle8 s, before;
    assert(vh_b8_init(&s, &r, 2, 1));
    before = s;
#define REJECT() do { assert(!vh_b8_init(&s, &r, 2, 1)); \
    assert(memcmp(&s, &before, sizeof(s)) == 0); \
    r = adjacent(3, 3, 2); } while (0)
    r.ally_count = 0; REJECT();
    r.enemy_count = 5; REJECT();
    r.units[3].hp = 1; REJECT();
    r.units[7].x = 1; REJECT();
    r.units[4].x = 0; REJECT();
    r.cursor_x = 7; REJECT();
#undef REJECT
    assert(!vh_b8_init(&s, &r, 0, 1));
    assert(memcmp(&s, &before, sizeof(s)) == 0);
    assert(!vh_b8_init(&s, &r, 2, 21));
    assert(memcmp(&s, &before, sizeof(s)) == 0);
    assert(!vh_b8_init(&s, NULL, 2, 1));
    assert(memcmp(&s, &before, sizeof(s)) == 0);
    assert(!vh_b8_init(NULL, &r, 2, 1));
}

int main(void) {
    four_allies_defeat_four_opponents();
    four_opponents_defeat_four_allies();
    one_ally_two_foes_no_premature_victory();
    enemy_path_and_defeat_across_turns();
    blocked_route_and_real_movement();
    invalid_init_cannot_mutate_live_game();
    puts("VH_MAP02_BATTLE8_PASS slots=8 ally_victory=4 enemy_defeat=4 "
         "multi_turn=1 pathfinding=1 no_mutation=1 switch_integration=0");
    return 0;
}
