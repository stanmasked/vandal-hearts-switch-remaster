#ifndef VH_MAP02_PROJECTION_H
#define VH_MAP02_PROJECTION_H
/*
 * Read-only MAP02 terrain RTPT -> NCLIP -> RTPS -> AVSZ4 reference.
 * Reconstructs the pinned public PC-port GTE register math, not actual
 * PlayStation hardware, and does NOT connect to runtime or draw pixels.
 * Input camera state must be supplied by caller; no guessed MAP02 camera.
 *
 * Source: pinned platform/pc/src/libgte.c TransformOne, UnrDivide,
 * PC_GTE_{RTPT,RTPS,NCLIP,AVSZ4}; src/core/graphics.c RenderMapTile.
 * Exports all four GPU FT4 projected corner positions with original
 * x0=face[0], x1=face[1], x3=face[2], x2=face[3] wiring.
 * No game assets, output textures, GTE 44-bit MAC flags, or draw calls.
 */
#include <limits.h>
#include <stddef.h>
#include <stdint.h>

typedef struct { int16_t x, y, z; } VhMap02ProjectVertex;
typedef struct { int16_t x, y; } VhMap02ProjectSxy;
typedef struct {
    int16_t rt[3][3];    /* RT1..3, Q12 */
    int32_t tr[3];       /* TRX/Y/Z: GTE translation */
    int32_t ofx, ofy;    /* OFX/OFY: signed 16.16 */
    int16_t h;           /* H (GTE perspective focal length) */
    int16_t zsf4;        /* ZSF4, used by AVSZ4 */
} VhMap02ProjectCamera;
typedef struct {
    VhMap02ProjectSxy gpu[4]; /* POLY_FT4 [0,1,2,3] */
    uint16_t sz[4];           /* original face[0..3] SZ */
    int32_t nclip_mac0;
    uint16_t otz;             /* raw AVSZ4 depth, 0 if culled */
    uint16_t depth;           /* max(5,otz) as renderer uses */
    uint32_t rtpt_flags, rtps_flags;
    uint8_t visible;          /* NCLIP > 0, before OT bounds */
    uint8_t ot_in_bounds;     /* OT_SIZE - depth addresses actual entry */
    size_t ot_slot;           /* valid only when ot_in_bounds */
} VhMap02ProjectFace;

static inline int64_t vh_map02_proj_asr(int64_t v, unsigned shift) {
    if (v >= 0) return v >> shift;
    return -(int64_t)(((uint64_t)(-(v + 1)) + 1u +
                        (((uint64_t)1u << shift) - 1u)) >> shift);
}
static inline int32_t vh_map02_proj_wrap32(int64_t val) {
    uint32_t low = (uint32_t)((uint64_t)val & UINT64_C(0xffffffff));
    return low <= (uint32_t)INT32_MAX ? (int32_t)low :
        (int32_t)((int64_t)low - INT64_C(4294967296));
}
static inline int32_t vh_map02_proj_clamp(int32_t v, int32_t lo, int32_t hi) {
    return v < lo ? lo : v > hi ? hi : v;
}
static inline uint16_t vh_map02_proj_satu16(int32_t v) {
    return (uint16_t)vh_map02_proj_clamp(v, 0, 65535);
}
static inline int vh_map02_proj_unr(
    uint16_t h, uint16_t sz, uint32_t *flags, uint32_t *out) {
    unsigned z = 0, idx;
    uint32_t n, d, u, entry, val;
    if (!flags || !out) return 0;
    if (sz == 0 || (uint32_t)h >= (uint32_t)sz * 2u) {
        *flags |= (UINT32_C(1) << 17) | (UINT32_C(1) << 31);
        *out = 0x1ffffu;
        return 1;
    }
    d = sz;
    while (!(d & 0x8000u)) { d <<= 1; ++z; }
    n = (uint32_t)h << z;
    d = (uint32_t)sz << z;
    idx = (d - 0x7fc0u) >> 7;
    /* Inline pinned BuildUnrTable entry, eliminating mutable global state. */
    entry = (UINT32_C(0x40000) / (idx + 0x100u) + 1u) / 2u;
    entry = entry < 0x101u ? 0u : entry - 0x101u;
    u = entry + 0x101u;
    val = (UINT32_C(0x2000080) - d * u) >> 8;
    val = (0x80u + val * u) >> 8;
    n = (uint32_t)((((uint64_t)n * val) + 0x8000u) >> 16);
    *out = n > 0x1ffffu ? 0x1ffffu : n;
    return 1;
}

