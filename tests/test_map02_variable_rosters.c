/*
 * Variable active troop rosters within the current fixed four-slot 8x6 engine.
 * All operations use the same APIs as libnx NRO; no retail game data.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_battle_fixture.h"

static VhBattleScenario one_on_one(void) {
    VhBattleScenario data = VH_MAP02_DEFAULT_SCENARIO;
    data.ally_count = 1;
    data.enemy_count = 1;
    data.spawn[1] = (VhBattleUnit){0, 0, 0, 0};
    data.spawn[2] = (VhBattleUnit){2, 2, 1, 0};
    data.spawn[3] = (VhBattleUnit){0, 0, 0, 0};
    return data;
}

static void test_one_ally_one_enemy_legitimate_victory(void) {
    VhBattleScenario cfg = one_on_one();
    VhMap02Battle battle;
    assert(vh_bscenario_valid(&cfg));
    assert(vh_binit_scenario(&battle, &cfg));
    assert(battle.ally_count == 1 && battle.enemy_count == 1);
    assert(!vh_balive(&battle.units[1]) && !vh_balive(&battle.units[3]));
    assert(vh_boccupant(&battle, 0, 0, -1) == -1);
    assert(vh_bchoose(&battle) == VH_BSELECT);
    battle.cursor_x = 2;
    battle.cursor_y = 2;
    assert(vh_bchoose(&battle) == VH_BATTACK);
    assert(!vh_balive(&battle.units[2]));
    assert(battle.status == VH_BWIN);
    assert(vh_bend_turn(&battle) == VH_BINVALID);
    assert(vh_binit_scenario(&battle, &cfg));
    assert(battle.status == VH_BONGOING && battle.selected == -1);
}

static void test_one_ally_two_enemies_turn_and_no_premature_victory(void) {
    VhBattleScenario cfg = one_on_one();
    VhMap02Battle battle;
    cfg.enemy_count = 2;
    cfg.spawn[3] = (VhBattleUnit){6, 4, 2, 0};
    assert(vh_binit_scenario(&battle, &cfg));
    assert(vh_bchoose(&battle) == VH_BSELECT);
    battle.cursor_x = 2;
    battle.cursor_y = 2;
    assert(vh_bchoose(&battle) == VH_BATTACK);
    assert(battle.status == VH_BONGOING); /* still one enemy */
    assert(vh_bend_turn(&battle) == VH_BEND);
    assert(!battle.units[0].acted && battle.turns_completed == 1);
    assert(battle.units[1].hp == 0 && battle.units[1].acted == 0);
    assert(battle.units[3].hp == 2);
}

static void test_two_allies_one_enemy_defeat_and_reset(void) {
    VhBattleScenario cfg = VH_MAP02_DEFAULT_SCENARIO;
    VhMap02Battle battle;
    cfg.enemy_count = 1;
    cfg.spawn[3] = (VhBattleUnit){0, 0, 0, 0};
    cfg.spawn[2] = (VhBattleUnit){5, 2, 1, 0};
    assert(vh_binit_scenario(&battle, &cfg));
    assert(battle.ally_count == 2 && battle.enemy_count == 1);
    assert(vh_bchoose(&battle) == VH_BSELECT);
    battle.cursor_x = 2;
    battle.cursor_y = 2;
    assert(vh_bchoose(&battle) == VH_BMOVE);
    assert(battle.units[0].acted);
    assert(vh_bend_turn(&battle) == VH_BEND);
    assert(!battle.units[0].acted && !battle.units[1].acted);
    battle.units[0].hp = 0;
    battle.units[1].hp = 0;
    vh_bupdate_status(&battle);
    assert(battle.status == VH_BLOSS);
    assert(vh_binit_scenario(&battle, &cfg));
    assert(battle.status == VH_BONGOING);
    assert(battle.units[3].hp == 0);
}

static void test_invalid_counts_or_nonzero_padding_do_not_mutate_state(void) {
    VhBattleScenario cfg = one_on_one();
    VhMap02Battle state, before;
    assert(vh_binit_scenario(&state, &cfg));
    before = state;
#define REJECT() do { \
    assert(!vh_bscenario_valid(&cfg)); \
    assert(!vh_binit_scenario(&state, &cfg)); \
    assert(memcmp(&state, &before, sizeof(state)) == 0); \
    cfg = one_on_one(); \
} while (0)
    cfg.ally_count = 0; REJECT();
    cfg.ally_count = 3; REJECT();
    cfg.enemy_count = 0; REJECT();
    cfg.enemy_count = 3; REJECT();
    cfg.spawn[1].hp = 1; REJECT();
    cfg.spawn[1].x = 1; REJECT();
    cfg.spawn[3].acted = 1; REJECT();
    cfg.spawn[3].y = 4; REJECT();
    cfg.cursor_x = 0; REJECT();
#undef REJECT
}

int main(void) {
    test_one_ally_one_enemy_legitimate_victory();
    test_one_ally_two_enemies_turn_and_no_premature_victory();
    test_two_allies_one_enemy_defeat_and_reset();
    test_invalid_counts_or_nonzero_padding_do_not_mutate_state();
    puts("VH_MAP02_VARIABLE_ROSTERS_PASS combinations=4 alternate_victory=1 "
         "enemy_phase=1 defeat=1 corrupted_rejections=9 original_retail=0");
    return 0;
}
