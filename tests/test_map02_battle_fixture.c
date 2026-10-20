#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_battle_fixture.h"

static void test_fixture_initialization(void) {
    VhMap02Battle s;
    int i;
    vh_binit(&s);
    assert(s.status == VH_BONGOING && s.turns_completed == 0);
    assert(s.selected == -1 && s.cursor_x == 1 && s.cursor_y == 2);
    assert(s.units[0].x == 1 && s.units[0].y == 2);
    assert(s.units[1].x == 1 && s.units[1].y == 4);
    assert(s.units[2].x == 5 && s.units[2].y == 2);
    assert(s.units[3].x == 6 && s.units[3].y == 4);
    for (i = 0; i < VH_BUNITS; ++i) {
        assert(s.units[i].hp > 0);
        assert(vh_btile_inside(s.units[i].x, s.units[i].y));
        assert(!vh_bwall(s.units[i].x, s.units[i].y));
        assert(vh_boccupant(&s, s.units[i].x, s.units[i].y, -1) == i);
    }
    assert(vh_bwall(3, 1) && vh_bwall(3, 2) && vh_bwall(3, 3));
    assert(!vh_bwall(3, 0));
    assert(vh_bwall(4, 4));
}

static void test_no_shortcuts_through_obstacles_or_units(void) {
    VhMap02Battle s;
    int distance;
    vh_binit(&s);
    assert(vh_bpath(&s, 0, 3, 2, -1, NULL, NULL) == -1);
    assert(vh_bpath(&s, 0, 1, 4, -1, NULL, NULL) == -1);
    assert(vh_bpath(&s, 0, -1, 3, -1, NULL, NULL) == -1);
    assert(vh_bpath(&s, 0, 5, 2, -1, NULL, NULL) == -1);
    distance = vh_bpath(&s, 0, 5, 2, 2, NULL, NULL);
    assert(distance > 4); /* wall forces a true detour, not Manhattan leap */
    assert(vh_bpath(&s, 0, 2, 2, -1, NULL, NULL) == 1);
}

static void test_player_movement_and_actions(void) {
    VhMap02Battle s;
    vh_binit(&s);
    assert(vh_bchoose(&s) == VH_BSELECT);
    s.cursor_x = 3; s.cursor_y = 2;
    assert(vh_bchoose(&s) == VH_BINVALID); /* wall */
    assert(s.selected == 0 && !s.units[0].acted);
    s.cursor_x = 5; s.cursor_y = 2;
    assert(vh_bchoose(&s) == VH_BINVALID); /* enemy occupied and far */
    assert(s.units[2].hp == 2 && s.selected == 0);
    s.cursor_x = 2; s.cursor_y = 2;
    assert(vh_bchoose(&s) == VH_BMOVE);
    assert(s.units[0].x == 2 && s.units[0].y == 2 && s.units[0].acted);
    assert(s.selected == -1);
    s.cursor_x = 2; s.cursor_y = 2;
    assert(vh_bchoose(&s) == VH_BINVALID); /* acted unit */
    s.cursor_x = 1; s.cursor_y = 4;
    assert(vh_bchoose(&s) == VH_BSELECT && s.selected == 1);
    assert(vh_bcancel(&s) == VH_BCANCEL);
    assert(s.selected == -1 && !s.units[1].acted);
    assert(vh_bchoose(&s) == VH_BSELECT);
    s.cursor_x = 2; s.cursor_y = 4;
    assert(vh_bchoose(&s) == VH_BMOVE);
    assert(s.units[1].x == 2 && s.units[1].y == 4 && s.units[1].acted);
    assert(vh_bchoose(&s) == VH_BINVALID);
}

