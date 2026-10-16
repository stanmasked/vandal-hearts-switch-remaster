#include "vh_spu_reverb.h"

#include <limits.h>
#include <math.h>
#include <stddef.h>
#include <string.h>

/* STUDIO_C register values match the software PC-port reference.
 * The original 16-bit register encodings are represented as signed
 * decimal to avoid out-of-range signed conversion at compile time.
 */
enum { DAPF1, DAPF2, VIIR, VCOMB1, VCOMB2, VCOMB3, VCOMB4, VWALL,
       VAPF1, VAPF2, MLSAME, MRSAME, MLCOMB1, MRCOMB1, MLCOMB2,
       MRCOMB2, DLSAME, DRSAME, MLDIFF, MRDIFF, MLCOMB3, MRCOMB3,
       MLCOMB4, MRCOMB4, DLDIFF, DRDIFF, MLAPF1, MRAPF1, MLAPF2,
       MRAPF2, VLIN, VRIN, REG_COUNT };

static const int16_t studio_c[REG_COUNT] = {
    227, 169, 28512, 20392, -17184, 17680, -16656, -22912, 
    22144, 21184, 3579, 2904, 3337, 2620, 3033, 2419, 
    2905, 2266, 2265, 1513, 2028, 1200, 1775, 978, 
    1514, 797, 796, 568, 340, 170, -32768, -32768

};
static const int16_t fir[VH_REV_FIR_TAPS] = {
    -1, 0, 2, 0, -10, 0, 35, 0, -103, 0, 266, 0, -616,
    0, 1332, 0, -2960, 0, 10246, 16384, 10246, 0, -2960, 0,
    1332, 0, -616, 0, 266, 0, -103, 0, 35, 0, -10, 0, 2, 0, -1
};
/* Pre-reduce all register offsets modulo the 0x37F0-sample work
 * buffer. Original encoded STUDIO_C register values remain above and
 * are used by the reference build. The accelerated path requires no
 * per-access division. tests/test_native_spu_reverb_reference.py
 * validates every value against the original unsigned register.
 */
#ifndef VH_REV_FIR_REFERENCE
static const uint16_t reg_addr[REG_COUNT] = {
    908, 676, 13808, 9968, 7248, 13440, 9360, 12976,
    2656, 13136, 14316, 11616, 13348, 10480, 12132, 9676,
    11620, 9064, 9060, 6052, 8112, 4800, 7100, 3912,
    6056, 3188, 3184, 2272, 1360, 680, 2192, 2192
};
_Static_assert(sizeof(reg_addr)/sizeof(reg_addr[0]) == REG_COUNT,
               "One reduced offset per STUDIO_C register");
#endif

_Static_assert(sizeof(studio_c)/sizeof(studio_c[0]) == 32,
               "STUDIO_C has 32 registers");
_Static_assert(sizeof(fir)/sizeof(fir[0]) == VH_REV_FIR_TAPS,
               "PS1 reverb FIR has 39 taps");

static int clip16(int64_t x) {
    if (x < INT16_MIN) return INT16_MIN;
    if (x > INT16_MAX) return INT16_MAX;
    return (int)x;
}
/* Both paths use the same circular SPU addresses and preserve the
 * order of feedback reads/writes. The reference path is enabled
 * exclusively in host benchmarking; Switch builds use the fast path.
 */
#ifdef VH_REV_FIR_REFERENCE
static int rev_off(int reg) {
    return (int)(uint16_t)studio_c[reg] * 4;
}
static int wrap(int pos) {
    pos %= (int)VH_REV_SAMPLES;
    return pos < 0 ? pos + (int)VH_REV_SAMPLES : pos;
}
static int reg_delta(int reg, int other) {
    return rev_off(reg) - rev_off(other);
}
static int read_reg(const VhSpuReverb *s, int reg, int delta) {
    return s->work[wrap(s->cursor + rev_off(reg) + delta)];
}
static int read_at(const VhSpuReverb *s, int delta) {
    return s->work[wrap(s->cursor + delta)];
}
static void write_reg(VhSpuReverb *s, int reg, int value) {
    s->work[wrap(s->cursor + rev_off(reg))] = (int16_t)clip16(value);
}
#else
/* All callers supply offsets within [-WORK, +WORK] and cursor is
 * always [0,WORK-1]. One conditional adjustment replaces modulus.
 */
