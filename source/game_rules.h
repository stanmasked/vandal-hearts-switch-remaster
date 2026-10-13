#ifndef VANDAL_HEARTS_GAME_RULES_H
#define VANDAL_HEARTS_GAME_RULES_H

static inline int vh_manhattan_distance(int x1, int y1, int x2, int y2) {
    int dx = x1 - x2;
    int dy = y1 - y2;
    if (dx < 0) dx = -dx;
    if (dy < 0) dy = -dy;
    return dx + dy;
}

static inline int vh_is_inside_grid(int x, int y, int width, int height) {
    return x >= 0 && y >= 0 && x < width && y < height;
}

static inline int vh_can_move(int from_x, int from_y, int to_x, int to_y,
                              int grid_width, int grid_height, int move_range,
                              int blocked_x, int blocked_y) {
    if (!vh_is_inside_grid(to_x, to_y, grid_width, grid_height)) return 0;
    if (to_x == blocked_x && to_y == blocked_y) return 0;
    return vh_manhattan_distance(from_x, from_y, to_x, to_y) <= move_range;
}

#endif
