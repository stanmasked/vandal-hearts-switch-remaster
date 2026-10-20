/* Source-to-gameplay contract for two authored independent 8-slot arenas. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_roster8_variants.h"

static void two_scene_capacity_combinations(void) {
    int scene, variant;
    assert(VH_R8_SCENES == 2 && VH_R8_VARIANTS == 3);
    for (scene = 0; scene < VH_R8_SCENES; ++scene)
        for (variant = 0; variant < VH_R8_VARIANTS; ++variant) {
            VhRoster8 data;
            VhBattle8 state;
            const int allies = variant == 0 ? 4 : variant == 1 ? 3 : 1;
            const int foes = variant == 1 ? 3 : 4;
            int i;
            assert(vh_r8_scene_variant(&data, scene, variant));
            assert(vh_r8_valid(&data));
            assert(vh_b8_init_scene_variant(&state, scene, variant));
            assert(state.roster.ally_count == allies);
            assert(state.roster.enemy_count == foes);
            assert(vh_r8_alive(&state.roster, 0) == allies);
            assert(vh_r8_alive(&state.roster, 1) == foes);
            assert(state.roster.cursor_x == (scene == 0 ? 0 : 1));
            assert(state.roster.cursor_y == 0);
            assert(state.status == VH_BONGOING && state.selected == -1);
            assert(state.turns_completed == 0);
            for (i = allies; i < VH_R8_SIDE_CAP; ++i) {
                const VhBattleUnit z = {0, 0, 0, 0};
                assert(memcmp(&data.units[i], &z, sizeof(z)) == 0);
            }
            for (i = VH_R8_SIDE_CAP + foes; i < VH_R8_CAPACITY; ++i) {
                const VhBattleUnit z = {0, 0, 0, 0};
                assert(memcmp(&data.units[i], &z, sizeof(z)) == 0);
            }
            assert(state.roster.units[4].x == (scene == 0 ? 1 : 5));
            assert(state.roster.units[4].hp == 2);
            /* A reset restores the same scene/capacity and all fresh HP. */
            state.roster.units[0].hp -= 1;
            state.roster.units[4].hp -= 1;
            assert(vh_b8_init_scene_variant(&state, scene, variant));
            assert(state.roster.units[0].hp == 3);
            assert(state.roster.units[4].hp == 2);
        }
}

static void second_arena_pathfinding_real_actions(void) {
    VhBattle8 state;
    int sx, sy;
    assert(vh_b8_init_scene_variant(&state, 1, 0));
    assert(state.roster.walls[1] == 0x08);
    assert(state.roster.walls[2] == 0x08);
    assert(state.roster.walls[3] == 0x18);
    assert(vh_b8_path(&state, 0, 3, 2, -1, 0, 0) == -1);
    assert(vh_b8_choose(&state) == VH_BSELECT);
    state.roster.cursor_x = 2;
    assert(vh_b8_path(&state, 0, 2, 0, -1, 0, 0) == 1);
    assert(vh_b8_choose(&state) == VH_BMOVE);
    assert(state.roster.units[0].x == 2);
    assert(state.roster.units[0].acted == 1);
    assert(vh_b8_path(&state, 4, 2, 0, 0, &sx, &sy) == 3);
    assert(sx == 4 && sy == 0);
    assert(vh_b8_end_turn(&state) == VH_BEND);
    assert(state.roster.units[4].x == 4);
    assert(state.roster.units[4].y == 0);
    assert(state.roster.units[0].acted == 0);
    assert(state.status == VH_BONGOING);
    assert(vh_b8_init_scene_variant(&state, 1, 0));
    assert(state.roster.units[4].x == 5);
    assert(state.roster.units[0].x == 1);
}

static void legacy_primary_unchanged_and_fail_closed(void) {
    VhRoster8 original, second, untouched;
    VhBattle8 game, before;
    assert(vh_r8_variant(&original, 0));
    assert(memcmp(&original, &VH_MAP02_ROSTER8_SMOKE,
                  sizeof(original)) == 0);
    assert(vh_r8_scene_variant(&second, 1, 0));
    assert(memcmp(&second, &VH_MAP02_ROSTER8_SECOND,
                  sizeof(second)) == 0);
    assert(memcmp(&original, &second, sizeof(original)) != 0);
    assert(vh_b8_init_scene_variant(&game, 1, 2));
    before = game;
    assert(!vh_b8_init_scene_variant(&game, 2, 0));
    assert(memcmp(&game, &before, sizeof(game)) == 0);
    assert(!vh_b8_init_scene_variant(&game, -1, 0));
    assert(memcmp(&game, &before, sizeof(game)) == 0);
    assert(!vh_b8_init_scene_variant(&game, 1, 3));
    assert(memcmp(&game, &before, sizeof(game)) == 0);
    assert(!vh_b8_init_scene_variant(&game, 0, -1));
    assert(memcmp(&game, &before, sizeof(game)) == 0);
    assert(!vh_b8_init_scene_variant(NULL, 1, 0));
    untouched = second;
    assert(!vh_r8_scene_variant(&second, 4, 0));
    assert(memcmp(&second, &untouched, sizeof(second)) == 0);
    assert(!vh_r8_scene_variant(&second, 1, 7));
    assert(memcmp(&second, &untouched, sizeof(second)) == 0);
}

int main(void) {
    two_scene_capacity_combinations();
    second_arena_pathfinding_real_actions();
    legacy_primary_unchanged_and_fail_closed();
    puts("VH_MAP02_TWO_EIGHT_ARENAS_PASS arenas=2 sizes=3 combinations=6 "
         "second_path=1 reset=1 preserved_default=1 fail_closed=1 retail=0");
    return 0;
}
