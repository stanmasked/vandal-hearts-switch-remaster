#ifndef VH_MAP02_TERRAIN_OT_SCENE_H
#define VH_MAP02_TERRAIN_OT_SCENE_H

/*
 * Asset-free ordering-table compositor for prepared MAP02 terrain FT4s.
 *
 * This reproduces the traversal order in the pinned public PC-port
 * platform/pc/src/libgpu.c (ClearOTag, AddPrim, DrawOTag):
 * bucket 0 -> bucket n-1, with AddPrim inserting at the HEAD of a
 * bucket. The source renderer submits at slot OT_SIZE - max(5,OTZ).
 * This means distant/high-OTZ faces draw before near/low-OTZ faces,
 * and two faces with the same slot draw in reverse submission order.
 *
 * This is a CPU diagnostic compositing interface, not a PS1 GPU emulator.
 * Real gameplay also submits sprites, environment packets and other
 * polygons; this scene contains ONLY caller-submitted terrain quads.
 * No owned assets, guessed UV/CLUT associations, allocation or I/O.
 */
#include <stddef.h>
#include <stdint.h>
#include "map02_terrain_quad.h"

typedef struct {
    const VhMap02TerrainQuad *quad;
    const uint8_t *atlas4;
    size_t atlas_bytes;
    const uint8_t *clut_le;
    size_t clut_bytes;
    VhFt4StpBlendFn stp_blend;
    void *blend_context;
    size_t next; /* SIZE_MAX is the end-of-bucket sentinel */
} VhMap02OtTerrainNode;

typedef struct {
    size_t *heads;                  /* caller-owned array of ot_size entries */
    size_t ot_size;
    VhMap02OtTerrainNode *nodes;    /* caller-owned array of capacity entries */
    size_t capacity;
    size_t count;
} VhMap02OtTerrainScene;

/* ClearOTag-equivalent reset. Existing node pointers are not dereferenced;
 * inputs must stay alive for the duration of a frame. */
static inline int vh_map02_ot_scene_init(
    VhMap02OtTerrainScene *scene, size_t *heads, size_t ot_size,
    VhMap02OtTerrainNode *nodes, size_t capacity) {
    size_t i;
    if (!scene || !heads || !nodes || ot_size < 5u || capacity == 0u)
        return 0;
    for (i = 0; i < ot_size; ++i) heads[i] = SIZE_MAX;
    *scene = (VhMap02OtTerrainScene){
        heads, ot_size, nodes, capacity, 0u
    };
    return 1;
}

/* Returns 0 invalid, 1 accepted-but-culled/no-material, 2 queued.
 * Insertion is O(1) just like original AddPrim, no sort or heap.
 * Caller must have prepared the quad against this exact ot_size.
 * Source texture/CLUT buffers and quad must remain alive and unchanged
 * until the scene has been rendered or reset.
 */
static inline int vh_map02_ot_scene_add(
    VhMap02OtTerrainScene *scene, const VhMap02TerrainQuad *quad,
    const uint8_t *atlas4, size_t atlas_bytes,
    const uint8_t *clut_le, size_t clut_bytes,
    VhFt4StpBlendFn blend, void *blend_context) {
    VhMap02OtTerrainNode node;
    size_t slot;
    if (!scene || !scene->heads || !scene->nodes || !quad ||
        scene->ot_size < 5u || scene->count > scene->capacity)
        return 0;
    if (!quad->drawable) return 1;
    if (!quad->projection.visible || !quad->projection.ot_in_bounds ||
        quad->material == 0 || quad->projection.depth < 5u ||
        quad->projection.depth > scene->ot_size ||
        quad->u < 0 || quad->v < 0 || quad->u > 255 || quad->v > 255 ||
        quad->w < 1 || quad->h < 1 ||
        quad->w > 255 - quad->u || quad->h > 255 - quad->v ||
        !atlas4 || atlas_bytes < 32768u ||
        !clut_le || clut_bytes < 32u ||
        scene->count == scene->capacity)
        return 0;
    slot = scene->ot_size - (size_t)quad->projection.depth;
    if (slot != quad->projection.ot_slot || slot >= scene->ot_size ||
        scene->heads[slot] != SIZE_MAX &&
            scene->heads[slot] >= scene->count)
        return 0;
    node = (VhMap02OtTerrainNode){
        quad, atlas4, atlas_bytes, clut_le, clut_bytes,
        blend, blend_context, scene->heads[slot]
    };
    scene->nodes[scene->count] = node;
    scene->heads[slot] = scene->count;
    scene->count++;
    return 2;
}

