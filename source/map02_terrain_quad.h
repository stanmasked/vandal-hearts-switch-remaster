#ifndef VH_MAP02_TERRAIN_QUAD_H
#define VH_MAP02_TERRAIN_QUAD_H

/*
 * MAP02 opt-in source-local terrain polygon -> projected GPU FT4 -> RGBA32.
 * A small, portable integration seam: this is NOT yet connected to the
 * live Switch renderer, and NOT evidence of real MAP02 visible pixels.
 *
 * Sources:
 * - pinned US PC-port field.h: 304-byte MapTileModel, 22 SVECTORs (8 bytes),
 *   gfx[18], faces[18][4], shades[18], faceCt at 302.
 * - original RenderMapTile: GFX_NULL=0 skip; first three RTPT/NCLIP,
 *   face[3] RTPS, POLY_FT4 x0/x1/x3/x2, AVSZ4 and OT_SIZE-depth.
 * - 4-bit indexed atlas CLUT and FT4 draw paths already audited separately.
 *
 * The caller MUST supply authentic source UVWH, camera and BGR555 palette;
 * this code does not invent map/texture associations or world placement.
 * No allocations or file I/O; all buffers are caller-owned. CPU FT4 uses
 * an approximate affine rasterizer, NOT bit-exact PS1 GPU rasterization.
 */
#include <stddef.h>
#include <stdint.h>

#include "map02_projection.h"
#include "ft4_textured_quad.h"
#include "ps1_indexed_texture.h"

#define VH_MAP02_FACE_RECORD_BYTES 304u
#define VH_MAP02_FACE_MODEL_VERTICES 22u
#define VH_MAP02_FACE_MAX_COUNT 18u

typedef struct {
    int16_t material;          /* exact tile.gfx[face], no +400 guess */
    uint8_t shade;
    uint8_t face;
    uint8_t drawable;          /* nonzero material, NCLIP > 0, valid OT slot */
    int u, v, w, h;            /* EXTERNAL confirmed atlas UVWH */
    VhMap02ProjectFace projection;
    VhFt4Vertex gpu_ft4[4];   /* original GPU corner order 0/1/2/3 */
} VhMap02TerrainQuad;

static inline int16_t vh_map02_quad_s16(
    const uint8_t *source, size_t offset) {
    uint16_t b = (uint16_t)source[offset] |
                 (uint16_t)((uint16_t)source[offset + 1u] << 8);
    return (int16_t)(b <= 32767u ? (int32_t)b : (int32_t)b - 65536);
}

/*
 * Returns 0 on invalid records/arguments, writing no result. Returns 1
 * for a valid face even if it has no material, is culled or is outside OT.
 * Does not mutate caller tile or camera. Material==0 matches GFX_NULL:
 * skip projection, matching RenderMapTile's material-first gate.
 */
static inline int vh_map02_prepare_terrain_quad(
    const uint8_t *tile, size_t tile_bytes,
    unsigned face_index, const VhMap02ProjectCamera *camera,
    size_t ot_size, int u, int v, int w, int h,
    VhMap02TerrainQuad *out) {
    VhMap02TerrainQuad q = {0};
    VhMap02ProjectVertex corners[4];
    VhFt4Point perimeter[4];
    unsigned i, j;
    if (!tile || !camera || !out || tile_bytes != VH_MAP02_FACE_RECORD_BYTES ||
        face_index >= VH_MAP02_FACE_MAX_COUNT ||
        tile[302] > VH_MAP02_FACE_MAX_COUNT ||
        face_index >= tile[302] ||
        u < 0 || v < 0 || u > 255 || v > 255 ||
        w < 1 || h < 1 || w > 255-u || h > 255-v)
        return 0;
    q.face = (uint8_t)face_index;
    q.material = vh_map02_quad_s16(tile, 176u + 2u * face_index);
    q.shade = tile[284u + face_index];
    q.u = u; q.v = v; q.w = w; q.h = h;
    if (q.material == 0) {
        *out = q;
        return 1;
    }
    for (i = 0; i < 4u; ++i) {
        unsigned vi = tile[212u + face_index * 4u + i];
        if (vi >= VH_MAP02_FACE_MODEL_VERTICES) return 0;
        for (j = 0; j < 3u; ++j) {
            int16_t val = vh_map02_quad_s16(tile, vi * 8u + j * 2u);
            if (j == 0u) corners[i].x = val;
            else if (j == 1u) corners[i].y = val;
            else corners[i].z = val;
        }
    }
    if (!vh_map02_project_face(camera, corners, ot_size, &q.projection))
        return 0;
    if (q.projection.visible && q.projection.ot_in_bounds) {
        /* Projection is ALREADY in GPU order 0,1,2,3. Convert to source
         * perimeter before calling the UV/FT4 converter, avoiding a
         * double permutation of face[2] and face[3]. */
        static const unsigned gpu_for_face[4] = {0u,1u,3u,2u};
        for (i = 0; i < 4u; ++i) {
            const VhMap02ProjectSxy p = q.projection.gpu[gpu_for_face[i]];
            perimeter[i].x = (float)p.x;
            perimeter[i].y = (float)p.y;
        }
        if (!vh_ft4_from_face_perimeter(perimeter, u, v, w, h, q.gpu_ft4))
            return 0;
        q.drawable = 1u;
    }
    *out = q;
    return 1;
}

