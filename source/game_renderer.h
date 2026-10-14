#ifndef VANDAL_HEARTS_GAME_RENDERER_H
#define VANDAL_HEARTS_GAME_RENDERER_H

#include <stdint.h>
#include "software_renderer.h"

/* Palette supplied by the platform layer; colors remain pixel-format agnostic. */
typedef struct {
    uint32_t tile;
    uint32_t border;
} VhTilePalette;

/* Draw one filled tactical-grid tile with a two-pixel frame. */
static inline void vh_render_grid_tile(VhCanvas *canvas, int x, int y,
                                       int size, VhTilePalette palette) {
    if (!canvas || size <= 0) return;
    if (size <= 4) {
        vh_canvas_fill_rect(canvas, x, y, size, size, palette.border);
        return;
    }

    vh_canvas_fill_rect(canvas, x + 2, y + 2, size - 4, size - 4, palette.tile);
    vh_canvas_fill_rect(canvas, x, y, size, 2, palette.border);
    vh_canvas_fill_rect(canvas, x, y + size - 2, size, 2, palette.border);
    vh_canvas_fill_rect(canvas, x, y, 2, size, palette.border);
    vh_canvas_fill_rect(canvas, x + size - 2, y, 2, size, palette.border);
}

#endif
