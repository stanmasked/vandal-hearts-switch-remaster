#ifndef VH_MAP02_EXTERNAL_GTE_FT4_H
#define VH_MAP02_EXTERNAL_GTE_FT4_H

/*
 * Strict source-keyed MAP02 GTE-evidence -> FT4 compositor adapter.
 *
 * This adapter does NOT execute RTPT, RTPS, NCLIP, AVSZ4 or guess camera
 * parameters. Its caller supplies screen coordinates and raw OTZ allegedly
 * captured at an original submitted RenderMapTile POLY_FT4. It checks the
 * observation against the owned decoded 616-record MAP02 source buffer,
 * including all four vertex indices and 12 position components, a unique
 * face key, signed local GFX and shade. It deliberately does NOT certify
 * that the external measurement came from a real PS1 or PC gameplay frame.
 *
 * The output is a VhMap02TerrainQuad suitable for
 * vh_map02_ot_scene_add(); its projection.visible is an *externally
 * asserted submitted-face gate*, NOT a computed NCLIP result. Unobserved
 * SZ/MAC0/RTPT flags remain zero. External evidence and synthetic GTE
 * calculations must not be mixed into an asserted source trace.
 */
#include <stddef.h>
#include <stdint.h>
#include "map02_terrain_ot_scene.h"

#define VH_MAP02_EXTERNAL_STRIDE 28u
#define VH_MAP02_EXTERNAL_ACTIVE_X 24u
#define VH_MAP02_EXTERNAL_ACTIVE_Z 12u
#define VH_MAP02_EXTERNAL_RECORDS (VH_MAP02_EXTERNAL_STRIDE * 22u)
#define VH_MAP02_EXTERNAL_DECODED_BYTES (VH_MAP02_EXTERNAL_RECORDS * 304u)

/* Do not collapse the source key to GFX alone: multiple faces/cells may
 * legitimately share the same material number, UVs or depth. */
typedef struct {
    int32_t z, x, record_index, face_index;
    int32_t local_gfx, face_shade;
    int32_t vertex_indices[4];  /* original face perimeter indices */
    int32_t vertex_xyz[4][3];   /* original local SVECTOR values */
    int32_t perimeter_xy[4][2]; /* face[0..3], NOT GPU [0,1,2,3] */
    int32_t raw_otz;            /* observed AVSZ4 result, 0..65535 */
    int32_t u, v, w, h;         /* externally authenticated UVWH */
} VhMap02ExternalFaceEvidence;

typedef struct {
    int32_t z, x, record_index, face_index;
    uint8_t supplied_gte_observation;
    VhMap02TerrainQuad quad;
} VhMap02ExternalPreparedFace;

/*
 * Returns 1 for an accepted externally observed submission; returns 0
 * and does NOT change *out for any mismatch or malformed source/evidence.
 * Mandatory full decoded MAP02 buffer prevents silently confusing a
 * standalone 304-byte tile with source-keyed face provenance.
 *
 * The caller must independently establish origin, timing, UV/CLUT and
 * source-binary provenance; comparing bytes to observations alone is
 * NOT cryptographic proof of a live gameplay trace.
 */
static inline int vh_map02_prepare_external_face(
    const uint8_t *decoded, size_t decoded_size,
    const VhMap02ExternalFaceEvidence *ev,
    size_t ot_size, VhMap02ExternalPreparedFace *out) {
    const uint8_t *tile;
    VhMap02ExternalPreparedFace prepared = {0};
    VhFt4Point perimeter[4];
    unsigned i, j;
    size_t record;
    int32_t depth;
    if (!decoded || !ev || !out ||
        decoded_size != VH_MAP02_EXTERNAL_DECODED_BYTES ||
        ev->z < 0 || ev->z >= (int32_t)VH_MAP02_EXTERNAL_ACTIVE_Z ||
        ev->x < 0 || ev->x >= (int32_t)VH_MAP02_EXTERNAL_ACTIVE_X ||
        ev->face_index < 0 || ev->face_index >= (int32_t)VH_MAP02_FACE_MAX_COUNT ||
        ev->u < 0 || ev->v < 0 || ev->u > 255 || ev->v > 255 ||
        ev->w < 1 || ev->h < 1 ||
        ev->w > 255 - ev->u || ev->h > 255 - ev->v ||
        ev->raw_otz < 0 || ev->raw_otz > 65535 ||
        ot_size < 5u || ev->face_shade < 0 || ev->face_shade >= 26)
        return 0;
    record = (size_t)ev->z * VH_MAP02_EXTERNAL_STRIDE + (size_t)ev->x;
    if (ev->record_index != (int32_t)record) return 0;
    tile = decoded + record * VH_MAP02_FACE_RECORD_BYTES;
    if (tile[302] > VH_MAP02_FACE_MAX_COUNT ||
        ev->face_index >= tile[302] ||
        vh_map02_quad_s16(tile, 176u + 2u * (size_t)ev->face_index) != ev->local_gfx ||
        ev->local_gfx <= 0 ||
        tile[284u + (size_t)ev->face_index] != ev->face_shade)
        return 0;

    for (i=0; i<4u; ++i) {
        unsigned vertex = tile[212u + (size_t)ev->face_index * 4u + i];
        if (vertex >= VH_MAP02_FACE_MODEL_VERTICES ||
            ev->vertex_indices[i] != (int32_t)vertex)
            return 0;
        for (j=0; j<3u; ++j)
            if (ev->vertex_xyz[i][j] !=
                (int32_t)vh_map02_quad_s16(tile,(size_t)vertex*8u+(size_t)j*2u))
                return 0;
        if (ev->perimeter_xy[i][0] < -1024 ||
            ev->perimeter_xy[i][0] > 1023 ||
            ev->perimeter_xy[i][1] < -1024 ||
            ev->perimeter_xy[i][1] > 1023)
            return 0;
        perimeter[i].x = (float)ev->perimeter_xy[i][0];
        perimeter[i].y = (float)ev->perimeter_xy[i][1];
    }
    depth = ev->raw_otz < 5 ? 5 : ev->raw_otz;
    if ((size_t)depth > ot_size) return 0;
    prepared.z=ev->z;
    prepared.x=ev->x;
    prepared.record_index=ev->record_index;
    prepared.face_index=ev->face_index;
    prepared.supplied_gte_observation=1u;
    prepared.quad.face=(uint8_t)ev->face_index;
    prepared.quad.material=(int16_t)ev->local_gfx;
    prepared.quad.shade=(uint8_t)ev->face_shade;
    prepared.quad.u=ev->u; prepared.quad.v=ev->v;
    prepared.quad.w=ev->w; prepared.quad.h=ev->h;
    /* Only the supplied accepted-submission fact is represented.
     * No GTE calculation, NCLIP sign, SZ or flags have been inferred. */
    prepared.quad.projection.visible=1u;
    prepared.quad.projection.ot_in_bounds=1u;
    prepared.quad.projection.otz=(uint16_t)ev->raw_otz;
    prepared.quad.projection.depth=(uint16_t)depth;
    prepared.quad.projection.ot_slot=ot_size-(size_t)depth;
    if (!vh_ft4_from_face_perimeter(
            perimeter,ev->u,ev->v,ev->w,ev->h,prepared.quad.gpu_ft4))
        return 0;
    prepared.quad.drawable=1u;
    *out=prepared;
    return 1;
}
#endif
