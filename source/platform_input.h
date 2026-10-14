#ifndef VANDAL_HEARTS_PLATFORM_INPUT_H
#define VANDAL_HEARTS_PLATFORM_INPUT_H

#include "game_state.h"

/*
 * Platform-neutral action bits. A platform adapter (libnx, SDL, or desktop)
 * translates native button events into these actions; game logic never needs
 * to include platform-specific headers.
 */
enum {
    VH_INPUT_LEFT   = 1u << 0,
    VH_INPUT_RIGHT  = 1u << 1,
    VH_INPUT_UP     = 1u << 2,
    VH_INPUT_DOWN   = 1u << 3,
    VH_INPUT_CONFIRM = 1u << 4,
    VH_INPUT_CANCEL = 1u << 5,
    VH_INPUT_QUIT   = 1u << 6
};

static inline int vh_process_input(VhGameState *state, unsigned int actions,
                                   int grid_width, int grid_height,
                                   int move_range) {
    if (actions & VH_INPUT_QUIT) return 1;

    if (actions & VH_INPUT_LEFT)
        vh_move_cursor(state, -1, 0, grid_width, grid_height);
    if (actions & VH_INPUT_RIGHT)
        vh_move_cursor(state, 1, 0, grid_width, grid_height);
    if (actions & VH_INPUT_UP)
        vh_move_cursor(state, 0, -1, grid_width, grid_height);
    if (actions & VH_INPUT_DOWN)
        vh_move_cursor(state, 0, 1, grid_width, grid_height);

    if (actions & VH_INPUT_CONFIRM)
        vh_activate_cursor(state, grid_width, grid_height, move_range);
    if (actions & VH_INPUT_CANCEL)
        vh_cancel_selection(state);

    return 0;
}

#endif
