#ifndef VH_MAP02_FACE_DIRECTION_H
#define VH_MAP02_FACE_DIRECTION_H

/*
 * PS1 terrain face -> one of 26 lighting directions, for the Switch
 * MAP02 renderer's *reference* shading path.
 *
 * The 26 signed vectors and cross-product vertex selection come from
 * pinned US src/core/graphics.c SetupLightNormals/UpdateMapTileLighting.
 * The original performs gte_OuterProduct0, VectorNormalS and compares
 * normalized Q12 vectors with a six-part tie breaker. PC-port
 * VectorNormalS computes sqrt magnitude and truncates toward zero
 * after multiplying by 4096. This implementation obtains the same
 * mathematical integer quotient without floating-point rounding via
 * 128-bit integer comparisons: axes=4096, 2-axes=2896, 3-axes=2364.
 * The source's sign/normalized-component equality tie break is exact
 * for the represented cross product. However, the original GTE's OP0
 * uses 16-bit IR inputs and hardware arithmetic, which can differ
 * from this full-width cross product on out-of-range geometry. Neither
 * PC floating-point libm nor actual PS1 GPU/GTE execution is used:
 * this is a bounded, deterministic PC-port math reference, NOT a
 * certified cycle/bit-exact hardware GTE emulator.
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

/* The integer-normalized Q12 component is the largest q in 0..4096
 * for which q*q*(x*x+y*y+z*z) <= 4096*4096*c*c. This exactly computes
 * trunc(4096*abs(c)/sqrt(magnitude squared)) without floating-point
 * sqrt or hidden FPU rounding. 128-bit intermediate prevents overflow
 * for all 16-bit input vertices and their 64-bit cross products. */
static inline int32_t vh_map02_q12_component(
    int64_t component, unsigned __int128 magnitude_sq) {
    unsigned __int128 absolute;
    unsigned __int128 target;
    unsigned low = 0, high = 4097;
    if (!component || !magnitude_sq) return 0;
    absolute = (unsigned __int128)(
        component < 0 ? -(component + 1) + 1 : component);
    target = absolute * absolute * 4096u * 4096u;
    while (high - low > 1) {
        unsigned mid = low + (high - low) / 2;
        if ((unsigned __int128)mid * mid * magnitude_sq <= target)
            low = mid;
        else
            high = mid;
    }
    return component < 0 ? -(int32_t)low : (int32_t)low;
}

static inline int vh_map02_normal_q12(
    VhMap02Cross normal, int32_t result[3]) {
    unsigned __int128 a, b, c, squared;
    if (!result || (normal.x == 0 && normal.y == 0 && normal.z == 0))
        return 0;
    /* Construct unsigned squares without negating INT64_MIN directly. */
    a = (unsigned __int128)(normal.x < 0 ?
        (uint64_t)(-(normal.x + 1)) + 1u : (uint64_t)normal.x);
    b = (unsigned __int128)(normal.y < 0 ?
        (uint64_t)(-(normal.y + 1)) + 1u : (uint64_t)normal.y);
    c = (unsigned __int128)(normal.z < 0 ?
        (uint64_t)(-(normal.z + 1)) + 1u : (uint64_t)normal.z);
    squared = a * a + b * b + c * c;
    result[0] = vh_map02_q12_component(normal.x, squared);
    result[1] = vh_map02_q12_component(normal.y, squared);
    result[2] = vh_map02_q12_component(normal.z, squared);
    return 1;
}

/* Exact original six checks, on the NORMALIZED Q12 components:
 * three matching nonzero signs followed by three component equalities. */
static inline int vh_map02_q12_tie_count(
    const int32_t normal[3], const int32_t candidate[3]) {
    int count = 0;
    unsigned axis;
    for (axis = 0; axis < 3; ++axis) {
        if ((normal[axis] > 0 && candidate[axis] > 0) ||
            (normal[axis] < 0 && candidate[axis] < 0))
            ++count;
        if (normal[axis] == candidate[axis])
            ++count;
    }
    return count;
}

/* Reconstruct PC-port VectorNormalS direction table mathematically.
 * 4096/sqrt(2) truncates to 2896; 4096/sqrt(3) to 2364, NOT 2365. */
static inline void vh_map02_direction_q12(
    VhMap02Direction direction, int32_t result[3]) {
    unsigned axes = (unsigned)(direction.x != 0) +
                    (unsigned)(direction.y != 0) +
                    (unsigned)(direction.z != 0);
    int32_t scale = axes == 1u ? 4096 : axes == 2u ? 2896 : 2364;
    result[0] = direction.x * scale;
    result[1] = direction.y * scale;
    result[2] = direction.z * scale;
}

static inline int vh_map02_best_q12_direction(
    VhMap02Cross normal, uint8_t *out_index) {
    int32_t q[3], candidate[3], incumbent[3];
    int64_t greatest = -0x1000000;
    unsigned best = 0, i;
    if (!out_index || !vh_map02_normal_q12(normal, q)) return 0;
    for (i = 0; i < VH_MAP02_LIGHT_DIRECTION_COUNT; ++i) {
        int64_t score;
        vh_map02_direction_q12(vh_map02_directions[i], candidate);
        score = (int64_t)q[0] * candidate[0] +
                (int64_t)q[1] * candidate[1] +
                (int64_t)q[2] * candidate[2];
        if (score > greatest) {
            best = i;
            greatest = score;
        } else if (score == greatest) {
            vh_map02_direction_q12(vh_map02_directions[best], incumbent);
            if (vh_map02_q12_tie_count(q, candidate) >
                vh_map02_q12_tie_count(q, incumbent))
                best = i;
        }
    }
    *out_index = (uint8_t)best;
    return 1;
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

    if (!vh_map02_best_q12_direction(normal, shade_idx)) return 0;
    if (out_normal) *out_normal = normal;
    return 1;
}

#endif