/*
 * Preflight the entire scene before writing a pixel. The quad and texture
 * buffers must not alias canvas/scratch, as for the underlying rasterizer.
 * Pixel/primitive counts are written only on successful completion.
 *
 * Drawing follows the actual PC-port forward OT chain. Checking the
 * bucket/next indices and depth linkage prevents broken OT pointer chains
 * from becoming out-of-bounds reads. Unused buckets are still traversed.
 */
static inline int vh_map02_ot_scene_draw(
    const VhMap02OtTerrainScene *scene, VhCanvas *canvas,
    uint32_t *scratch_rgba, uint8_t *scratch_classes,
    size_t scratch_pixels,
    VhPs1RgbPackFn pack, void *pack_context,
    size_t *out_primitives, size_t *out_pixels) {
    size_t phase, bucket;
    size_t drawn = 0u, pixels = 0u;
    if (!scene || !scene->heads || !scene->nodes || !canvas ||
        !canvas->pixels || !scratch_rgba || !scratch_classes || !pack ||
        !out_primitives || !out_pixels ||
        canvas->width <= 0 || canvas->height <= 0 ||
        canvas->stride_pixels < (size_t)canvas->width ||
        scene->count > scene->capacity || scene->ot_size < 5u)
        return 0;
    /* phase 0 validates the entire frame; phase 1 actually draws it.
     * Do not let malicious cyclic next pointers spin forever. */
    for (phase = 0; phase < 2u; ++phase) {
        size_t visited = 0u;
        for (bucket = 0; bucket < scene->ot_size; ++bucket) {
            size_t index = scene->heads[bucket];
            while (index != SIZE_MAX) {
                const VhMap02OtTerrainNode *node;
                size_t written = 0u, w, h;
                if (index >= scene->count || visited >= scene->count)
                    return 0;
                ++visited;
                node = &scene->nodes[index];
                if (!node->quad || !node->quad->drawable ||
                    !node->quad->projection.visible ||
                    !node->quad->projection.ot_in_bounds ||
                    node->quad->projection.depth < 5u ||
                    node->quad->projection.depth > scene->ot_size ||
                    scene->ot_size - node->quad->projection.depth != bucket ||
                    node->quad->projection.ot_slot != bucket ||
                    !node->atlas4 || node->atlas_bytes < 32768u ||
                    !node->clut_le || node->clut_bytes < 32u ||
                    node->quad->w < 1 || node->quad->w > 255 ||
                    node->quad->h < 1 || node->quad->h > 255 ||
                    node->quad->u < 0 || node->quad->v < 0 ||
                    node->quad->u > 255 - node->quad->w ||
                    node->quad->v > 255 - node->quad->h)
                    return 0;
                w = (size_t)node->quad->w + 1u;
                h = (size_t)node->quad->h + 1u;
                if (scratch_pixels < w * h) return 0;
                if (phase == 1u) {
                    if (!vh_map02_draw_terrain_4bpp(
                            canvas, node->quad, node->atlas4,
                            node->atlas_bytes, node->clut_le,
                            node->clut_bytes, scratch_rgba,
                            scratch_classes, scratch_pixels,
                            pack, pack_context, node->stp_blend,
                            node->blend_context, &written))
                        return 0;
                    ++drawn;
                    pixels += written;
                }
                index = node->next;
            }
        }
        if (visited != scene->count) return 0;
    }
    *out_primitives = drawn;
    *out_pixels = pixels;
    return 1;
}

#endif
