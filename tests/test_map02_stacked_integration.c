/*
 * Final-stage combined tactical interaction without original retail assets.
 * This is a host-only preflight against the exact C headers compiled by libnx.
 * The existing real NeXium evidence remains the definitive controller proof.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_roster8_variants.h"
#include "../source/map02_ranged8.h"
#include "../source/map02_medic8.h"
#include "../source/map02_guard8.h"
#include "../source/map02_guard_hud.h"

static void same_roster_fields(const VhRoster8 *a, const VhRoster8 *b) {
    int i;
    assert(a->ally_count == b->ally_count);
    assert(a->enemy_count == b->enemy_count);
    assert(a->cursor_x == b->cursor_x);
    assert(a->cursor_y == b->cursor_y);
    for (i = 0; i < VH_BH; ++i)
        assert(a->walls[i] == b->walls[i]);
    for (i = 0; i < VH_R8_CAPACITY; ++i) {
        assert(a->units[i].x == b->units[i].x);
        assert(a->units[i].y == b->units[i].y);
        assert(a->units[i].hp == b->units[i].hp);
        assert(a->units[i].acted == b->units[i].acted);
    }
}

static void all_six_variants(void) {
    int scene, variant;
    for (scene = 0; scene < VH_R8_SCENES; ++scene) {
        for (variant = 0; variant < VH_R8_VARIANTS; ++variant) {
            VhBattle8 game;
            VhGuard8 guard = {0};
            int expected_allies = variant == 0 ? 4 :
                                  variant == 1 ? 3 : 1;
            assert(vh_b8_init_scene_variant(&game, scene, variant));
            assert(vh_r8_alive(&game.roster, 0) == expected_allies);
            assert(vh_r8_alive(&game.roster, 1) ==
                   (variant == 1 ? 3 : 4));
            assert(vh_b8_guard_hud_state(&game, &guard, scene) ==
                   (scene == 0 ? VH_GHUD_HIDDEN :
                    variant == 2 ? VH_GHUD_UNAVAILABLE : VH_GHUD_READY));
            assert(vh_r8_valid(&game.roster));
            assert(!vh_b8_clear_shot(&game, 0, 4, 3) ||
                   game.roster.units[4].hp > 0);
            assert(vh_b8_init_scene_variant(&game, scene, variant));
        }
    }
}

static void guard_plus_medic_plus_bow_same_fixture(void) {
    VhBattle8 battle, before;
    VhGuard8 guard = {0};
    int i;
    assert(vh_b8_init_scene_variant(&battle, 1, 0));

    /* Ranged shot at enemy four squares away is invalid, non-mutating. */
    assert(vh_b8_choose(&battle) == VH_BSELECT);
    battle.roster.cursor_x = 5;
    before = battle;
    assert(vh_b8_shoot(&battle) == VH_BINVALID);
    assert(memcmp(&battle, &before, sizeof(battle)) == 0);
    assert(vh_b8_cancel(&battle) == VH_BCANCEL);

    /* Three actual enemy pursuit turns set up a reproducible attack. */
    for (i = 0; i < 3; ++i)
        assert(vh_b8_end_turn(&battle) == VH_BEND);
    assert(battle.roster.units[0].hp == 3);

    /* Third ally spends an action to reduce the first incoming enemy hit. */
    battle.roster.cursor_x = battle.roster.units[2].x;
    battle.roster.cursor_y = battle.roster.units[2].y;
    assert(vh_b8_choose(&battle) == VH_BSELECT);
    assert(vh_b8_guard_action(&battle, &guard) == VH_BGUARD);
    assert(vh_b8_guard_hud_state(&battle, &guard, 1) == VH_GHUD_ARMED);
    assert(vh_b8_end_turn_guarded(&battle, &guard) == VH_BEND);
    assert(guard.absorbed_last_turn == 1);
    assert(battle.roster.units[0].hp == 2);
    assert(vh_b8_guard_hud_state(&battle, &guard, 1) == VH_GHUD_BLOCKED);

    /* Second ally repairs the actual enemy damage in the same battle. */
    battle.roster.cursor_x = battle.roster.units[1].x;
    battle.roster.cursor_y = battle.roster.units[1].y;
    assert(vh_b8_choose(&battle) == VH_BSELECT);
    battle.roster.cursor_x = battle.roster.units[0].x;
    battle.roster.cursor_y = battle.roster.units[0].y;
    assert(vh_b8_heal(&battle) == VH_BHEAL);
    assert(battle.roster.units[0].hp == 3);
    assert(battle.roster.units[1].acted == 1);

    /* Reset clears all extra battle state and leaves fixture untouched. */
    assert(vh_b8_init_scene_variant(&battle, 1, 0));
    vh_b8_guard_reset(&guard);
    assert(vh_b8_guard_hud_state(&battle, &guard, 1) == VH_GHUD_READY);
    assert(battle.roster.units[0].hp == 3);
    assert(battle.roster.units[4].hp == 2);
    same_roster_fields(&battle.roster, &VH_MAP02_ROSTER8_SECOND);
}

static void old_scene_and_padding_unchanged(void) {
    VhBattle8 b;
    VhRoster8 r;
    int i;
    assert(vh_r8_scene_variant(&r, 0, 0));
    same_roster_fields(&r, &VH_MAP02_ROSTER8_SMOKE);
    assert(vh_b8_init_scene_variant(&b, 0, 0));
    assert(vh_b8_choose(&b) == VH_BSELECT);
    b.roster.cursor_x = 1;
    assert(vh_b8_choose(&b) == VH_BATTACK);
    assert(b.roster.units[4].hp == 0);
    for (i = 0; i < 2; ++i) {
        assert(vh_b8_init_scene_variant(&b, 1, i));
        assert(vh_r8_valid(&b.roster));
    }
    assert(vh_b8_init_scene_variant(&b, 1, 2));
    assert(!vh_r8_active(&b.roster, VH_B8_MEDIC_SLOT));
    assert(!vh_r8_active(&b.roster, VH_B8_GUARD_SLOT));
}

int main(void) {
    all_six_variants();
    guard_plus_medic_plus_bow_same_fixture();
    old_scene_and_padding_unchanged();
    puts("VH_MAP02_STACK_NATIVE_PASS rosters=6 bow=1 medic=1 guard=1 "
         "original_scene=1 zero_retail=1");
    return 0;
}
