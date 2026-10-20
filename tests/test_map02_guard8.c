/* Original-data-free squad-guard and medic cooperation verification. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_roster8_variants.h"
#include "../source/map02_guard8.h"
#include "../source/map02_medic8.h"
#include "../source/map02_ranged8.h"

static void same(const VhBattle8 *a, const VhBattle8 *b) {
    assert(memcmp(a, b, sizeof(*a)) == 0);
}

static void invalid_guard_has_no_effect(void) {
    VhBattle8 b, previous;
    VhGuard8 guard = {0}, old;
    assert(vh_b8_init_scene_variant(&b, 1, 0));
    previous = b;
    assert(vh_b8_guard_action(&b, &guard) == VH_BINVALID);
    same(&b, &previous);
    assert(!guard.active && !guard.absorbed_last_turn);

    b.roster.cursor_x = 1; b.roster.cursor_y = 2;
    assert(vh_b8_choose(&b) == VH_BSELECT);
    assert(b.selected == VH_B8_GUARD_SLOT);
    b.roster.cursor_y = 1;
    previous = b; old = guard;
    assert(vh_b8_guard_action(&b, &guard) == VH_BINVALID);
    same(&b, &previous);
    assert(memcmp(&guard, &old, sizeof(old)) == 0);
    b.roster.cursor_y = 2;
    assert(vh_b8_guard_action(&b, &guard) == VH_BGUARD);
    assert(guard.active && !guard.absorbed_last_turn);
    assert(b.roster.units[2].acted == 1 && b.selected == -1);
    previous = b; old = guard;
    assert(vh_b8_guard_action(&b, &guard) == VH_BINVALID);
    same(&b, &previous);
    assert(memcmp(&guard, &old, sizeof(old)) == 0);

    assert(vh_b8_end_turn_guarded(&b, &guard) == VH_BEND);
    assert(!guard.active && !guard.absorbed_last_turn);
    assert(!b.roster.units[2].acted); /* all flags reset at turn end */
    assert(vh_b8_init_scene_variant(&b, 1, 2));
    previous = b;
    assert(vh_b8_guard_action(&b, &guard) == VH_BINVALID);
    same(&b, &previous);
    assert(vh_b8_guard_action(NULL, &guard) == VH_BINVALID);
    assert(vh_b8_guard_action(&b, NULL) == VH_BINVALID);
    assert(vh_b8_end_turn_guarded(NULL, &guard) == VH_BINVALID);
    assert(vh_b8_end_turn_guarded(&b, NULL) == VH_BINVALID);
    vh_b8_guard_reset(&guard);
    assert(guard.active == 0 && guard.absorbed_last_turn == 0);
    vh_b8_guard_reset(NULL);
}

static void shield_during_real_enemy_attack(void) {
    VhBattle8 baseline, shielded, after_first;
    VhGuard8 g = {0};
    int i;
    assert(vh_b8_init_scene_variant(&baseline, 1, 0));
    for (i = 0; i < 3; ++i)
        assert(vh_b8_end_turn(&baseline) == VH_BEND);
    assert(baseline.roster.units[0].hp == 3);
    assert(vh_balive(&baseline.roster.units[2]));
    shielded = baseline;
    shielded.roster.cursor_x = shielded.roster.units[2].x;
    shielded.roster.cursor_y = shielded.roster.units[2].y;
    assert(vh_b8_choose(&shielded) == VH_BSELECT);
    assert(vh_b8_guard_action(&shielded, &g) == VH_BGUARD);
    assert(g.active && shielded.roster.units[2].acted);

    assert(vh_b8_end_turn(&baseline) == VH_BEND);
    assert(vh_b8_end_turn_guarded(&shielded, &g) == VH_BEND);
    assert(baseline.roster.units[0].hp == 1);
    assert(shielded.roster.units[0].hp == 2);
    assert(!g.active && g.absorbed_last_turn == 1);
    assert(shielded.roster.units[1].hp == baseline.roster.units[1].hp);
    assert(shielded.roster.units[2].hp == baseline.roster.units[2].hp);
    assert(shielded.roster.units[0].x == baseline.roster.units[0].x);
    assert(shielded.roster.units[0].y == baseline.roster.units[0].y);
    for (i = 4; i < 8; ++i)
        assert(memcmp(&shielded.roster.units[i],
                      &baseline.roster.units[i],
                      sizeof(VhBattleUnit)) == 0);
    assert(shielded.turns_completed == baseline.turns_completed);
    assert(shielded.status == VH_BONGOING);
    after_first = shielded;
    /* Medic (ally #2) may now heal the actual victim of the guarded hit. */
    shielded.roster.cursor_x = shielded.roster.units[1].x;
    shielded.roster.cursor_y = shielded.roster.units[1].y;
    assert(vh_b8_choose(&shielded) == VH_BSELECT);
    shielded.roster.cursor_x = shielded.roster.units[0].x;
    shielded.roster.cursor_y = shielded.roster.units[0].y;
    assert(vh_b8_heal(&shielded) == VH_BHEAL);
    assert(shielded.roster.units[0].hp == 3);
    assert(shielded.roster.units[1].acted);
    assert(after_first.roster.units[0].hp == 2);
    assert(vh_b8_init_scene_variant(&shielded, 1, 0));
    vh_b8_guard_reset(&g);
    assert(shielded.roster.units[0].hp == 3);
    assert(shielded.roster.units[2].acted == 0);
    assert(g.absorbed_last_turn == 0);
    printf("VH_MAP02_GUARD_AI_DAMAGE regular_hp=%d shielded_hp=%d healed_hp=%d\n",
           baseline.roster.units[0].hp, after_first.roster.units[0].hp,
           shielded.roster.units[0].hp);
}

static void default_engine_is_unchanged_without_stance(void) {
    VhBattle8 standard, guarded;
    VhGuard8 shield = {0};
    VhRoster8 a, b;
    int i;
    assert(vh_b8_init_scene_variant(&standard, 1, 0));
    guarded = standard;
    for (i = 0; i < 6 && standard.status == VH_BONGOING; ++i) {
        assert(vh_b8_end_turn(&standard) == VH_BEND);
        assert(vh_b8_end_turn_guarded(&guarded, &shield) == VH_BEND);
        same(&standard, &guarded);
        assert(shield.active == 0 && shield.absorbed_last_turn == 0);
    }
    assert(vh_r8_scene_variant(&a, 0, 0));
    assert(vh_r8_scene_variant(&b, 1, 0));
    assert(memcmp(&a, &VH_MAP02_ROSTER8_SMOKE, sizeof(a)) == 0);
    assert(memcmp(&b, &VH_MAP02_ROSTER8_SECOND, sizeof(b)) == 0);
}

int main(void) {
    invalid_guard_has_no_effect();
    shield_during_real_enemy_attack();
    default_engine_is_unchanged_without_stance();
    puts("VH_MAP02_GUARD_PASS third_ally=1 squad_first_hit=1 "
         "damage_reduced=1 medic_followup=1 guard_expires=1 "
         "unused_ai_parity=1 invalid_no_mutation=1 originals=1");
    return 0;
}
