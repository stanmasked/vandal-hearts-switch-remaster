/* New opt-in scene-B ranged tactical action, checked without game assets.
 * All tests exercise the exact portable API compiled into the Switch NRO.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_roster8_variants.h"
#include "../source/map02_ranged8.h"

static void assert_unchanged(const VhBattle8 *a, const VhBattle8 *b) {
    assert(memcmp(a, b, sizeof(*a)) == 0);
}

static void long_shot_requires_position_and_clear_line(void) {
    VhBattle8 s, old;
    assert(vh_b8_init_scene_variant(&s, 1, 0));
    assert(vh_b8_choose(&s) == VH_BSELECT);
    s.roster.cursor_x = 5; /* Original archer (1,0) -> foe (5,0): 4 */
    old = s;
    assert(!vh_b8_clear_shot(&s, 0, 4, VH_B8_BOW_MAX_RANGE));
    assert(vh_b8_shoot(&s) == VH_BINVALID);
    assert_unchanged(&s, &old);
    assert(vh_b8_cancel(&s) == VH_BCANCEL);
    s.roster.cursor_x = 1; /* select same archer again */
    assert(vh_b8_choose(&s) == VH_BSELECT);
    s.roster.cursor_x = 2; /* legal move closer */
    assert(vh_b8_choose(&s) == VH_BMOVE);
    assert(s.roster.units[0].acted == 1);
    assert(vh_b8_end_turn(&s) == VH_BEND);
    assert(s.roster.units[4].x == 4 && s.roster.units[4].y == 0);
    assert(!s.roster.units[0].acted);
    assert(vh_b8_choose(&s) == VH_BSELECT); /* cursor at (2,0) */
    s.roster.cursor_x = 4;
    assert(vh_b8_clear_shot(&s, 0, 4, VH_B8_BOW_MAX_RANGE));
    assert(vh_b8_shoot(&s) == VH_BATTACK);
    assert(s.roster.units[4].hp == 0);
    assert(s.roster.units[0].acted == 1);
    assert(s.roster.units[0].hp == 3);
    assert(s.status == VH_BONGOING);
    assert(vh_r8_alive(&s.roster, 1) == 3);
    assert(s.selected == -1);
    old = s;
    assert(vh_b8_shoot(&s) == VH_BINVALID);
    assert_unchanged(&s, &old);
}

static void wall_blocks_line_of_sight(void) {
    VhBattle8 s, old;
    assert(vh_b8_init_scene_variant(&s, 1, 0));
    s.roster.units[0].x = 2;
    s.roster.units[0].y = 2;
    s.roster.cursor_x = 5;
    s.roster.cursor_y = 2;
    s.selected = 0;
    assert(s.roster.walls[2] & (1u << 3));
    old = s;
    assert(!vh_b8_clear_shot(&s, 0, 6, VH_B8_BOW_MAX_RANGE));
    assert(vh_b8_shoot(&s) == VH_BINVALID);
    assert_unchanged(&s, &old);
}

static void actors_block_line_of_sight(void) {
    VhBattle8 s, old;
    assert(vh_b8_init_scene_variant(&s, 1, 0));
    s.roster.units[4].x = 4;
    s.roster.units[5].x = 3;
    s.roster.units[5].y = 0;
    s.roster.cursor_x = 4;
    s.roster.cursor_y = 0;
    s.selected = 0;
    old = s;
    assert(!vh_b8_clear_shot(&s, 0, 4, VH_B8_BOW_MAX_RANGE));
    assert(vh_b8_shoot(&s) == VH_BINVALID);
    assert_unchanged(&s, &old);
}

static void illegal_shots_preserve_every_byte(void) {
    VhBattle8 s, old;
    assert(vh_b8_init_scene_variant(&s, 1, 0));
    s.selected = 0;
    s.roster.cursor_x = s.roster.units[1].x;
    s.roster.cursor_y = s.roster.units[1].y; /* friendly fire */
    old = s;
    assert(vh_b8_shoot(&s) == VH_BINVALID);
    assert_unchanged(&s, &old);

    s.roster.units[4].x = 3;
    s.roster.units[4].y = 1; /* diagonal from (1,0) */
    s.roster.cursor_x = 3;
    s.roster.cursor_y = 1;
    old = s;
    assert(vh_b8_shoot(&s) == VH_BINVALID);
    assert_unchanged(&s, &old);

    s.roster.units[4].x = 2;
    s.roster.units[4].y = 0; /* adjacent: A melee, no bow */
    s.roster.cursor_x = 2;
    s.roster.cursor_y = 0;
    old = s;
    assert(vh_b8_shoot(&s) == VH_BINVALID);
    assert_unchanged(&s, &old);

    s.roster.units[4].x = 3;
    s.roster.units[0].acted = 1;
    s.roster.cursor_x = 3;
    old = s;
    assert(vh_b8_shoot(&s) == VH_BINVALID);
    assert_unchanged(&s, &old);

    s.roster.units[0].acted = 0;
    s.roster.units[4].hp = 0; /* eliminated target */
    old = s;
    assert(vh_b8_shoot(&s) == VH_BINVALID);
    assert_unchanged(&s, &old);

    assert(vh_b8_shoot(NULL) == VH_BINVALID);
    assert(!vh_b8_clear_shot(NULL, 0, 4, 3));
    assert(!vh_b8_clear_shot(&s, -1, 4, 3));
    assert(!vh_b8_clear_shot(&s, 0, 8, 3));
    assert(!vh_b8_clear_shot(&s, 0, 4, 99));
}

static void ranged_finish_sets_victory_and_resets(void) {
    VhBattle8 s;
    int i;
    assert(vh_b8_init_scene_variant(&s, 1, 2)); /* 1v4 */
    for (i = 5; i < 8; ++i) s.roster.units[i].hp = 0;
    s.roster.units[4].x = 3; /* straight range two */
    s.selected = 0;
    s.roster.cursor_x = 3;
    assert(vh_b8_shoot(&s) == VH_BATTACK);
    assert(s.status == VH_BWIN);
    assert(vh_r8_alive(&s.roster, 1) == 0);
    assert(vh_b8_shoot(&s) == VH_BINVALID);
    assert(vh_b8_init_scene_variant(&s, 1, 2));
    assert(s.status == VH_BONGOING && s.selected == -1);
    assert(s.roster.units[4].hp == 2);
    assert(s.roster.units[4].x == 5);
}

/* The previously validated scene-A 4v4 and legacy MAP02 files remain
 * byte-compatible, including actor padding and authored walls. */
static void source_scenes_unchanged(void) {
    VhRoster8 a, b;
    assert(vh_r8_scene_variant(&a, 0, 0));
    assert(vh_r8_scene_variant(&b, 1, 0));
    assert(memcmp(&a, &VH_MAP02_ROSTER8_SMOKE, sizeof(a)) == 0);
    assert(memcmp(&b, &VH_MAP02_ROSTER8_SECOND, sizeof(b)) == 0);
}

int main(void) {
    long_shot_requires_position_and_clear_line();
    wall_blocks_line_of_sight();
    actors_block_line_of_sight();
    illegal_shots_preserve_every_byte();
    ranged_finish_sets_victory_and_resets();
    source_scenes_unchanged();
    puts("VH_MAP02_BOW_PASS range=2to3 los=1 wall_block=1 actor_block=1 "
         "friendly_fire=0 repeat_attack=0 victory=1 original_scenes=1");
    return 0;
}
