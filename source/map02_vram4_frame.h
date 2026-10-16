#ifndef VH_MAP02_VRAM4_FRAME_H
#define VH_MAP02_VRAM4_FRAME_H

/*
 * Prepare one source-keyed MAP02 4bpp terrain draw frame, no heap or I/O.
 *
 * Inputs must be frozen, non-overlapping, caller-owned evidence:
 *   - exactly one decoded 187264-byte MAP02 buffer;
 *   - one full 1024x512x16-bit VRAM snapshot;
 *   - externally obtained screen/OTZ/UVWH and per-primitive tpage/CLUT/
 *     GP0(E2) texture window, all labelled with one frame identifier.
 *
 * A matching frame identifier is a CONSISTENCY CHECK, not a signature
 * or proof that the real game provided any of these values. The VRAM
 * image must correspond to the GPU read time for EVERY submitted face.
 * If the game writes VRAM between submissions, a single snapshot is
 * insufficient: use multiple snapshots and a later replay mechanism.
 *
 * This is an opt-in, terrain-only CPU diagnostic, not live Switch game
 * rendering or bit-accurate PS1 GPU output. The caller may subsequently
 * invoke vh_map02_ot_scene_draw on workspace.scene. No proprietary
 * source game data is bundled with this interface.
 */
#include <stddef.h>
#include <stdint.h>
#include "map02_external_gte_ft4.h"
#include "map02_vram4_page.h"

#define VH_MAP02_VRAM4_FRAME_MAX_FACES 32u

typedef struct {
    uint64_t observation_frame;
    uint64_t gpu_register_frame;
    VhMap02ExternalFaceEvidence face;
    VhMap02Vram4Registers registers;
    VhFt4StpBlendFn blend;
    void *blend_context;
} VhMap02Vram4FrameFace;

typedef struct {
    uint64_t frame;
    uint64_t vram_snapshot_frame;
    const uint8_t *decoded;
    size_t decoded_bytes;
    const uint8_t *vram_le;
    size_t vram_bytes;
    const VhMap02Vram4FrameFace *faces;
    size_t face_count;
    size_t ot_size;
} VhMap02Vram4FrameInput;

typedef struct {
    VhMap02OtTerrainScene scene;
    size_t *bucket_heads;
    size_t bucket_capacity;
    VhMap02OtTerrainNode *nodes;
    VhMap02ExternalPreparedFace *prepared;
    uint8_t *atlases;
    size_t atlas_capacity_bytes;
    uint8_t *palettes;
    size_t palette_capacity_bytes;
    VhMap02Vram4PageStats *stats;
    size_t face_capacity;
} VhMap02Vram4FrameWorkspace;

/* Strict complete preflight. Never mutate output buffers. In addition
 * to valid sources, require all submissions to be uniquely identified by
 * record_index + face_index, NOT their (possibly identical) material.
 */
static inline int vh_map02_vram4_frame_preflight(
    const VhMap02Vram4FrameInput *input,
    const VhMap02Vram4FrameWorkspace *workspace) {
    size_t i, j;
    VhMap02ExternalPreparedFace one;
    if (!input || !workspace || !input->decoded || !input->vram_le ||
        !input->faces || !workspace->bucket_heads || !workspace->nodes ||
        !workspace->prepared || !workspace->atlases || !workspace->palettes ||
        !workspace->stats ||
        input->frame == UINT64_C(0) ||
        input->frame != input->vram_snapshot_frame ||
        input->decoded_bytes != VH_MAP02_EXTERNAL_DECODED_BYTES ||
        input->vram_bytes != VH_MAP02_VRAM_BYTES ||
        input->face_count == 0u ||
        input->face_count > VH_MAP02_VRAM4_FRAME_MAX_FACES ||
        input->face_count > workspace->face_capacity ||
        input->ot_size < 5u || input->ot_size > workspace->bucket_capacity ||
        workspace->atlas_capacity_bytes /
            VH_MAP02_VRAM4_ATLAS_BYTES < input->face_count ||
        workspace->palette_capacity_bytes /
            VH_MAP02_VRAM4_CLUT_BYTES < input->face_count)
        return 0;
    for (i = 0u; i < input->face_count; ++i) {
        const VhMap02Vram4FrameFace *face = &input->faces[i];
        if (face->observation_frame != input->frame ||
            face->gpu_register_frame != input->frame ||
            !vh_map02_vram4_registers_valid(&face->registers) ||
            !vh_map02_prepare_external_face(
                input->decoded, input->decoded_bytes,
                &face->face, input->ot_size, &one))
            return 0;
        for (j = 0u; j < i; ++j) {
            const VhMap02ExternalFaceEvidence *prev = &input->faces[j].face;
            if (face->face.record_index == prev->record_index &&
                face->face.face_index == prev->face_index)
                return 0;
        }
    }
    return 1;
}

/* Returns 1 when a complete scene is built. On any validation failure
 * returns 0 BEFORE touching workspace state, atlas, CLUT, or stats.
 * The staged face, source, VRAM and register buffers must remain immutable.
 * The constructor must not be invoked with aliased input/output buffers.
 * Runtime C source materializer/OT add are already preflighted; their
 * failures after preflight would indicate mutating input/contract breach.
 */
static inline int vh_map02_vram4_frame_build(
    const VhMap02Vram4FrameInput *input,
    VhMap02Vram4FrameWorkspace *workspace) {
    size_t i;
    if (!vh_map02_vram4_frame_preflight(input, workspace))
        return 0;
    if (!vh_map02_ot_scene_init(
            &workspace->scene, workspace->bucket_heads, input->ot_size,
            workspace->nodes, workspace->face_capacity))
        return 0;
    for (i = 0u; i < input->face_count; ++i) {
        const VhMap02Vram4FrameFace *face = &input->faces[i];
        uint8_t *atlas = workspace->atlases +
                         i * VH_MAP02_VRAM4_ATLAS_BYTES;
        uint8_t *palette = workspace->palettes +
                           i * VH_MAP02_VRAM4_CLUT_BYTES;
        if (!vh_map02_prepare_external_face(
                input->decoded, input->decoded_bytes, &face->face,
                input->ot_size, &workspace->prepared[i]))
            return 0;
        if (!vh_map02_vram4_materialize(
                input->vram_le, input->vram_bytes, &face->registers,
                atlas, VH_MAP02_VRAM4_ATLAS_BYTES,
                palette, VH_MAP02_VRAM4_CLUT_BYTES,
                &workspace->stats[i]))
            return 0;
        if (vh_map02_ot_scene_add(
                &workspace->scene, &workspace->prepared[i].quad,
                atlas, VH_MAP02_VRAM4_ATLAS_BYTES,
                palette, VH_MAP02_VRAM4_CLUT_BYTES,
                face->blend, face->blend_context) != 2)
            return 0;
    }
    return workspace->scene.count == input->face_count;
}
#endif
