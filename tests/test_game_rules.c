#include <assert.h>
#include <stdio.h>

#include "../source/game_rules.h"

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

    puts("All tactical movement rule tests passed.");
    return 0;
}