static void test_enemy_turn_and_replay_determinism(void) {
    VhMap02Battle a, b;
    int step, i;
    vh_binit(&a);
    vh_binit(&b);
    for (step = 0; step < 5; ++step) {
        if (step == 0) {
            assert(vh_bchoose(&a) == VH_BSELECT);
            assert(vh_bchoose(&b) == VH_BSELECT);
            vh_bcursor(&a, 1, 0); vh_bcursor(&b, 1, 0);
            assert(vh_bchoose(&a) == VH_BMOVE && vh_bchoose(&b) == VH_BMOVE);
        } else if (step == 1) {
            a.cursor_x = b.cursor_x = 1;
            a.cursor_y = b.cursor_y = 4;
            assert(vh_bchoose(&a) == VH_BSELECT && vh_bchoose(&b) == VH_BSELECT);
            vh_bcursor(&a, 1, 0); vh_bcursor(&b, 1, 0);
            assert(vh_bchoose(&a) == VH_BMOVE && vh_bchoose(&b) == VH_BMOVE);
        } else {
            assert(vh_bend_turn(&a) == VH_BEND);
            assert(vh_bend_turn(&b) == VH_BEND);
        }
        assert(memcmp(&a, &b, sizeof(a)) == 0);
    }
    assert(a.turns_completed == 3);
    assert(!a.units[0].acted && !a.units[1].acted);
    assert(a.selected == -1);
    for (i = 0; i < VH_BUNITS; ++i) {
        assert(vh_btile_inside(a.units[i].x, a.units[i].y));
        assert(!vh_bwall(a.units[i].x, a.units[i].y));
    }
}

static void test_valid_adjacent_attack_and_victory(void) {
    VhMap02Battle s;
    vh_binit(&s);
    s.units[0].x = 4; s.units[0].y = 2;
    s.units[2].hp = 1;
    s.units[3].hp = 0;
    s.cursor_x = 4; s.cursor_y = 2;
    assert(vh_bchoose(&s) == VH_BSELECT);
    s.cursor_x = 5; s.cursor_y = 2;
    assert(vh_bchoose(&s) == VH_BATTACK);
    assert(!vh_balive(&s.units[2]));
    assert(s.status == VH_BWIN);
    assert(vh_bchoose(&s) == VH_BINVALID);
    assert(vh_bend_turn(&s) == VH_BINVALID);
    vh_binit(&s);
    assert(s.status == VH_BONGOING); /* reproducible reset */
}

static void test_enemy_attack_and_defeat(void) {
    VhMap02Battle s;
    vh_binit(&s);
    s.units[0].x = 5; s.units[0].y = 1; s.units[0].hp = 1;
    s.units[1].x = 6; s.units[1].y = 3; s.units[1].hp = 1;
    assert(vh_bend_turn(&s) == VH_BEND);
    assert(!vh_balive(&s.units[0]) && !vh_balive(&s.units[1]));
    assert(s.status == VH_BLOSS);
    assert(vh_bchoose(&s) == VH_BINVALID);
    assert(vh_bcancel(&s) == VH_BINVALID);
    assert(vh_bend_turn(&s) == VH_BINVALID);
}

static void test_enemy_movement_respects_walls(void) {
    VhMap02Battle s;
    int cycle, u;
    vh_binit(&s);
    for (cycle = 0; cycle < 12 && s.status == VH_BONGOING; ++cycle) {
        assert(vh_bend_turn(&s) == VH_BEND);
        for (u = 0; u < VH_BUNITS; ++u) {
            assert(vh_btile_inside(s.units[u].x, s.units[u].y));
            assert(!vh_bwall(s.units[u].x, s.units[u].y));
            if (vh_balive(&s.units[u]))
                assert(vh_boccupant(&s, s.units[u].x, s.units[u].y, -1) == u);
        }
    }
    assert(s.turns_completed > 0);
}

int main(void) {
    test_fixture_initialization();
    test_no_shortcuts_through_obstacles_or_units();
    test_player_movement_and_actions();
    test_enemy_turn_and_replay_determinism();
    test_valid_adjacent_attack_and_victory();
    test_enemy_attack_and_defeat();
    test_enemy_movement_respects_walls();
    puts("MAP02 asset-free playable battle fixture: all deterministic host tests passed.");
    return 0;
}
