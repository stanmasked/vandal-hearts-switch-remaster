#ifndef VH_MAP02_CAPTURED_VRAM4_BRIDGE_H
#define VH_MAP02_CAPTURED_VRAM4_BRIDGE_H

/*
 * Source-keyed captured GTE -> per-primitive VRAM4 frame bridge.
 *
 * This is a diagnostic staging layer, NOT evidence of an authentic PC game
 * capture or hardware-accurate rendering. The caller supplies immutable
 * MAP02 bytes, source-keyed cameras/UVWH, same-frame GTE observations, and
 * original GPU texture register observations. It does not guess missing
 * face placement, UV, CLUT, or texture window registers.
 *
 * A successful return produces only the NCLIP-visible submissions, in their
 * original order. Culled polygons never enter the GPU ordering table.
 * Output and *out_count are unchanged for ANY invalid source, projection,
 * texture register or capacity. All input/output storage must not overlap.
 * The caller must independently verify provenance and VRAM timing before
 * treating a staged frame as original gameplay.
 */
#include <stddef.h>
#include <stdint.h>
#include "map02_captured_projection_batch.h"
#include "map02_vram4_frame.h"

typedef struct {
    uint64_t frame; /* same measured frame as camera and submitted polygon */
    VhMap02Vram4Registers registers;
    VhFt4StpBlendFn blend;
    void *blend_context;
} VhMap02CapturedTextureState;

static inline int vh_map02_stage_captured_vram4_faces(
    const uint8_t *decoded, size_t decoded_bytes,
    const VhMap02SourceFaceRequest *requests,
    const VhMap02CapturedFaceProjection *observations,
    const VhMap02CapturedTextureState *textures,
    size_t count, size_t ot_size,
    VhMap02Vram4FrameFace *out, size_t capacity,
    size_t *out_count) {
    VhMap02SourceProjectedFace projected[VH_MAP02_SOURCE_BATCH_MAX];
    VhMap02Vram4FrameFace staged[VH_MAP02_SOURCE_BATCH_MAX];
    size_t i, j, accepted = 0u;
    uint64_t frame;

    if (!decoded || !requests || !observations || !textures ||
        !out || !out_count || count == 0u ||
        count > VH_MAP02_SOURCE_BATCH_MAX || capacity == 0u ||
        !vh_map02_verify_captured_projection_batch(
            decoded, decoded_bytes, requests, observations, count,
            ot_size, projected, VH_MAP02_SOURCE_BATCH_MAX))
        return 0;
    frame = observations[0].frame;
    for (i = 0u; i < count; ++i) {
        const VhMap02SourceFaceRequest *request = &requests[i];
        const VhMap02CapturedFaceProjection *observed = &observations[i];
        const VhMap02CapturedTextureState *texture = &textures[i];
        const VhMap02TerrainQuad *quad = &projected[i].quad;
        VhMap02ExternalFaceEvidence *ev;
        VhMap02ExternalPreparedFace proof;
        const uint8_t *tile;
        static const unsigned face_for_gpu[4] = {0u,1u,3u,2u};

        if (texture->frame != frame)
            return 0;
        if (!observed->visible)
            continue;
        if (!vh_map02_vram4_registers_valid(&texture->registers) ||
            accepted >= capacity)
            return 0;
        tile = decoded + (size_t)request->record_index *
                         VH_MAP02_FACE_RECORD_BYTES;
        staged[accepted] = (VhMap02Vram4FrameFace){0};
        staged[accepted].observation_frame = frame;
        staged[accepted].gpu_register_frame = texture->frame;
        staged[accepted].registers = texture->registers;
        staged[accepted].blend = texture->blend;
        staged[accepted].blend_context = texture->blend_context;
        ev = &staged[accepted].face;
        ev->z = request->z;
        ev->x = request->x;
        ev->record_index = request->record_index;
        ev->face_index = request->face_index;
        ev->local_gfx = quad->material;
        ev->face_shade = quad->shade;
        ev->raw_otz = observed->raw_otz;
        ev->u = request->u;
        ev->v = request->v;
        ev->w = request->w;
        ev->h = request->h;
        for (j = 0u; j < 4u; ++j) {
            const unsigned vi =
                tile[212u + (size_t)request->face_index * 4u + j];
            const unsigned gpu = face_for_gpu[j];
            unsigned axis;
            ev->vertex_indices[j] = (int32_t)vi;
            for (axis = 0u; axis < 3u; ++axis)
                ev->vertex_xyz[j][axis] = (int32_t)vh_map02_quad_s16(
                    tile, (size_t)vi * 8u + (size_t)axis * 2u);
            ev->perimeter_xy[j][0] = observed->gpu_xy[gpu][0];
            ev->perimeter_xy[j][1] = observed->gpu_xy[gpu][1];
        }
        /* Independently verify against the original source-keyed FT4
         * materializer used by the VRAM4 frame builder. */
        if (!vh_map02_prepare_external_face(
                decoded, decoded_bytes, ev, ot_size, &proof))
            return 0;
        for (j = 0u; j < 4u; ++j) {
            if (proof.quad.gpu_ft4[j].x != quad->gpu_ft4[j].x ||
                proof.quad.gpu_ft4[j].y != quad->gpu_ft4[j].y ||
                proof.quad.gpu_ft4[j].u != quad->gpu_ft4[j].u ||
                proof.quad.gpu_ft4[j].v != quad->gpu_ft4[j].v)
                return 0;
        }
        ++accepted;
    }
    if (accepted == 0u) return 0; /* VRAM4 frame needs a submission */
    for (i = 0u; i < accepted; ++i)
        out[i] = staged[i];
    *out_count = accepted;
    return 1;
}

#endif