/*
 * Draw one prepared face directly from the original 256x256 4-bpp atlas
 * and supplied 16-color BGR555 CLUT. The caller allocates scratch
 * (w+1)*(h+1) RGBA32 pixels and class bytes, without any heap usage.
 * Returns 0 only on invalid arguments, 1 on a valid no-op or draw.
 * Successful returned pixel count is available in out_written.
 *
 * Transparent BGR555 == 0 pixels are skipped; nonzero STP is emitted
 * with caller-chosen blend function. With no blend callback, STP is
 * copied opaque for diagnostic purposes, not assumed to be alpha.
 * Caller ensures scratch, atlas, CLUT and framebuffer do not alias.
 */
static inline int vh_map02_draw_terrain_4bpp(
    VhCanvas *canvas, const VhMap02TerrainQuad *quad,
    const uint8_t *atlas4, size_t atlas_bytes,
    const uint8_t *clut_le, size_t clut_bytes,
    uint32_t *scratch_rgba, uint8_t *scratch_classes,
    size_t scratch_pixels, VhPs1RgbPackFn pack, void *pack_context,
    VhFt4StpBlendFn blend, void *blend_context, size_t *out_written) {
    size_t cols, rows, required, written;
    VhFt4Vertex crop_ft4[4];
    unsigned i;
    if (!canvas || !canvas->pixels || !quad || !out_written ||
        canvas->width < 1 || canvas->height < 1 ||
        canvas->stride_pixels < (size_t)canvas->width ||
        !atlas4 || !clut_le || !scratch_rgba || !scratch_classes || !pack ||
        atlas_bytes < (size_t)256u * 128u || clut_bytes < 32u ||
        quad->u < 0 || quad->v < 0 ||
        quad->w < 1 || quad->h < 1 ||
        quad->u > 255 || quad->v > 255 ||
        quad->w > 255-quad->u || quad->h > 255-quad->v)
        return 0;
    cols = (size_t)quad->w + 1u;
    rows = (size_t)quad->h + 1u;
    required = cols * rows;
    if (scratch_pixels < required) return 0;
    if (!quad->drawable) {
        *out_written = 0;
        return 1;
    }
    for (i = 0; i < 4u; ++i) {
        crop_ft4[i] = quad->gpu_ft4[i];
        crop_ft4[i].u -= (float)quad->u;
        crop_ft4[i].v -= (float)quad->v;
    }
    if (!vh_ft4_inputs_valid(canvas, scratch_rgba, cols, rows, cols, crop_ft4))
        return 0;
    if (!vh_ps1_decode_clut4_crop_classified(
            atlas4, atlas_bytes, 256u, 256u, 128u,
            clut_le, clut_bytes, (size_t)quad->u, (size_t)quad->v,
            cols, rows, scratch_rgba, cols,
            scratch_classes, cols, pack, pack_context, NULL))
        return 0;
    written = vh_canvas_draw_ft4_classified_rgba32(
        canvas, scratch_rgba, cols, rows, cols,
        crop_ft4, scratch_classes, cols, blend, blend_context);
    *out_written = written;
    return 1;
}
#endif
