#ifndef VH_NATIVE_VAB_H
#define VH_NATIVE_VAB_H

#include <stddef.h>
#include <stdint.h>
#include "vh_native_seq.h"

/* Bounded VH/VB bank importer for a caller-owned, predecoded PCM arena.
 * No filesystem access, heap allocation or reading in the audio callback.
 * Keep the PCM arena allocated while any native SPU voice refers to it.
 */
#define VH_VAB_PROGRAMS 128u
#define VH_VAB_TONES_PER_PROGRAM 16u
#define VH_VAB_SAMPLES 256u

typedef struct {
    uint8_t present, low, high;
    int8_t center, fine;
    uint8_t volume, pan, mode;
    uint16_t adsr1, adsr2, vag; /* 1-based VAG index */
} VhVabTone;

typedef struct {
    const int16_t *pcm; /* borrowed from the provided PCM arena */
    size_t frames;
    int64_t loop_start, loop_end;
    size_t vb_offset, adpcm_bytes;
} VhVabSample;

typedef struct {
    uint8_t master_volume, program_volume[VH_VAB_PROGRAMS];
    uint8_t program_pan[VH_VAB_PROGRAMS];
    uint8_t program_tones[VH_VAB_PROGRAMS];
    uint8_t active;
    uint16_t vag_count;
    size_t required_pcm_frames;
    VhVabTone tones[VH_VAB_PROGRAMS][VH_VAB_TONES_PER_PROGRAM];
    VhVabSample samples[VH_VAB_SAMPLES];
    unsigned seq_left, seq_right; /* 0..127; default 127 */
    unsigned selected_program, selected_tone, selected_vag; /* diagnostics */
} VhNativeVab;

/* Prevalidate complete VH, VB bounds and all referenced ADPCM headers,
 * decode each referenced VAG once into caller-owned arena, and publish
 * *bank only on success. On error, the arena can contain partial output,
 * but the bank struct and original VH/VB bytes remain untouched.
 *
 * pcm_capacity is in 16-bit MONO samples, not bytes. Required storage
 * cannot be deduced from VH alone without validating packed tone tables.
 */
int vh_native_vab_load(VhNativeVab *bank, const uint8_t *vh, size_t vh_size,
                       const uint8_t *vb, size_t vb_size,
                       int16_t *pcm_arena, size_t pcm_capacity);

/* The native pQES engine's VhSeqResolve callback. Applies the same
 * sparse-tone fallback, approximate pitch and squared PsyQ pan law
 * as the reference PC port. Missing playable sample returns -1.
 * Passing bank->seq_left/right separately allows per-sequence levels.
 */
int vh_native_vab_resolve(void *context, unsigned program, unsigned note,
                          unsigned velocity, unsigned channel_volume,
                          unsigned channel_pan, VhSeqTone *out);

#endif
