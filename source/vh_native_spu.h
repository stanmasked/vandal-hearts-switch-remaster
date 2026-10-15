#ifndef VH_NATIVE_SPU_H
#define VH_NATIVE_SPU_H

#include <stddef.h>
#include <stdint.h>
#include "vh_audio_stream.h"

/* Diagnostic PC-port-style mixer: 20 music voice slots, 512-frame blocks.
 * Caller owns decoded PCM and keeps it alive until note terminates.
 * Not a game SEQ parser or hardware-accurate Gaussian/reverb renderer.
 */
#define VH_NATIVE_MUSIC_VOICES 20u

typedef enum {
    VH_ADSR_OFF = 0,
    VH_ADSR_ATTACK,
    VH_ADSR_DECAY,
    VH_ADSR_SUSTAIN,
    VH_ADSR_RELEASE
} VhAdsrPhase;

typedef struct {
    uint16_t adsr1;
    uint16_t adsr2;
    int level;
    int counter;
    VhAdsrPhase phase;
} VhAdsrState;

typedef struct {
    const int16_t *pcm;
    size_t frames;
    int64_t loop_start;
    int64_t loop_end;
    uint64_t phase;
    uint32_t pitch_step;
    float gain_left;
    float gain_right;
    VhAdsrState adsr;
    int active;
} VhNativeVoice;

typedef struct {
    VhNativeVoice voice[VH_NATIVE_MUSIC_VOICES];
    unsigned int steal_index;
    uint64_t frames_rendered;
} VhNativeSpu;

void vh_native_spu_reset(VhNativeSpu *spu);
/* First free music slot, or round-robin steal among 20 occupied slots. */
int vh_native_spu_allocate_slot(VhNativeSpu *spu);
/* Returns 0 for success, -1 for invalid params; replaces existing slot. */
int vh_native_spu_note_on(
    VhNativeSpu *spu, unsigned slot, const int16_t *pcm, size_t frames,
    int64_t loop_start, int64_t loop_end, uint32_t pitch_step,
    uint16_t adsr1, uint16_t adsr2, float gain_left, float gain_right);
void vh_native_spu_note_off(VhNativeSpu *spu, unsigned slot);
int vh_native_spu_voice_active(const VhNativeSpu *spu, unsigned slot);

/* Dry stereo output, nearest-sample fetch and PC-port ADSR. No allocations.
 * One output-sample render call is reflected in frames_rendered.
 */
void vh_native_spu_render(VhNativeSpu *spu, int16_t *out_stereo, size_t frames);

/* Produce exactly 1..512 output frames iff ring has capacity. Otherwise
 * returns zero WITHOUT advancing the synth. Caller must synchronize ring
 * with callback access (SDL_LockAudioDevice on Switch).
 */
size_t vh_native_spu_pump(VhNativeSpu *spu, VhAudioStream *stream, size_t frames);

#endif
