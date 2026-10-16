#ifndef VH_FT4_TEXTURED_QUAD_H
#define VH_FT4_TEXTURED_QUAD_H

/*
 * Portable CPU reference rasterizer for a textured POLY_FT4.
 *
 * This deliberately is NOT a PS1 GPU emulator: no perspective correction,
 * subpixel quantization, dithering, semi-transparency, texture windows or
 * ordering tables. It gives the Switch project a deterministic, asset-free
 * diagnostic path from projected terrain vertices to decoded RGBA32 texels.
 * The caller owns screen-space projection, texture decoding and blending.
 */
#include <limits.h>
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include "software_renderer.h"

typedef struct {
    float x;
    float y;
} VhFt4Point;

typedef struct {
    float x;
    float y;
    float u;  /* Texel coordinates: e.g. atlas u = 240..255, inclusive. */
    float v;
} VhFt4Vertex;

/*
 * Original US PC-port maps face vertices [0,1,2,3] to POLY_FT4
 * [x0,x1,x3,x2], while setUVWH maps [uv0,uv1,uv3,uv2] respectively.
 * Output indices are GPU corners 0,1,2,3, *not* perimeter ordering.
 */
static inline int vh_ft4_from_face_perimeter(
    const VhFt4Point face[4], int u, int v, int w, int h,
    VhFt4Vertex out[4]) {
    static const int perimeter_for_gpu[4] = {0, 1, 3, 2};
    int i;
    if (!face || !out || u < 0 || v < 0 || w < 1 || h < 1 ||
        u > 255 || v > 255 || w > 255 - u || h > 255 - v) {
        return 0;
    }
    for (i = 0; i < 4; ++i) {
        if (!isfinite(face[i].x) || !isfinite(face[i].y)) return 0;
    }
    /* face/out may alias at the same address: snapshot first. */
    {
        VhFt4Point tmp[4];
        for (i = 0; i < 4; ++i) tmp[i] = face[i];
        for (i = 0; i < 4; ++i) {
            out[i].x = tmp[perimeter_for_gpu[i]].x;
            out[i].y = tmp[perimeter_for_gpu[i]].y;
        }
    }
    out[0].u = out[2].u = (float)u;
    out[1].u = out[3].u = (float)(u + w);
    out[0].v = out[1].v = (float)v;
    out[2].v = out[3].v = (float)(v + h);
    return 1;
}

static inline double vh_ft4_edge(
    const VhFt4Vertex *a, const VhFt4Vertex *b, double x, double y) {
    return (x - (double)a->x) * ((double)b->y - a->y)
         - (y - (double)a->y) * ((double)b->x - a->x);
}

static inline int vh_ft4_inputs_valid(
    const VhCanvas *canvas, const uint32_t *texture,
    size_t tex_width, size_t tex_height, size_t tex_stride,
    const VhFt4Vertex corners[4]) {
    size_t i;
    if (!canvas || !canvas->pixels || !texture || !corners ||
        canvas->width < 1 || canvas->height < 1 ||
        canvas->stride_pixels < (size_t)canvas->width ||
        canvas->stride_pixels > SIZE_MAX / (size_t)canvas->height ||
        tex_width < 1 || tex_height < 1 ||
        tex_width > INT_MAX || tex_height > INT_MAX ||
        tex_stride < tex_width || tex_stride > SIZE_MAX / tex_height) {
        return 0;
    }
    for (i = 0; i < 4; ++i) {
        const VhFt4Vertex *p = &corners[i];
        if (!isfinite(p->x) || !isfinite(p->y) ||
            !isfinite(p->u) || !isfinite(p->v) ||
            p->u < 0.0f || p->v < 0.0f ||
            p->u > (float)(tex_width - 1) ||
            p->v > (float)(tex_height - 1)) {
            return 0;
        }
    }
    return 1;
}

/*
 * Affine triangle rasterization of POLY_FT4 triangles (0,1,2) & (1,3,2).
 * Pixel-center sampling and nearest texel. Winding can be CW or CCW.
 * Returns pixels written (overlapping shared-edge pixels counted twice).
 *
 * The target canvas and texture must not alias. No alpha/zero/STP treatment:
 * colors are copied as caller-provided RGBA32 words.
 */
static inline size_t vh_canvas_draw_ft4_rgba32(
    VhCanvas *canvas, const uint32_t *texture,
    size_t tex_width, size_t tex_height, size_t tex_stride,
    const VhFt4Vertex corners[4]) {
    static const int triangles[2][3] = {{0, 1, 2}, {1, 3, 2}};
    size_t written = 0;
    int tri;
    if (!vh_ft4_inputs_valid(canvas, texture, tex_width, tex_height,
                             tex_stride, corners)) return 0;

    for (tri = 0; tri < 2; ++tri) {
        const VhFt4Vertex *a = &corners[triangles[tri][0]];
        const VhFt4Vertex *b = &corners[triangles[tri][1]];
        const VhFt4Vertex *c = &corners[triangles[tri][2]];
        double area = vh_ft4_edge(a, b, c->x, c->y);
        double min_x, max_x, min_y, max_y;
        int first_x, last_x, first_y, last_y, x, y;
        if (!isfinite(area) || area == 0.0) continue;
        min_x = a->x < b->x ? a->x : b->x;
        min_x = c->x < min_x ? c->x : min_x;
        max_x = a->x > b->x ? a->x : b->x;
        max_x = c->x > max_x ? c->x : max_x;
        min_y = a->y < b->y ? a->y : b->y;
        min_y = c->y < min_y ? c->y : min_y;
        max_y = a->y > b->y ? a->y : b->y;
        max_y = c->y > max_y ? c->y : max_y;

        /* Clip before converting bounds to int: oversized floats cannot
         * overflow loop indices, and fully off-screen triangles cost O(1). */
        if (max_x < 0.0 || max_y < 0.0 ||
            min_x >= (double)canvas->width ||
            min_y >= (double)canvas->height) continue;
        first_x = (int)(min_x < 0.0 ? 0.0 : min_x);
        first_y = (int)(min_y < 0.0 ? 0.0 : min_y);
        last_x = (int)(max_x >= canvas->width ? canvas->width - 1 : max_x);
        last_y = (int)(max_y >= canvas->height ? canvas->height - 1 : max_y);
        for (y = first_y; y <= last_y; ++y) {
            for (x = first_x; x <= last_x; ++x) {
                double px = (double)x + 0.5, py = (double)y + 0.5;
                double alpha = vh_ft4_edge(b, c, px, py) / area;
                double beta  = vh_ft4_edge(c, a, px, py) / area;
                double gamma = vh_ft4_edge(a, b, px, py) / area;
                double u, v;
                size_t tx, ty;
                if (alpha < -1e-12 || beta < -1e-12 || gamma < -1e-12)
                    continue;
                u = alpha * a->u + beta * b->u + gamma * c->u;
                v = alpha * a->v + beta * b->v + gamma * c->v;
                if (u < 0.0) u = 0.0;
                if (v < 0.0) v = 0.0;
                if (u > (double)(tex_width - 1)) u = (double)(tex_width - 1);
                if (v > (double)(tex_height - 1)) v = (double)(tex_height - 1);
                tx = (size_t)(u + 0.5);
                ty = (size_t)(v + 0.5);
                canvas->pixels[(size_t)y * canvas->stride_pixels + (size_t)x] =
                    texture[ty * tex_stride + tx];
                ++written;
            }
        }
    }
    return written;
}

#endif
