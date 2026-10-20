/* Independent 4x4, 3x3, 1x4 controller roster-state contract. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_roster8_variants.h"

static void prove_variant(int variant, int expected_allies, int expected_foes,
                          const char *label) {
    VhBattle8 state;
    VhRoster8 r;
    int i;
    assert(strcmp(vh_r8_variant_label(variant), label) == 0);
    assert(vh_r8_variant(&r, variant));
    assert(vh_r8_valid(&r));
    assert(r.ally_count == expected_allies);
    assert(r.enemy_count == expected_foes);
    assert(vh_b8_init_variant(&state, variant));
    assert(state.status == VH_BONGOING);
    assert(state.selected == -1);
    assert(state.turns_completed == 0);
    assert(state.roster.cursor_x == 0 && state.roster.cursor_y == 0);
    assert(vh_r8_alive(&state.roster, 0) == expected_allies);
    assert(vh_r8_alive(&state.roster, 1) == expected_foes);
    assert(state.roster.units[0].x == 0 && state.roster.units[0].y == 0);
    assert(vh_r8_occupant(&state.roster, 1, 0) == 4);
    for (i = expected_allies; i < 4; ++i) {
        const VhBattleUnit empty = {0, 0, 0, 0};
        assert(memcmp(&state.roster.units[i], &empty, sizeof(empty)) == 0);
        assert(!vh_r8_active(&state.roster, i));
    }
    for (i = 4 + expected_foes; i < 8; ++i) {
        const VhBattleUnit empty = {0, 0, 0, 0};
        assert(memcmp(&state.roster.units[i], &empty, sizeof(empty)) == 0);
        assert(!vh_r8_active(&state.roster, i));
    }
    if (variant == 0) {
        assert(memcmp(&r, &VH_MAP02_ROSTER8_SMOKE, sizeof(r)) == 0);
    }
    /* An A-button attack must not end the game prematurely unless the
     * victim really is the final living opponent. */
    assert(vh_b8_choose(&state) == VH_BSELECT);
    state.roster.cursor_x = 1;
    assert(vh_b8_choose(&state) == VH_BATTACK);
    assert(state.roster.units[4].hp == 0);
    assert(state.status == VH_BONGOING);
    assert(vh_r8_alive(&state.roster, 1) == expected_foes - 1);
    /* Y resets the selected size, not always the original 4x4. */
    assert(vh_b8_init_variant(&state, variant));
    assert(vh_r8_alive(&state.roster, 0) == expected_allies);
    assert(vh_r8_alive(&state.roster, 1) == expected_foes);
    assert(state.roster.units[4].hp == 2);
}

static void illegal_variant_cannot_mutate_game(void) {
    VhBattle8 s, before;
    VhRoster8 r, previous;
    assert(vh_b8_init_variant(&s, 0));
    before = s;
    assert(!vh_b8_init_variant(&s, -1));
    assert(memcmp(&s, &before, sizeof(s)) == 0);
    assert(!vh_b8_init_variant(&s, 3));
    assert(memcmp(&s, &before, sizeof(s)) == 0);
    assert(!vh_b8_init_variant(NULL, 0));
    assert(vh_r8_variant(&r, 2));
    previous = r;
    assert(!vh_r8_variant(&r, 5));
    assert(memcmp(&r, &previous, sizeof(r)) == 0);
    assert(!vh_r8_variant(NULL, 1));
    assert(strcmp(vh_r8_variant_label(5), "INVALID ROSTER") == 0);
}

int main(void) {
    assert(VH_R8_VARIANTS == 3);
    prove_variant(0, 4, 4, "ROSTER 4 VS 4");
    prove_variant(1, 3, 3, "ROSTER 3 VS 3");
    prove_variant(2, 1, 4, "ROSTER 1 VS 4");
    illegal_variant_cannot_mutate_game();
    puts("VH_MAP02_4V4_VARIANTS_PASS default=4v4 second=3v3 third=1v4 "
         "padding=1 reset_current=1 fail_closed=1 retail=0");
    return 0;
}
