/* Independent native field-medic rules, with no retail game assets. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_roster8_variants.h"
#include "../source/map02_medic8.h"
#include "../source/map02_ranged8.h"

static void check_same(const VhBattle8 *a, const VhBattle8 *b) {
    assert(memcmp(a, b, sizeof(*a)) == 0);
}

static void healing_requires_real_damage_and_valid_target(void) {
    VhBattle8 b, previous;
    assert(vh_b8_init_scene_variant(&b, 1, 0));
    b.roster.cursor_y = 1;
    assert(vh_b8_choose(&b) == VH_BSELECT);
    assert(b.selected == VH_B8_MEDIC_SLOT);
    b.roster.cursor_y = 0;
    previous = b;
    assert(!vh_b8_can_heal(&b, 1, 0)); /* already full */
    assert(vh_b8_heal(&b) == VH_BINVALID);
    check_same(&b, &previous);
    b.roster.units[0].hp = 1;
    assert(vh_b8_can_heal(&b, 1, 0));
    assert(vh_b8_heal(&b) == VH_BHEAL);
    assert(b.roster.units[0].hp == 3);
    assert(b.roster.units[1].acted == 1);
    assert(b.roster.units[1].hp == 3);
    assert(b.status == VH_BONGOING);
    assert(b.selected == -1);
    assert(b.last_action == VH_BHEAL);
    previous = b;
    assert(vh_b8_heal(&b) == VH_BINVALID);
    check_same(&b, &previous);
}

static void support_is_bounded_and_cannot_revive(void) {
    VhBattle8 b, before;
    assert(vh_b8_init_scene_variant(&b, 1, 0));
    b.selected = 1;
    b.roster.cursor_x = 1;
    b.roster.cursor_y = 0;

    b.roster.units[0].hp = 2;
    assert(vh_b8_heal(&b) == VH_BHEAL);
    assert(b.roster.units[0].hp == VH_B8_HEAL_HP_CAP);
    assert(vh_b8_init_scene_variant(&b, 1, 0));
    b.selected = 1;
    b.roster.cursor_y = 0;
    b.roster.units[0].hp = 0;
    before = b;
    assert(vh_b8_heal(&b) == VH_BINVALID);
    check_same(&b, &before);

    b.roster.units[0].hp = 1;
    b.roster.units[1].acted = 1;
    before = b;
    assert(vh_b8_heal(&b) == VH_BINVALID);
    check_same(&b, &before);
    b.roster.units[1].acted = 0;

    b.roster.units[0].x = 0; /* diagonal from (1,1) to (0,0) */
    before = b;
    assert(vh_b8_heal(&b) == VH_BINVALID);
    check_same(&b, &before);
    b.roster.units[0].x = 1;

    b.roster.cursor_y = 1; /* selected medic cannot self-heal */
    before = b;
    assert(vh_b8_heal(&b) == VH_BINVALID);
    check_same(&b, &before);

    b.roster.cursor_x = 5;
    b.roster.cursor_y = 0; /* heal an enemy */
    before = b;
    assert(vh_b8_heal(&b) == VH_BINVALID);
    check_same(&b, &before);

    b.status = VH_BLOSS;
    before = b;
    assert(vh_b8_heal(&b) == VH_BINVALID);
    check_same(&b, &before);
    assert(vh_b8_heal(NULL) == VH_BINVALID);
    assert(!vh_b8_can_heal(NULL, 1, 0));
}

static void padded_rosters_and_original_arena_unchanged(void) {
    VhBattle8 b, before;
    VhRoster8 a, original;
    assert(vh_b8_init_scene_variant(&b, 1, 2));
    assert(!vh_r8_active(&b.roster, VH_B8_MEDIC_SLOT));
    before = b;
    assert(vh_b8_heal(&b) == VH_BINVALID);
    check_same(&b, &before);
    assert(vh_r8_scene_variant(&a, 0, 0));
    original = VH_MAP02_ROSTER8_SMOKE;
    assert(memcmp(&a, &original, sizeof(a)) == 0);
    assert(vh_b8_init_scene_variant(&b, 1, 0));
    assert(vh_b8_init_scene_variant(&b, 0, 0));
    assert(b.roster.units[0].x == 0 && b.roster.units[4].x == 1);
}

static void real_enemy_phase_then_field_medic(void) {
    VhBattle8 b;
    int turn = 0;
    assert(vh_b8_init_scene_variant(&b, 1, 0));
    while (turn < 8 && b.roster.units[0].hp >= 3 &&
           b.status == VH_BONGOING) {
        assert(vh_b8_end_turn(&b) == VH_BEND);
        ++turn;
    }
    /* Actual pathfinding AI, not forced HP injection. */
    assert(b.status == VH_BONGOING);
    assert(b.roster.units[0].hp >= 1);
    assert(b.roster.units[0].hp < 3);
    assert(vh_balive(&b.roster.units[1]));
    assert(b.roster.units[1].acted == 0);
    b.roster.cursor_x = b.roster.units[1].x;
    b.roster.cursor_y = b.roster.units[1].y;
    assert(vh_b8_choose(&b) == VH_BSELECT);
    assert(b.selected == 1);
    b.roster.cursor_x = b.roster.units[0].x;
    b.roster.cursor_y = b.roster.units[0].y;
    assert(vh_b8_heal(&b) == VH_BHEAL);
    assert(b.roster.units[0].hp == 3);
    printf("VH_MAP02_MEDIC_ENEMY_PHASE first_damage_turn=%d\n", turn);
}

int main(void) {
    healing_requires_real_damage_and_valid_target();
    support_is_bounded_and_cannot_revive();
    padded_rosters_and_original_arena_unchanged();
    real_enemy_phase_then_field_medic();
    puts("VH_MAP02_MEDIC_PASS adjacent=1 hp_cap=3 no_revive=1 no_self=1 "
         "no_enemy=1 spent_action=1 natural_damage=1 "
         "invalid_no_mutation=1 old_scenes=1");
    return 0;
}
