#ifndef VH_MAP02_CAPTURED_PROJECTION_BATCH_H
#define VH_MAP02_CAPTURED_PROJECTION_BATCH_H

/*
 * Strict diagnostic adapter for source-keyed MAP02 camera/GTE observations.
 *
 * Inputs contain an entire caller-owned decoded MAP02 buffer, exact face
 * requests (including camera registers and UVWH), and per-face observations
 * from ONE claimed gameplay frame. The adapter compares the compiled
 * portable PC-GTE model to captured NCLIP, raw AVSZ4 OTZ and GPU FT4 XY.
 *
 * A matching frame identifier and projection are consistency checks only.
 * They do NOT authenticate that the camera, GPU state, vertices or frame
 * came from the retail game. Bundle hashes, binary provenance and VRAM
 * timing require separate validation. No source assets are included.
 *
 * Inactive/null-material polygons are not valid camera observations.
 * A culled polygon uses raw_otz=-1 and zero screen coordinates.
 * An accepted, visible polygon must also fit the supplied OT size.
 * All caller-owned inputs/output must be distinct, non-overlapping buffers.
 */
#include <stddef.h>
#include <stdint.h>
#include "map02_source_projection_batch.h"

typedef struct {
    uint64_t frame;
    uint64_t camera_frame;
    int32_t z, x, record_index, face_index;
    int32_t nclip_mac0;
    int32_t raw_otz;           /* -1 for NCLIP-culled, 0..65535 visible */
    uint8_t visible;           /* exactly 0 or 1 */
    int16_t gpu_xy[4][2];      /* GPU POLY_FT4 order x0,x1,x2,x3 */
} VhMap02CapturedFaceProjection;

/*
 * Validate ALL samples before writing any output. The destination remains
 * unchanged on malformed camera provenance, source identity or GTE mismatch.
 * Return 1 for a consistent batch (including legitimately culled faces).
 */
static inline int vh_map02_verify_captured_projection_batch(
    const uint8_t *decoded, size_t decoded_bytes,
    const VhMap02SourceFaceRequest *requests,
    const VhMap02CapturedFaceProjection *observations,
    size_t count, size_t ot_size,
    VhMap02SourceProjectedFace *out, size_t capacity) {
    VhMap02SourceProjectedFace staged[VH_MAP02_SOURCE_BATCH_MAX];
    size_t i, k;
    uint64_t frame;
    if (!decoded || !requests || !observations || !out ||
        !count || count > VH_MAP02_SOURCE_BATCH_MAX || count > capacity)
        return 0;
    frame = observations[0].frame;
    if (!frame ||
        !vh_map02_project_source_batch(decoded, decoded_bytes, requests,
                                       count, ot_size, staged,
                                       VH_MAP02_SOURCE_BATCH_MAX))
        return 0;
    for (i = 0u; i < count; ++i) {
        const VhMap02SourceFaceRequest *request = &requests[i];
        const VhMap02CapturedFaceProjection *capture = &observations[i];
        const VhMap02TerrainQuad *quad = &staged[i].quad;
        if (capture->frame != frame || capture->camera_frame != frame ||
            capture->z != request->z || capture->x != request->x ||
            capture->record_index != request->record_index ||
            capture->face_index != request->face_index ||
            capture->visible > 1u ||
            quad->material <= 0 || quad->shade >= 26u ||
            capture->nclip_mac0 != quad->projection.nclip_mac0 ||
            capture->visible != quad->projection.visible)
            return 0;
        if (capture->visible) {
            if (!quad->drawable || !quad->projection.ot_in_bounds ||
                capture->raw_otz < 0 || capture->raw_otz > 65535 ||
                capture->raw_otz != (int32_t)quad->projection.otz)
                return 0;
            for (k = 0u; k < 4u; ++k)
                if (capture->gpu_xy[k][0] != quad->projection.gpu[k].x ||
                    capture->gpu_xy[k][1] != quad->projection.gpu[k].y)
                    return 0;
        } else {
            if (quad->drawable || capture->raw_otz != -1)
                return 0;
            for (k = 0u; k < 4u; ++k)
                if (capture->gpu_xy[k][0] != 0 ||
                    capture->gpu_xy[k][1] != 0)
                    return 0;
        }
    }
    for (i = 0u; i < count; ++i)
        out[i] = staged[i];
    return 1;
}

#endif
