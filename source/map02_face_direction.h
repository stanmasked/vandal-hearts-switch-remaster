#ifndef VH_MAP02_FACE_DIRECTION_H
#define VH_MAP02_FACE_DIRECTION_H

/*
 * PS1 terrain face -> one of 26 lighting directions, for the Switch
 * MAP02 renderer's *reference* shading path.
 *
 * The 26 signed vectors and cross-product vertex selection come from
 * pinned US src/core/graphics.c SetupLightNormals/UpdateMapTileLighting.
 * The original performs gte_OuterProduct0, VectorNormalS and compares
 * normalized Q12 vectors, with a six-part tie breaker. Here the
 * candidate vectors are pre-normalized to Q12 (4096, 2896, 2365)
 * and projected against an unnormalized signed 64-bit cross product.
 * Exact-match ties are resolved by the same six-part rule. The index
 * is deterministic, but GTE integer roundoff near boundaries can
 * differ. Never label it bit-exact PS1 GTE emulation.
 */
#include <stddef.h>
#include <stdint.h>
#include <limits.h>

#define VH_MAP02_VERTEX_COUNT 22u
#define VH_MAP02_FACE_COUNT 18u
#define VH_MAP02_LIGHT_DIRECTION_COUNT 26u
#define VH_MAP02_TILE_BYTES 304u

typedef struct {
    int8_t x;
    int8_t y;
    int8_t z;
} VhMap02Direction;

typedef struct {
    int64_t x;
    int64_t y;
    int64_t z;
} VhMap02Cross;

static const VhMap02Direction vh_map02_directions[26] = {
    { 0, 1, 0}, { 0,-1, 0}, { 1, 0, 0}, { 0, 0, 1}, {-1, 0, 0}, { 0, 0,-1},
    { 1, 0,-1}, { 1, 0, 1}, {-1, 0, 1}, {-1, 0,-1},
    { 1, 1, 0}, { 0, 1, 1}, {-1, 1, 0}, { 0, 1,-1},
    { 1, 1,-1}, { 1, 1, 1}, {-1, 1, 1}, {-1, 1,-1},
    { 1,-1, 0}, { 0,-1, 1}, {-1,-1, 0}, { 0,-1,-1},
    { 1,-1,-1}, { 1,-1, 1}, {-1,-1, 1}, {-1,-1,-1}
};

static inline int32_t vh_map02_sign64(int64_t a) {
    return (a > 0) - (a < 0);
}

static inline int vh_map02_direction_tie_count(
    VhMap02Cross normal, VhMap02Direction candidate) {
    const int32_t x = vh_map02_sign64(normal.x);
    const int32_t y = vh_map02_sign64(normal.y);
    const int32_t z = vh_map02_sign64(normal.z);
    /* Sign agreement for three nonzero components + exact normalized
     * direction component equalities. Cross vector is *not* normalized,
     * so equality here is tested using axis-sign cases only; candidate
     * equality scores are an approximation to the original GTE Q12. */
    int count = (x != 0 && x == candidate.x ? 1 : 0)
              + (y != 0 && y == candidate.y ? 1 : 0)
              + (z != 0 && z == candidate.z ? 1 : 0);
    count += (x == candidate.x);
    count += (y == candidate.y);
    count += (z == candidate.z);
    return count;
}

static inline int64_t vh_map02_candidate_dot(
    VhMap02Cross normal, VhMap02Direction direction) {
    const unsigned axes = (unsigned)(direction.x != 0)
                        + (unsigned)(direction.y != 0)
                        + (unsigned)(direction.z != 0);
    const int64_t q12 = axes == 1u ? 4096 : axes == 2u ? 2896 : 2365;
    return (normal.x * direction.x + normal.y * direction.y +
            normal.z * direction.z) * q12;
}

/* Input: raw 304-byte little-endian MapTileModel, faceIdx < faceCt.
 * Returns nonzero on well-formed, nondegenerate geometry; outputs the
 * best-matching index and optionally the unnormalized model-space normal.
 * Neither the model nor the caller output is touched on invalid input.
 */
static inline int vh_map02_face_direction(
    const uint8_t *tile, size_t tile_bytes, unsigned face_idx,
    uint8_t *shade_idx, VhMap02Cross *out_normal) {
    unsigned vi[4], first, second, third, i;
    int32_t p[3][3], e1[3], e2[3];
    VhMap02Cross normal;
    int64_t best = INT64_MIN;
    int best_tie = -1;
    unsigned best_idx = 0u;

    if (!tile || !shade_idx || tile_bytes < VH_MAP02_TILE_BYTES ||
        tile[302] == 0 || tile[302] > VH_MAP02_FACE_COUNT ||
        face_idx >= tile[302]) return 0;
    for (i = 0; i < 4; ++i) {
        vi[i] = tile[212u + face_idx * 4u + i];
        if (vi[i] >= VH_MAP02_VERTEX_COUNT) return 0;
    }

    /* Source chooses three nonidentical face vertices in an unusual
     * order when specific corners repeat. Preserve those branches. */
    first = vi[0]; second = vi[1]; third = vi[2];
    if (vi[0] == vi[1]) {
        first = vi[2]; second = vi[0]; third = vi[3];
    } else if (vi[0] == vi[2]) {
        first = vi[1]; second = vi[0]; third = vi[3];
    } else if (vi[0] == vi[3]) {
        first = vi[1]; second = vi[0]; third = vi[2];
    } else if (vi[1] == vi[2]) {
        first = vi[1]; second = vi[0]; third = vi[3];
    }

    {
        const unsigned chosen[3] = {first, second, third};
        for (i = 0; i < 3; ++i) {
            unsigned k;
            const size_t at = chosen[i] * 8u;
            for (k = 0; k < 3; ++k) {
                const size_t ofs = at + k * 2u;
                p[i][k] = (int16_t)(
                    (uint16_t)tile[ofs] | ((uint16_t)tile[ofs + 1] << 8));
            }
        }
    }
    for (i = 0; i < 3; ++i) {
        e1[i] = p[1][i] - p[0][i];
        e2[i] = p[2][i] - p[0][i];
    }
    normal.x = (int64_t)e1[1] * e2[2] - (int64_t)e1[2] * e2[1];
    normal.y = (int64_t)e1[2] * e2[0] - (int64_t)e1[0] * e2[2];
    normal.z = (int64_t)e1[0] * e2[1] - (int64_t)e1[1] * e2[0];
    if (normal.x == 0 && normal.y == 0 && normal.z == 0) return 0;

    for (i = 0; i < VH_MAP02_LIGHT_DIRECTION_COUNT; ++i) {
        const int64_t score = vh_map02_candidate_dot(normal, vh_map02_directions[i]);
        const int tie = vh_map02_direction_tie_count(normal, vh_map02_directions[i]);
        if (score > best || (score == best && tie > best_tie)) {
            best = score;
            best_tie = tie;
            best_idx = i;
        }
    }
    *shade_idx = (uint8_t)best_idx;
    if (out_normal) *out_normal = normal;
    return 1;
}

#endif
