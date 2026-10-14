#ifndef VANDAL_HEARTS_GAME_STATE_H
#define VANDAL_HEARTS_GAME_STATE_H

#include "game_rules.h"

typedef struct {
    int cursor_x;
    int cursor_y;
    int hero_x;
    int hero_y;
    int enemy_x;
    int enemy_y;
    int hero_selected;
} VhGameState;

static inline void vh_move_cursor(VhGameState *state, int dx, int dy,
                                  int grid_width, int grid_height) {
    state->cursor_x += dx;
    state->cursor_y += dy;

    if (state->cursor_x < 0) state->cursor_x = 0;
    if (state->cursor_x >= grid_width) state->cursor_x = grid_width - 1;
    if (state->cursor_y < 0) state->cursor_y = 0;
    if (state->cursor_y >= grid_height) state->cursor_y = grid_height - 1;
}

static inline void vh_activate_cursor(VhGameState *state,
                                      int grid_width, int grid_height,
                                      int move_range) {
    if (!state->hero_selected) {
        if (state->cursor_x == state->hero_x &&
            state->cursor_y == state->hero_y) {
            state->hero_selected = 1;
        }
        return;
    }

    if (vh_can_move(state->hero_x, state->hero_y,
                    state->cursor_x, state->cursor_y,
                    grid_width, grid_height, move_range,
                    state->enemy_x, state->enemy_y)) {
        state->hero_x = state->cursor_x;
        state->hero_y = state->cursor_y;
        state->hero_selected = 0;
    }
}

static inline void vh_cancel_selection(VhGameState *state) {
    state->hero_selected = 0;
}

#endif
