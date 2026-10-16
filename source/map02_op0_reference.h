#ifndef VH_MAP02_OP0_REFERENCE_H
#define VH_MAP02_OP0_REFERENCE_H

/*
 * Deterministic register-boundary models for MAP02's gte_OuterProduct0.
 *
 * PC-port behavior (pinned platform/pc/src/libgte.c):
 * - LoadOPV1 stores the first edge as full 32-bit integers (D1,D2,D3).
 * - LoadOPV2 loads the low signed 16 bits of the second edge into IR1..3.
 * - OP0 writes MAC1..3. StoreLVNL returns MAC, NOT the saturated IR.
 * - A 32-bit two's-complement wrap models GCC -fwrapv when the source's
 *   signed int intermediate overflows; native comparison explicitly uses
 *   this compiler option.
 *
 * PS1 input/register model:
 * - The pinned MIPS gte_ldopv1 macro writes first-edge words to control
 *   registers 0/2/4, whose OP0 diagonal coefficients are signed 16-bit.
 * - gte_ldopv2 loads signed IR1..3; gte_stlvnl reads MAC1..3 as 32-bit.
 * - We model the low 32 MAC bits using wide arithmetic with explicit wrap.
 *
 * This does NOT implement GTE's 44-bit internal accumulator flags, timing,
 * hardware saturation flags, or PS1 BIOS VectorNormalS. Do not label
 * either mode as hardware-verified or silently replace the PC reference.
 *
 * Inputs are signed 32-bit vertex differences (each axis of an SVECTOR
 * subtraction lies in [-65535, 65535]); no game assets are involved.
 */
#include <stdint.h>
#include <stddef.h>

typedef struct {
    int32_t x;
    int32_t y;
    int32_t z;
} VhMap02Op0Mac;

static inline int32_t vh_map02_op0_signed16(int32_t n) {
    uint32_t lo = (uint32_t)n & UINT32_C(0xffff);
    return lo < UINT32_C(0x8000) ? (int32_t)lo :
           (int32_t)lo - INT32_C(65536);
}

static inline int32_t vh_map02_op0_wrap32(int64_t n) {
    uint32_t bits = (uint32_t)((uint64_t)n & UINT64_C(0xffffffff));
    return bits <= (uint32_t)INT32_MAX ? (int32_t)bits :
           (int32_t)((int64_t)bits - INT64_C(4294967296));
}

static inline int vh_map02_op0_model(
    const int32_t first[3], const int32_t second[3],
    int first_is_signed16, VhMap02Op0Mac *out) {
    int64_t d[3], ir[3];
    VhMap02Op0Mac result;
    unsigned i;
    if (!first || !second || !out) return 0;
    for (i = 0; i < 3; ++i) {
        d[i] = first_is_signed16 ?
               vh_map02_op0_signed16(first[i]) : first[i];
        ir[i] = vh_map02_op0_signed16(second[i]);
    }
    result.x = vh_map02_op0_wrap32(d[1] * ir[2] - d[2] * ir[1]);
    result.y = vh_map02_op0_wrap32(d[2] * ir[0] - d[0] * ir[2]);
    result.z = vh_map02_op0_wrap32(d[0] * ir[1] - d[1] * ir[0]);
    *out = result;
    return 1;
}

static inline int vh_map02_op0_pc(
    const int32_t first[3], const int32_t second[3],
    VhMap02Op0Mac *out) {
    return vh_map02_op0_model(first, second, 0, out);
}

static inline int vh_map02_op0_ps1_registers(
    const int32_t first[3], const int32_t second[3],
    VhMap02Op0Mac *out) {
    return vh_map02_op0_model(first, second, 1, out);
}

#endif
