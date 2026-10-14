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
    /* Invalid source coordinates and negative movement ranges are rejected. */
    assert(!vh_can_move(-1, 2, 0, 2, 8, 6, 2, 6, 3));
    assert(!vh_can_move(8, 2, 7, 2, 8, 6, 2, 6, 3));
    assert(!vh_can_move(1, 2, 1, 2, 8, 6, -1, 6, 3));

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

    /* Exhaustive bounds check: every cursor position and direction stays on-grid. */
    for (int y = 0; y < 6; y++) {
        for (int x = 0; x < 8; x++) {
            const int dxs[] = {-1, 0, 1};
            const int dys[] = {-1, 0, 1};
            for (unsigned int ix = 0; ix < sizeof(dxs) / sizeof(dxs[0]); ix++) {
                for (unsigned int iy = 0; iy < sizeof(dys) / sizeof(dys[0]); iy++) {
                    VhGameState edge = {x, y, 1, 2, 6, 3, 0};
                    vh_move_cursor(&edge, dxs[ix], dys[iy], 8, 6);
                    assert(vh_is_inside_grid(edge.cursor_x, edge.cursor_y, 8, 6));
                    assert(edge.cursor_x >= 0 && edge.cursor_x <= 7);
                    assert(edge.cursor_y >= 0 && edge.cursor_y <= 5);
                }
            }
        }
    }

    /* Exhaustively check movement range and enemy blocking over the board. */
    for (int y = 0; y < 6; y++) {
        for (int x = 0; x < 8; x++) {
            const int allowed = vh_manhattan_distance(1, 2, x, y) <= 2 &&
                                !(x == 6 && y == 3);
            assert(vh_can_move(1, 2, x, y, 8, 6, 2, 6, 3) == allowed);
        }
    }

    puts("All tactical movement rule tests passed.");
    return 0;
}
