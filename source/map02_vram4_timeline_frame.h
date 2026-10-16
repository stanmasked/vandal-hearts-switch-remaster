#ifndef VH_MAP02_VRAM4_TIMELINE_FRAME_H
#define VH_MAP02_VRAM4_TIMELINE_FRAME_H

/*
 * One frozen VRAM snapshot PER submitted MAP02 terrain polygon.
 *
 * The existing map02_vram4_frame.h accepts one snapshot for the whole
 * frame, which is only safe when VRAM remains unchanged at every texture
 * fetch. This opt-in timeline compositor instead materializes each atlas
 * and CLUT from its own caller-supplied submission-time VRAM image.
 *
 * The indices/frame labels establish internal consistency only; they do
 * not authenticate gameplay, prove uninterrupted GPU-write observation
 * or make the CPU affine FT4 rasterizer bit-accurate to the PS1 GPU.
 * No game assets, allocations or I/O are included.
 *
 * Inputs, scene buffers, texture buffers, and every VRAM snapshot must
 * remain frozen and non-overlapping through construction/drawing.
 */
#include <stddef.h>
#include <stdint.h>
#include "map02_vram4_frame.h"

typedef struct {
    VhMap02Vram4FrameFace face;
    const uint8_t *vram_le;
    size_t vram_bytes;
    uint64_t vram_snapshot_frame;
    size_t submission_index;
    size_t vram_snapshot_index;
} VhMap02Vram4TimelineEntry;

typedef struct {
    uint64_t frame;
    const uint8_t *decoded;
    size_t decoded_bytes;
    const VhMap02Vram4TimelineEntry *entries;
    size_t count;
    size_t ot_size;
} VhMap02Vram4TimelineInput;

/*
 * Validate the WHOLE timeline before touching output/workspace memory.
 * Requiring submission/snapshot index == i prevents swapped, missing or
 * reused snapshots from silently masquerading as the captured ordering.
 */
static inline int vh_map02_vram4_timeline_preflight(
    const VhMap02Vram4TimelineInput *input,
    const VhMap02Vram4FrameWorkspace *workspace) {
    size_t i, j;
    VhMap02ExternalPreparedFace proof;
    if (!input || !workspace || !input->decoded || !input->entries ||
        !workspace->bucket_heads || !workspace->nodes ||
        !workspace->prepared || !workspace->atlases ||
        !workspace->palettes || !workspace->stats ||
        input->frame == UINT64_C(0) ||
        input->decoded_bytes != VH_MAP02_EXTERNAL_DECODED_BYTES ||
        input->count == 0u ||
        input->count > VH_MAP02_VRAM4_FRAME_MAX_FACES ||
        input->count > workspace->face_capacity ||
        input->ot_size < 5u || input->ot_size > workspace->bucket_capacity ||
        workspace->atlas_capacity_bytes /
            VH_MAP02_VRAM4_ATLAS_BYTES < input->count ||
        workspace->palette_capacity_bytes /
            VH_MAP02_VRAM4_CLUT_BYTES < input->count)
        return 0;
    for (i = 0u; i < input->count; ++i) {
        const VhMap02Vram4TimelineEntry *entry = &input->entries[i];
        const VhMap02Vram4FrameFace *face = &entry->face;
        if (!entry->vram_le ||
            entry->vram_bytes != VH_MAP02_VRAM_BYTES ||
            entry->vram_snapshot_frame != input->frame ||
            entry->submission_index != i ||
            entry->vram_snapshot_index != i ||
            face->observation_frame != input->frame ||
            face->gpu_register_frame != input->frame ||
            !vh_map02_vram4_registers_valid(&face->registers) ||
            !vh_map02_prepare_external_face(
                input->decoded, input->decoded_bytes, &face->face,
                input->ot_size, &proof))
            return 0;
        for (j = 0u; j < i; ++j)
            if (face->face.record_index ==
                    input->entries[j].face.face.record_index &&
                face->face.face_index ==
                    input->entries[j].face.face.face_index)
                return 0;
    }
    return 1;
}

/* Same OT insertion order as the original ClearOTag/AddPrim path.
 * All source and snapshot errors fail before the first output write.
 * As with vh_map02_vram4_frame_build(), the caller must not mutate input
 * after preflight: post-validation failures indicate contract violation. */
static inline int vh_map02_vram4_timeline_build(
    const VhMap02Vram4TimelineInput *input,
    VhMap02Vram4FrameWorkspace *workspace) {
    size_t i;
    if (!vh_map02_vram4_timeline_preflight(input, workspace))
        return 0;
    if (!vh_map02_ot_scene_init(
            &workspace->scene, workspace->bucket_heads, input->ot_size,
            workspace->nodes, workspace->face_capacity))
        return 0;
    for (i = 0u; i < input->count; ++i) {
        const VhMap02Vram4TimelineEntry *entry = &input->entries[i];
        const VhMap02Vram4FrameFace *face = &entry->face;
        uint8_t *atlas = workspace->atlases +
                         i * VH_MAP02_VRAM4_ATLAS_BYTES;
        uint8_t *palette = workspace->palettes +
                           i * VH_MAP02_VRAM4_CLUT_BYTES;
        if (!vh_map02_prepare_external_face(
                input->decoded, input->decoded_bytes, &face->face,
                input->ot_size, &workspace->prepared[i]) ||
            !vh_map02_vram4_materialize(
                entry->vram_le, entry->vram_bytes, &face->registers,
                atlas, VH_MAP02_VRAM4_ATLAS_BYTES,
                palette, VH_MAP02_VRAM4_CLUT_BYTES,
                &workspace->stats[i]) ||
            vh_map02_ot_scene_add(
                &workspace->scene, &workspace->prepared[i].quad,
                atlas, VH_MAP02_VRAM4_ATLAS_BYTES,
                palette, VH_MAP02_VRAM4_CLUT_BYTES,
                face->blend, face->blend_context) != 2)
            return 0;
    }
    return workspace->scene.count == input->count;
}

#endif