static int wrap(int pos) {
    if (pos < 0) pos += (int)VH_REV_SAMPLES;
    if (pos >= (int)VH_REV_SAMPLES) pos -= (int)VH_REV_SAMPLES;
    return pos;
}
static int reg_delta(int reg, int other) {
    return (int)reg_addr[reg] - (int)reg_addr[other];
}
static int read_reg(const VhSpuReverb *s, int reg, int delta) {
    return s->work[wrap(s->cursor + (int)reg_addr[reg] + delta)];
}
static int read_at(const VhSpuReverb *s, int delta) {
    return s->work[wrap(s->cursor + delta)];
}
static void write_reg(VhSpuReverb *s, int reg, int value) {
    s->work[wrap(s->cursor + (int)reg_addr[reg])] = (int16_t)clip16(value);
}
#endif
static int mul(int value, int16_t coeff) {
    return (int)(((int64_t)value * coeff) / INT64_C(32768));
}
static int filter(const int16_t *hist, int pos) {
    int64_t acc = 0;
#ifdef VH_REV_FIR_REFERENCE
    /* Baseline retained only for the separate host performance
     * comparison. The shipped Switch build uses the branch below.
     */
    for (int i = 0; i < (int)VH_REV_FIR_TAPS; ++i)
        acc += (int64_t)fir[i] * hist[(pos+i) % (int)VH_REV_FIR_TAPS];
#else
    /* The STUDIO_C FIR has coefficients only at even positions
     * 0,2,...,38 and at the odd center 19. Compute the 21 nonzero
     * products rather than 39, and use one wrap subtraction rather
     * than 21 remainder operations. Since the sum is accumulated in
     * int64_t, rearranging these additions cannot change PCM bits.
     *
     * 'pos' is always a validated ring cursor in [0,38].
     */
    int slot = pos;
    for (int i = 0; i < (int)VH_REV_FIR_TAPS; i += 2) {
        acc += (int64_t)fir[i] * hist[slot];
        slot += 2;
        if (slot >= (int)VH_REV_FIR_TAPS) slot -= (int)VH_REV_FIR_TAPS;
    }
    int center = pos + 19;
    if (center >= (int)VH_REV_FIR_TAPS) center -= (int)VH_REV_FIR_TAPS;
    acc += (int64_t)fir[19] * hist[center];
#endif
    return clip16(acc / INT64_C(32768));
}
static int reflect(VhSpuReverb *s, int input, int fb_reg, int wr_reg) {
    const int prev = read_reg(s, wr_reg, -1);
    const int fb = mul(read_reg(s, fb_reg, 0), studio_c[VWALL]);
    return mul(input + fb - prev, studio_c[VIIR]) + prev;
}
static int comb(VhSpuReverb *s, int base) {
    int v = mul(read_reg(s, base, 0), studio_c[VCOMB1]);
    v += mul(read_reg(s, base+2, 0), studio_c[VCOMB2]);
    v += mul(read_reg(s, base+8, 0), studio_c[VCOMB3]);
    v += mul(read_reg(s, base+10, 0), studio_c[VCOMB4]);
    return v;
}
static int allpass(VhSpuReverb *s, int input, int apf, int delay, int vol) {
    const int delta = reg_delta(apf, delay);
    int previous = read_at(s, delta);
    const int stored = input - mul(previous, studio_c[vol]);
    write_reg(s, apf, stored);
    previous = read_at(s, delta);
    return previous + mul(stored, studio_c[vol]);
}

void vh_spu_reverb_reset(VhSpuReverb *state) {
    if (state) memset(state, 0, sizeof(*state));
}

void vh_spu_reverb_process(VhSpuReverb *s, int send_left,
                           int send_right, float depth,
                           int *wet_left, int *wet_right) {
    if (!wet_left || !wet_right) return;
    *wet_left = *wet_right = 0;
    if (!s || !isfinite(depth) || depth < 0.0f || depth > 1.0f)
        return;

    s->in_l[s->in_cursor] = (int16_t)clip16(send_left);
    s->in_r[s->in_cursor] = (int16_t)clip16(send_right);
    s->in_cursor = (s->in_cursor+1) % (int)VH_REV_FIR_TAPS;
    s->phase ^= 1;
    if (s->phase == 0) {
        const int lin = mul(filter(s->in_l,s->in_cursor),studio_c[VLIN]);
        const int rin = mul(filter(s->in_r,s->in_cursor),studio_c[VRIN]);
        const int same_l = reflect(s,lin,DLSAME,MLSAME);
        const int same_r = reflect(s,rin,DRSAME,MRSAME);
        const int diff_l = reflect(s,lin,DRDIFF,MLDIFF);
        const int diff_r = reflect(s,rin,DLDIFF,MRDIFF);
        write_reg(s,MLSAME,same_l);
        write_reg(s,MRSAME,same_r);
        write_reg(s,MLDIFF,diff_l);
        write_reg(s,MRDIFF,diff_r);
        int l = comb(s,MLCOMB1), r = comb(s,MRCOMB1);
        l = allpass(s,l,MLAPF1,DAPF1,VAPF1);
        r = allpass(s,r,MRAPF1,DAPF1,VAPF1);
        l = allpass(s,l,MLAPF2,DAPF2,VAPF2);
        r = allpass(s,r,MRAPF2,DAPF2,VAPF2);
        s->out_l[s->out_cursor] = (int16_t)clip16(l);
        s->out_r[s->out_cursor] = (int16_t)clip16(r);
        s->out_cursor = (s->out_cursor+1) % (int)VH_REV_FIR_TAPS;
        s->cursor = wrap(s->cursor+1);
    } else {
        s->out_l[s->out_cursor] = 0;
        s->out_r[s->out_cursor] = 0;
        s->out_cursor = (s->out_cursor+1) % (int)VH_REV_FIR_TAPS;
    }
    const int l = clip16((int64_t)filter(s->out_l,s->out_cursor)*2);
    const int r = clip16((int64_t)filter(s->out_r,s->out_cursor)*2);
    *wet_left = (int)(l * depth);
    *wet_right = (int)(r * depth);
}
