/*
 * Portability and state-safety contract for an opt-in 4+4 tactical roster.
 * This test is not a claim that NeXium currently runs the 8-unit game.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_roster8.h"

static VhRoster8 authored(int n) {
    VhRoster8 r = {0};
    int i;
    r.ally_count = n;
    r.enemy_count = n;
    r.cursor_x = 0;
    r.cursor_y = 0;
    for (i = 0; i < n; ++i) {
        r.units[i] = (VhBattleUnit){0, i, 1, 0};
        r.units[VH_R8_SIDE_CAP + i] = (VhBattleUnit){1, i, 1, 0};
    }
    return r;
}

static void legacy_translation_preserves_both_authored_maps(void) {
    VhRoster8 r, before;
    VhBattleScenario bad;
    int scene, i;
    for (scene = 0; scene < VH_BSCENARIOS; ++scene) {
        const VhBattleScenario *cfg = vh_bscenario_by_index(scene);
        assert(vh_r8_from_legacy(&r, cfg));
        assert(vh_r8_valid(&r));
        assert(r.ally_count == 2 && r.enemy_count == 2);
        assert(r.cursor_x == cfg->cursor_x && r.cursor_y == cfg->cursor_y);
        assert(memcmp(r.walls, cfg->walls, sizeof(r.walls)) == 0);
        for (i = 0; i < 2; ++i) {
            assert(memcmp(&r.units[i], &cfg->spawn[i],
                          sizeof(VhBattleUnit)) == 0);
            assert(memcmp(&r.units[4 + i], &cfg->spawn[2 + i],
                          sizeof(VhBattleUnit)) == 0);
        }
        for (i = 2; i < 4; ++i) {
            const VhBattleUnit zero = {0, 0, 0, 0};
            assert(memcmp(&r.units[i], &zero, sizeof(zero)) == 0);
            assert(memcmp(&r.units[4 + i], &zero, sizeof(zero)) == 0);
        }
        assert(vh_r8_alive(&r, 0) == 2 && vh_r8_alive(&r, 1) == 2);
    }
    before = r;
    bad = VH_MAP02_DEFAULT_SCENARIO;
    bad.enemy_count = 0;
    assert(!vh_r8_from_legacy(&r, &bad));
    assert(memcmp(&r, &before, sizeof(r)) == 0);
    assert(!vh_r8_from_legacy(&r, NULL));
    assert(memcmp(&r, &before, sizeof(r)) == 0);
    assert(!vh_r8_from_legacy(NULL, &VH_MAP02_DEFAULT_SCENARIO));
}

static void three_vs_three_legitimate_attacks(void) {
    VhRoster8 r = authored(3);
    int i;
    assert(vh_r8_valid(&r));
    assert(vh_r8_index(0, 3) == 3 && vh_r8_index(1, 3) == 7);
    assert(vh_r8_index(2, 0) == -1 && vh_r8_index(0, 4) == -1);
    assert(vh_r8_occupant(&r, 1, 0) == 4);
    assert(vh_r8_occupant(&r, 0, 2) == 2);
    assert(vh_r8_occupant(&r, 1, 3) == -1);
    assert(vh_r8_result(&r) == VH_BONGOING);
    for (i = 0; i < 3; ++i) {
        assert(vh_r8_attack(&r, i, 4 + i, 1));
        assert(!vh_r8_attack(&r, i, 4 + i, 1));
        assert(vh_r8_occupant(&r, 1, i) == -1);
        assert(vh_r8_result(&r) == (i == 2 ? VH_BWIN : VH_BONGOING));
    }
    assert(vh_r8_alive(&r, 0) == 3);
    assert(vh_r8_alive(&r, 1) == 0);
    assert(!vh_r8_attack(&r, 3, 7, 1)); /* hidden slots remain inert */
    vh_r8_reset_actions(&r, 0);
    assert(!r.units[0].acted && !r.units[1].acted && !r.units[2].acted);
}

static void four_vs_four_enemy_caused_defeat(void) {
    VhRoster8 r = authored(4);
    int i;
    assert(vh_r8_valid(&r));
    assert(vh_r8_alive(&r, 0) == 4 && vh_r8_alive(&r, 1) == 4);
    assert(vh_r8_occupant(&r, 1, 3) == 7);
    for (i = 0; i < 4; ++i) {
        assert(vh_r8_attack(&r, 4 + i, i, 1));
        assert(vh_r8_result(&r) == (i == 3 ? VH_BLOSS : VH_BONGOING));
        assert(!vh_r8_attack(&r, 4 + i, i, 1));
    }
    assert(vh_r8_alive(&r, 0) == 0);
    assert(vh_r8_alive(&r, 1) == 4);
    assert(vh_r8_occupant(&r, 0, 3) == -1);
}

static void forged_rosters_are_rejected(void) {
    VhRoster8 r = authored(3);
#define BAD(expression) do { VhRoster8 b = r; expression; \
    assert(!vh_r8_valid(&b)); } while (0)
    BAD(b.ally_count = 0);
    BAD(b.enemy_count = 5);
    BAD(b.units[3].hp = 1);            /* hidden allied reinforcement */
    BAD(b.units[7].acted = 1);         /* hidden enemy action */
    BAD(b.units[4].x = 0);             /* overlapping enemies and allies */
    BAD(b.units[1].y = 6);             /* outside grid */
    BAD(b.walls[0] = 1u);              /* hero on wall */
    BAD(b.cursor_x = 7);               /* cursor does not match first ally */
    BAD(b.units[0].acted = 1);         /* spawn must be fresh */
#undef BAD
    assert(vh_r8_valid(&r));
    assert(vh_r8_result(NULL) == VH_R8_INVALID_STATUS);
    {
        VhRoster8 before = r;
        assert(!vh_r8_attack(&r, 0, 1, 1)); /* no friendly fire */
        assert(!vh_r8_attack(&r, 0, 4, 0));
        assert(memcmp(&before, &r, sizeof(r)) == 0);
    }
    assert(!vh_r8_attack(&r, 0, 6, 1)); /* not adjacent */
    assert(!vh_r8_attack(&r, 3, 4, 1)); /* forged hidden ally */
    assert(!vh_r8_attack(&r, 4, 7, 1)); /* forged hidden enemy */
    assert(vh_r8_result(&r) == VH_BONGOING);
}

int main(void) {
    legacy_translation_preserves_both_authored_maps();
    three_vs_three_legitimate_attacks();
    four_vs_four_enemy_caused_defeat();
    forged_rosters_are_rejected();
    puts("VH_MAP02_ROSTER8_PASS max_allies=4 max_enemies=4 legacy_scenes=2 "
         "three_vs_three=1 four_vs_four=1 hidden_rejection=1 retail=0");
    return 0;
}
