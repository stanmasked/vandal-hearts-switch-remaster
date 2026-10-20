/*
 * Independent host tests for an authored, data-driven MAP02 encounter.
 * Default scene must retain the exact formerly hard-coded five-turn layout.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_battle_fixture.h"

static void test_checked_in_fixture_matches_prior_gameplay(void) {
    VhMap02Battle scene, reset;
    assert(vh_bscenario_valid(&VH_MAP02_DEFAULT_SCENARIO));
    vh_binit(&scene);
    assert(scene.selected == -1 && scene.status == VH_BONGOING);
    assert(scene.units[0].x == 1 && scene.units[0].y == 2 && scene.units[0].hp == 5);
    assert(scene.units[1].x == 1 && scene.units[1].y == 4 && scene.units[1].hp == 5);
    assert(scene.units[2].x == 5 && scene.units[2].y == 2 && scene.units[2].hp == 2);
    assert(scene.units[3].x == 6 && scene.units[3].y == 4 && scene.units[3].hp == 2);
    assert(scene.cursor_x == 1 && scene.cursor_y == 2);
    assert(scene.move_range == 2 && scene.attack_damage == 1);
    assert(scene.event_count == 2);
    assert(vh_bwall_at(&scene, 3, 1));
    assert(vh_bwall_at(&scene, 3, 2));
    assert(vh_bwall_at(&scene, 3, 3));
    assert(vh_bwall_at(&scene, 4, 4));
    assert(!vh_bwall_at(&scene, 3, 0));
    assert(vh_bwall(3, 2) && !vh_bwall(3, 0));
    vh_binit(&reset);
    assert(memcmp(&scene, &reset, sizeof(scene)) == 0);
}

static void test_distinct_data_alters_actual_terrain_movement_and_damage(void) {
    VhBattleScenario custom = VH_MAP02_DEFAULT_SCENARIO;
    VhMap02Battle state;
    custom.walls[2] &= (unsigned char)~(1u << 3);
    custom.walls[0] |= (unsigned char)(1u << 0);
    custom.spawn[0].x = 4; custom.spawn[0].y = 2; custom.spawn[0].hp = 6;
    custom.spawn[1].hp = 7;
    custom.spawn[2].hp = 3;
    custom.cursor_x = 4; custom.cursor_y = 2;
    custom.move_range = 1; custom.attack_damage = 2;
    assert(vh_bscenario_valid(&custom));
    assert(vh_binit_scenario(&state, &custom));
    assert(vh_bwall_at(&state, 0, 0));
    assert(!vh_bwall_at(&state, 3, 2)); /* previously hardcoded wall is gone */
    assert(vh_bwall(3, 2));           /* default-data query is unchanged */
    assert(state.move_range == 1 && state.attack_damage == 2);
    assert(state.units[1].hp == 7 && state.units[2].hp == 3);
    assert(vh_bchoose(&state) == VH_BSELECT);
    state.cursor_x = 5; state.cursor_y = 2;
    assert(vh_bchoose(&state) == VH_BATTACK);
    assert(state.units[2].hp == 1); /* authored 2-damage melee, not fixed 1 */
    assert(state.units[0].acted == 1);
    assert(vh_bcancel(&state) == VH_BINVALID);

    custom.spawn[0].x = 2; custom.spawn[0].y = 2;
    custom.cursor_x = 2; custom.cursor_y = 2;
    assert(vh_binit_scenario(&state, &custom));
    assert(vh_bpath(&state, 0, 3, 2, -1, 0, 0) == 1);
    assert(vh_bchoose(&state) == VH_BSELECT);
    state.cursor_x = 4; state.cursor_y = 2; /* two tiles, range limited to 1 */
    assert(vh_bchoose(&state) == VH_BINVALID);
    assert(state.selected == 0);
    state.cursor_x = 3; state.cursor_y = 2;
    assert(vh_bchoose(&state) == VH_BMOVE);
    assert(state.units[0].x == 3 && state.units[0].y == 2);
}

static void test_authored_win_lose_events_reordered_still_work(void) {
    VhBattleScenario custom = VH_MAP02_DEFAULT_SCENARIO;
    VhBattleEvent swap = custom.events[0];
    VhMap02Battle state;
    custom.events[0] = custom.events[1];
    custom.events[1] = swap;
    assert(vh_binit_scenario(&state, &custom));
    state.units[2].hp = 0;
    state.units[3].hp = 0;
    vh_bupdate_status(&state);
    assert(state.status == VH_BWIN);
    assert(vh_binit_scenario(&state, &custom));
    state.units[0].hp = 0;
    state.units[1].hp = 0;
    vh_bupdate_status(&state);
    assert(state.status == VH_BLOSS);
    assert(vh_binit_scenario(&state, &custom));
    assert(state.status == VH_BONGOING);
}

static void test_invalid_scenes_rejected_without_mutating_game(void) {
    VhBattleScenario invalid = VH_MAP02_DEFAULT_SCENARIO;
    VhMap02Battle state, before;
    vh_binit(&state);
    before = state;
#define REJECT() do { \
    assert(!vh_bscenario_valid(&invalid)); \
    assert(!vh_binit_scenario(&state, &invalid)); \
    assert(memcmp(&state, &before, sizeof(state)) == 0); \
    invalid = VH_MAP02_DEFAULT_SCENARIO; \
} while (0)
    invalid.spawn[1].x = invalid.spawn[0].x;
    invalid.spawn[1].y = invalid.spawn[0].y;
    REJECT();
    invalid.walls[2] |= (unsigned char)(1u << 1); /* ally on wall */
    REJECT();
    invalid.spawn[0].x = 8;
    REJECT();
    invalid.spawn[2].hp = 0;
    REJECT();
    invalid.spawn[0].acted = 1;
    REJECT();
    invalid.cursor_x = -1;
    REJECT();
    invalid.move_range = 0;
    REJECT();
    invalid.attack_damage = 0;
    REJECT();
    invalid.event_count = 1;
    REJECT();
    invalid.events[1] = invalid.events[0]; /* duplicate victory event */
    REJECT();
    invalid.events[1].result = VH_BWIN; /* defeat incorrectly mapped to victory */
    REJECT();
#undef REJECT
}

int main(void) {
    test_checked_in_fixture_matches_prior_gameplay();
    test_distinct_data_alters_actual_terrain_movement_and_damage();
    test_authored_win_lose_events_reordered_still_work();
    test_invalid_scenes_rejected_without_mutating_game();
    puts("VH_MAP02_DATA_DRIVEN_BATTLE_PASS default_unchanged=1 "
         "alternate_map=1 custom_damage=1 events=2 invalid_refusals=10 "
         "original_retail=0");
    return 0;
}