static inline int vh_map02_project_vertex(
    const VhMap02ProjectCamera *camera, VhMap02ProjectVertex point,
    VhMap02ProjectSxy *xy, uint16_t *sz, uint32_t *flags) {
    int32_t mac[3], ir[3];
    uint32_t n;
    int i, k;
    const int16_t pos[3] = {point.x, point.y, point.z};
    if (!camera || !xy || !sz || !flags) return 0;
    for (i = 0; i < 3; ++i) {
        int64_t acc = (int64_t)camera->tr[i] * 4096;
        for (k = 0; k < 3; ++k)
            acc += (int64_t)camera->rt[i][k] * pos[k];
        mac[i] = vh_map02_proj_wrap32(vh_map02_proj_asr(acc, 12));
        ir[i] = vh_map02_proj_clamp(mac[i], -32768, 32767);
    }
    *sz = vh_map02_proj_satu16(mac[2]);
    if (!vh_map02_proj_unr((uint16_t)camera->h, *sz, flags, &n)) return 0;
    {
        int32_t projected_x = vh_map02_proj_wrap32((int64_t)n * ir[0] + camera->ofx);
        int32_t projected_y = vh_map02_proj_wrap32((int64_t)n * ir[1] + camera->ofy);
        int32_t px = (int32_t)vh_map02_proj_asr(projected_x, 16);
        int32_t py = (int32_t)vh_map02_proj_asr(projected_y, 16);
        if (px < -1024 || px > 1023) *flags |= 1u << 14;
        if (py < -1024 || py > 1023) *flags |= 1u << 13;
        xy->x = (int16_t)vh_map02_proj_clamp(px, -1024, 1023);
        xy->y = (int16_t)vh_map02_proj_clamp(py, -1024, 1023);
    }
    return 1;
}

/* Returns zero only for invalid pointers. Correctly culled polygons still
 * return one, with visible=0. Writes 'out' only upon successful completion.
 * Caller supplies ordering table length; no pointer arithmetic is done.
 */
static inline int vh_map02_project_face(
    const VhMap02ProjectCamera *camera,
    const VhMap02ProjectVertex corners[4],
    size_t ot_size, VhMap02ProjectFace *out) {
    VhMap02ProjectFace face = {0};
    VhMap02ProjectSxy p[4];
    int64_t nclip;
    int32_t mac0;
    unsigned i;
    if (!camera || !corners || !out) return 0;
    for (i = 0; i < 3; ++i) {
        if (!vh_map02_project_vertex(camera, corners[i], &p[i],
                                    &face.sz[i], &face.rtpt_flags)) return 0;
    }
    /* StoreOPZ is signed MAC0, not OTZ. Preserve 32-bit wrap semantics. */
    nclip = (int64_t)p[0].x * p[1].y +
            (int64_t)p[1].x * p[2].y +
            (int64_t)p[2].x * p[0].y -
            (int64_t)p[0].x * p[2].y -
            (int64_t)p[1].x * p[0].y -
            (int64_t)p[2].x * p[1].y;
    face.nclip_mac0 = vh_map02_proj_wrap32(nclip);
    face.visible = face.nclip_mac0 > 0;
    if (face.visible) {
        /* RTPS resets FLAG; RTPT's three-point FLAG is reported separately. */
        if (!vh_map02_project_vertex(camera, corners[3], &p[3],
                                    &face.sz[3], &face.rtps_flags)) return 0;
        mac0 = vh_map02_proj_wrap32((int64_t)camera->zsf4 *
               ((int64_t)face.sz[0] + face.sz[1] + face.sz[2] + face.sz[3]));
        face.otz = vh_map02_proj_satu16(
            (int32_t)vh_map02_proj_asr(mac0, 12));
        face.depth = face.otz < 5u ? 5u : face.otz;
        if ((size_t)face.depth <= ot_size && ot_size > 0u) {
            face.ot_in_bounds = 1u;
            face.ot_slot = ot_size - (size_t)face.depth;
        }
        face.gpu[0] = p[0];
        face.gpu[1] = p[1];
        face.gpu[2] = p[3];
        face.gpu[3] = p[2];
    }
    *out = face;
    return 1;
}
#endif
