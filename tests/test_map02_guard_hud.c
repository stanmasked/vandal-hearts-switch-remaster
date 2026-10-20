/* Pure guard display states must follow actual tactical state transitions. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_roster8_variants.h"
#include "../source/map02_guard_hud.h"

#define STATE(b,g,s,e) assert(vh_b8_guard_hud_state(&(b), &(g), s) == (e))

static void guard_state_transitions(void) {
    VhBattle8 b;
    VhGuard8 guard = {0};
    int i;
    assert(vh_b8_init_scene_variant(&b, 1, 0));
    STATE(b, guard, 0, VH_GHUD_HIDDEN);
    STATE(b, guard, 1, VH_GHUD_READY);
    assert(!strcmp(vh_b8_guard_hud_label(VH_GHUD_READY), "GUARD READY"));

    b.roster.cursor_x = b.roster.units[2].x;
    b.roster.cursor_y = b.roster.units[2].y;
    assert(vh_b8_choose(&b) == VH_BSELECT);
    STATE(b, guard, 1, VH_GHUD_READY);
    assert(vh_b8_guard_action(&b, &guard) == VH_BGUARD);
    STATE(b, guard, 1, VH_GHUD_ARMED);
    assert(!strcmp(vh_b8_guard_hud_label(VH_GHUD_ARMED),
                   "GUARD ARMED -1 HP"));
    assert(vh_b8_end_turn_guarded(&b, &guard) == VH_BEND);
    STATE(b, guard, 1, VH_GHUD_READY);
    assert(guard.absorbed_last_turn == 0);
    assert(vh_b8_init_scene_variant(&b, 1, 0));
    vh_b8_guard_reset(&guard);

    for (i = 0; i < 3; ++i)
        assert(vh_b8_end_turn(&b) == VH_BEND);
    b.roster.cursor_x = b.roster.units[2].x;
    b.roster.cursor_y = b.roster.units[2].y;
    assert(vh_b8_choose(&b) == VH_BSELECT);
    assert(vh_b8_guard_action(&b, &guard) == VH_BGUARD);
    STATE(b, guard, 1, VH_GHUD_ARMED);
    assert(vh_b8_end_turn_guarded(&b, &guard) == VH_BEND);
    assert(guard.absorbed_last_turn == 1);
    STATE(b, guard, 1, VH_GHUD_BLOCKED);
    assert(!strcmp(vh_b8_guard_hud_label(VH_GHUD_BLOCKED),
                   "GUARD BLOCKED 1 HP"));

    assert(vh_b8_end_turn_guarded(&b, &guard) == VH_BEND);
    STATE(b, guard, 1, VH_GHUD_READY);

    assert(vh_b8_init_scene_variant(&b, 1, 0));
    vh_b8_guard_reset(&guard);
    STATE(b, guard, 1, VH_GHUD_READY);
    b.roster.units[2].acted = 1;
    STATE(b, guard, 1, VH_GHUD_SPENT);
    b.roster.units[2].acted = 0;
    b.roster.units[2].hp = 0;
    STATE(b, guard, 1, VH_GHUD_UNAVAILABLE);
    b.status = VH_BLOSS;
    STATE(b, guard, 1, VH_GHUD_FINISHED);
}

static void all_rosters_and_invalid_inputs(void) {
    VhBattle8 b, old;
    VhGuard8 guard = {0};
    int scene, variant;
    for (scene = 0; scene < VH_R8_SCENES; ++scene) {
        for (variant = 0; variant < VH_R8_VARIANTS; ++variant) {
            assert(vh_b8_init_scene_variant(&b, scene, variant));
            old = b;
            STATE(b, guard, scene,
                  scene == 0 ? VH_GHUD_HIDDEN :
                  variant == 2 ? VH_GHUD_UNAVAILABLE : VH_GHUD_READY);
            assert(memcmp(&b, &old, sizeof(b)) == 0);
        }
    }
    assert(vh_b8_guard_hud_state(NULL, &guard, 1) == VH_GHUD_HIDDEN);
    assert(vh_b8_guard_hud_state(&b, NULL, 1) == VH_GHUD_HIDDEN);
    assert(vh_b8_guard_hud_state(&b, &guard, -1) == VH_GHUD_HIDDEN);
    assert(vh_b8_guard_hud_state(&b, &guard, 99) == VH_GHUD_HIDDEN);
    assert(!strcmp(vh_b8_guard_hud_label(-20), ""));
    assert(!strcmp(vh_b8_guard_hud_label(VH_GHUD_SPENT), "GUARD SPENT"));
}

int main(void) {
    guard_state_transitions();
    all_rosters_and_invalid_inputs();
    puts("VH_MAP02_GUARD_HUD_PASS stages=2 rosters=3 armed=1 blocked=1 "
         "expired=1 reset=1 unused=1 zero_mutation=1");
    return 0;
}
