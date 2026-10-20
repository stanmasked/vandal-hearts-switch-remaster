/*
 * Exact deterministic host replay of the independent NeXium 4v4 movement
 * route. This validates the expected tactical state but does NOT replace the
 * separate real-NeXium screenshots and physical-input integration job.
 */
#include <assert.h>
#include <stdio.h>
#include "../source/map02_battle8.h"
#include "../source/map02_roster8_smoke_data.h"

int main(void) {
    VhBattle8 battle;
    int i;
    assert(vh_b8_init(&battle, &VH_MAP02_ROSTER8_SMOKE, 2, 2));
    assert(vh_r8_alive(&battle.roster, 0) == 4);
    assert(vh_r8_alive(&battle.roster, 1) == 4);

    battle.roster.cursor_x = 0;
    battle.roster.cursor_y = 3;
    assert(vh_b8_choose(&battle) == VH_BSELECT);
    assert(battle.selected == 3);

    /* An authored wall at (3,2) cannot be entered from (0,3).
       The selected unit must remain available for a valid movement. */
    battle.roster.cursor_x = 3;
    battle.roster.cursor_y = 2;
    assert(vh_b8_path(&battle, 3, 3, 2, -1, 0, 0) == -1);
    assert(vh_b8_choose(&battle) == VH_BINVALID);
    assert(battle.selected == 3);
    assert(battle.roster.units[3].x == 0);
    assert(battle.roster.units[3].y == 3);
    assert(battle.roster.units[3].acted == 0);

    battle.roster.cursor_x = 0;
    battle.roster.cursor_y = 4;
    assert(vh_b8_path(&battle, 3, 0, 4, -1, 0, 0) == 1);
    assert(vh_b8_choose(&battle) == VH_BMOVE);
    assert(battle.selected == -1);
    assert(battle.roster.units[3].x == 0);
    assert(battle.roster.units[3].y == 4);
    assert(battle.roster.units[3].acted == 1);
    assert(vh_r8_occupant(&battle.roster, 0, 3) == -1);

    /* Three enemy attacks deplete ally HP, while foe #7 advances into the
       cell vacated by the moved fourth ally. No actor overlaps another. */
    assert(vh_b8_end_turn(&battle) == VH_BEND);
    assert(battle.turns_completed == 1);
    assert(battle.status == VH_BONGOING);
    for (i = 0; i < 3; ++i) {
        assert(battle.roster.units[i].hp == 1);
        assert(!battle.roster.units[i].acted);
    }
    assert(battle.roster.units[3].hp == 3);
    assert(!battle.roster.units[3].acted);
    assert(battle.roster.units[7].x == 0);
    assert(battle.roster.units[7].y == 3);
    assert(vh_r8_occupant(&battle.roster, 0, 3) == 7);
    assert(vh_r8_occupant(&battle.roster, 1, 3) == -1);
    for (i = 4; i < 8; ++i) assert(battle.roster.units[i].hp == 2);

    /* Reset gives the exact initial layout and fresh turn state. */
    assert(vh_b8_init(&battle, &VH_MAP02_ROSTER8_SMOKE, 2, 2));
    assert(battle.status == VH_BONGOING);
    assert(battle.turns_completed == 0);
    assert(battle.selected == -1);
    assert(battle.roster.units[3].y == 3);
    assert(battle.roster.units[7].x == 1);
    assert(battle.roster.units[7].y == 3);
    assert(battle.roster.cursor_x == 0);
    assert(battle.roster.cursor_y == 0);

    puts("VH_MAP02_4V4_PATH_MODEL_PASS illegal_wall=1 one_tile_move=1 "
         "ai_hp_loss=1 enemy_pursuit=1 reset=1 actual_nexium=0");
    return 0;
}
