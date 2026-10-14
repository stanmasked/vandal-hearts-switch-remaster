# Software Renderer Contract

## Purpose

`source/software_renderer.h` defines a small platform-neutral software-canvas primitive. It deliberately does not acquire a framebuffer, present a frame, choose a pixel format, or depend on libnx, SDL, OpenGL, or the original game's assets.

## Canvas

A `VhCanvas` contains:

- `pixels`: caller-owned memory holding packed 32-bit pixels;
- `stride_pixels`: distance between the starts of adjacent rows, measured in pixels (not bytes);
- `width` and `height`: visible canvas dimensions.

The caller is responsible for ensuring the allocation covers at least `stride_pixels * height` pixels. The stride must be at least the visible width.

## Rectangle fill behavior

`vh_canvas_fill_rect` fills the intersection of the requested rectangle and the visible canvas. Negative origins and rectangles extending beyond the right or bottom edges are clipped. Empty or wholly off-screen rectangles are no-ops. Null canvas pointers, null pixel storage, non-positive dimensions, and a stride smaller than the width are rejected as no-ops.

The color is copied unchanged into each covered pixel. Its channel ordering and alpha representation are intentionally platform-defined by the caller; the renderer does not convert colors.

Bounds are widened during arithmetic to avoid signed integer overflow when adding large coordinates and dimensions.

## Tests

Run `make test` to execute both the tactical-rule/input tests and `tests/test_software_renderer.c`. The renderer tests cover ordinary fills, padded row strides, clipping at all relevant edges, off-screen and empty rectangles, and malformed canvas inputs.

## Pixel and line primitives

- `vh_canvas_put_pixel` writes one pixel only when its coordinates are inside the visible canvas.
- `vh_canvas_draw_hline` and `vh_canvas_draw_vline` draw clipped horizontal and vertical lines using a positive length and a starting coordinate. The implementation shares rectangle-fill clipping, so partially off-screen lines are clipped and invalid lengths are no-ops.
- All primitives honor `stride_pixels` and leave row padding untouched.

- `vh_canvas_draw_rect_outline` draws a one-pixel border around a rectangle with the requested width and height. The same clipping and stride guarantees apply; non-positive extents are no-ops. Coordinate arithmetic for the far edges is widened before use.

The host-side renderer tests now cover valid and out-of-bounds pixel writes, clipped horizontal/vertical lines, and padding preservation.

## Current limitation

The Switch prototype still owns framebuffer acquisition and presentation in `source/main.c`. This contract only isolates the rectangle rasterization primitive; it is not a complete rendering backend and does not yet render the original Vandal Hearts game.
