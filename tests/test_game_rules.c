#include <assert.h>
#include <stdio.h>

#include "../source/game_rules.h"
#include "../source/game_state.h"

int main(void) {
    assert(vh_manhattan_distance(1, 2, 1, 2) == 0);
    assert(vh_manhattan_distance(1, 2, 3, 2) == 2);
    assert(vh_manhattan_distance(1, 2, 2, 4) == 3);

    assert(vh_is_inside_grid(0, 0, 8, 6));
    assert(vh_is_inside_grid(7, 5, 8, 6));
    assert(!vh_is_inside_grid(-1, 0, 8, 6));
    assert(!vh_is_inside_grid(8, 5, 8, 6));
    assert(!vh_is_inside_grid(0, 6, 8, 6));

    /* Within range, including staying in place. */
    assert(vh_can_move(1, 2, 1, 2, 8, 6, 2, 6, 3));
    assert(vh_can_move(1, 2, 3, 2, 8, 6, 2, 6, 3));
    assert(vh_can_move(1, 2, 2, 3, 8, 6, 2, 6, 3));

    /* Too far, outside the board, or onto the blocked enemy tile. */
    assert(!vh_can_move(1, 2, 4, 2, 8, 6, 2, 6, 3));
    assert(!vh_can_move(1, 2, -1, 2, 8, 6, 2, 6, 3));
    assert(!vh_can_move(1, 2, 6, 3, 8, 6, 20, 6, 3));

    /* Cursor clamps to the grid edges. */
    VhGameState state = {0, 0, 1, 2, 6, 3, 0};
    vh_move_cursor(&state, -1, 0, 8, 6);
    vh_move_cursor(&state, 0, -1, 8, 6);
    assert(state.cursor_x == 0 && state.cursor_y == 0);
    vh_move_cursor(&state, 99, 99, 8, 6);
    assert(state.cursor_x == 7 && state.cursor_y == 5);

    /* A selects only when the cursor is on the hero. */
    state = (VhGameState){2, 2, 1, 2, 6, 3, 0};
    vh_activate_cursor(&state, 8, 6, 2);
    assert(state.hero_selected == 0 && state.hero_x == 1 && state.hero_y == 2);
    state.cursor_x = state.hero_x;
    state.cursor_y = state.hero_y;
    vh_activate_cursor(&state, 8, 6, 2);
    assert(state.hero_selected == 1);

    /* A valid move updates the hero and clears selection. */
    vh_move_cursor(&state, 2, 0, 8, 6);
    vh_activate_cursor(&state, 8, 6, 2);
    assert(state.hero_x == 3 && state.hero_y == 2 && state.hero_selected == 0);

    /* Invalid moves leave both the hero and selection unchanged. */
    state.hero_selected = 1;
    state.cursor_x = state.enemy_x;
    state.cursor_y = state.enemy_y;
    vh_activate_cursor(&state, 8, 6, 2);
    assert(state.hero_x == 3 && state.hero_y == 2 && state.hero_selected == 1);
    state.cursor_x = 7;
    state.cursor_y = 5;
    vh_activate_cursor(&state, 8, 6, 2);
    assert(state.hero_x == 3 && state.hero_y == 2 && state.hero_selected == 1);

    vh_cancel_selection(&state);
    assert(state.hero_selected == 0);

    puts("All tactical movement rule tests passed.");
    return 0;
}
