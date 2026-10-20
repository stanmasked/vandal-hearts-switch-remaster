/* Second map is played via the same portable battle APIs as the Switch NRO.
 * This is an original tactical fixture, not retail MAP02 data.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_battle_fixture.h"

static void attack(VhMap02Battle *s, int ally, int enemy) {
    s->cursor_x = s->units[ally].x;
    s->cursor_y = s->units[ally].y;
    assert(vh_bchoose(s) == VH_BSELECT);
    s->cursor_x = s->units[enemy].x;
    s->cursor_y = s->units[enemy].y;
    assert(vh_bchoose(s) == VH_BATTACK);
}

static void catalog_select_and_protect_state(void) {
    VhMap02Battle s, before;
    assert(VH_BSCENARIOS == 2);
    assert(vh_bscenario_by_index(0) == &VH_MAP02_DEFAULT_SCENARIO);
    assert(vh_bscenario_by_index(1) == &VH_MAP02_SECOND_SCENARIO);
    assert(vh_bscenario_by_index(-1) == NULL);
    assert(vh_bscenario_by_index(2) == NULL);
    assert(vh_binit_index(&s, 0));
    before = s;
    assert(!vh_binit_index(&s, -1));
    assert(!vh_binit_index(&s, 2));
    assert(memcmp(&before, &s, sizeof(s)) == 0);
    assert(vh_bwall_at(&s, 5, 2) == 0);
    assert(s.units[2].x == 5 && s.units[2].y == 2);
    assert(s.move_range == 2 && s.attack_damage == 1);
    assert(vh_binit_index(&s, 1));
    assert(s.units[0].x == 1 && s.units[0].y == 2);
    assert(s.units[2].x == 2 && s.units[2].y == 2);
    assert(s.units[3].x == 2 && s.units[3].y == 4);
    assert(s.move_range == 3 && s.attack_damage == 2);
    assert(vh_bwall_at(&s, 5, 2));
    assert(!vh_bwall_at(&s, 0, 2));
    assert(vh_bpath(&s, 0, 2, 2, 2, NULL, NULL) == 1);
    /* Repeated scenario switch is deterministic and resets all battle state. */
    before = s;
    assert(vh_binit_index(&s, 0));
    assert(vh_binit_index(&s, 1));
    assert(memcmp(&before, &s, sizeof(s)) == 0);
}

static void alternate_map_two_attacks_from_real_start(void) {
    VhMap02Battle game, original;
    assert(vh_binit_index(&game, 1));
    original = game;
    /* The independently authored B map has adjacent foes and 2-damage A. */
    attack(&game, 0, 2);
    assert(!vh_balive(&game.units[2]));
    assert(game.status == VH_BONGOING && game.units[0].acted);
    attack(&game, 1, 3);
    assert(!vh_balive(&game.units[3]));
    assert(game.status == VH_BWIN);
    assert(game.turns_completed == 0);
    assert(vh_bend_turn(&game) == VH_BINVALID);
    assert(vh_binit_index(&game, 1)); /* Y reset retains selected map */
    assert(memcmp(&original, &game, sizeof(game)) == 0);
}

int main(void) {
    catalog_select_and_protect_state();
    alternate_map_two_attacks_from_real_start();
    puts("VH_MAP02_TWO_SCENARIOS_PASS catalog=2 original_preserved=1 "
         "alternate_victory=1 bounds_rejected=2 reset=1 retail=0");
    return 0;
}
