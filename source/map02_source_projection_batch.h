#ifndef VH_MAP02_SOURCE_PROJECTION_BATCH_H
#define VH_MAP02_SOURCE_PROJECTION_BATCH_H

/*
 * Source-keyed MAP02 tile/face -> portable GTE -> FT4 batch adapter.
 *
 * Requires one full decoded MAP02 buffer (616 * 304 bytes) and an explicit
 * camera and UVWH for EACH face. Cameras are supplied by the caller: they
 * are NOT reconstructed or authenticated by this adapter. In particular,
 * separate tile-local model transforms must already be reflected in the
 * supplied GTE state. No world grid-spacing guess is made here.
 *
 * The output preserves caller submission order, but does not create a
 * GPU ordering table or render pixels. Only synthetic/test data is bundled.
 * All inputs and outputs must be distinct, non-overlapping buffers and
 * must remain immutable during this call.
 */
#include <stddef.h>
#include <stdint.h>
#include "map02_terrain_quad.h"

#define VH_MAP02_SOURCE_STRIDE 28u
#define VH_MAP02_SOURCE_ACTIVE_X 24u
#define VH_MAP02_SOURCE_ACTIVE_Z 12u
#define VH_MAP02_SOURCE_RECORDS (VH_MAP02_SOURCE_STRIDE * 22u)
#define VH_MAP02_SOURCE_DECODED_BYTES (VH_MAP02_SOURCE_RECORDS * VH_MAP02_FACE_RECORD_BYTES)
#define VH_MAP02_SOURCE_BATCH_MAX 32u

typedef struct {
    int32_t z, x, record_index, face_index;
    VhMap02ProjectCamera camera; /* explicitly supplied GTE register state */
    int u, v, w, h;              /* explicitly supplied UVWH */
} VhMap02SourceFaceRequest;

typedef struct {
    int32_t z, x, record_index, face_index;
    VhMap02TerrainQuad quad;
} VhMap02SourceProjectedFace;

/*
 * Fail closed: no output entry is overwritten unless every source-keyed
 * face has been decoded and prepared successfully. Different faces in one
 * tile and faces from different tiles may occur in the same input batch.
 * A nonzero return does NOT mean a face is visible or drawable; inspect
 * each output quad, exactly as with vh_map02_prepare_terrain_quad().
 */
static inline int vh_map02_project_source_batch(
    const uint8_t *decoded, size_t decoded_bytes,
    const VhMap02SourceFaceRequest *requests, size_t count,
    size_t ot_size, VhMap02SourceProjectedFace *out, size_t capacity) {
    VhMap02SourceProjectedFace staged[VH_MAP02_SOURCE_BATCH_MAX];
    size_t i, j;
    if (!decoded || !requests || !out ||
        decoded_bytes != VH_MAP02_SOURCE_DECODED_BYTES ||
        count == 0u || count > VH_MAP02_SOURCE_BATCH_MAX ||
        count > capacity || ot_size < 5u)
        return 0;
    for (i = 0u; i < count; ++i) {
        const VhMap02SourceFaceRequest *r = &requests[i];
        size_t record;
        if (r->z < 0 || r->z >= (int32_t)VH_MAP02_SOURCE_ACTIVE_Z ||
            r->x < 0 || r->x >= (int32_t)VH_MAP02_SOURCE_ACTIVE_X ||
            r->face_index < 0 ||
            r->face_index >= (int32_t)VH_MAP02_FACE_MAX_COUNT)
            return 0;
        record = (size_t)r->z * VH_MAP02_SOURCE_STRIDE + (size_t)r->x;
        if (r->record_index != (int32_t)record)
            return 0;
        for (j = 0u; j < i; ++j)
            if (requests[j].record_index == r->record_index &&
                requests[j].face_index == r->face_index)
                return 0;
        staged[i].z = r->z;
        staged[i].x = r->x;
        staged[i].record_index = r->record_index;
        staged[i].face_index = r->face_index;
        if (!vh_map02_prepare_terrain_quad(
                decoded + record * VH_MAP02_FACE_RECORD_BYTES,
                VH_MAP02_FACE_RECORD_BYTES, (unsigned)r->face_index,
                &r->camera, ot_size, r->u, r->v, r->w, r->h,
                &staged[i].quad))
            return 0;
    }
    for (i = 0u; i < count; ++i)
        out[i] = staged[i];
    return 1;
}

#endif
