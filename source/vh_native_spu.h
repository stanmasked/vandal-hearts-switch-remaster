#ifndef VH_NATIVE_SPU_H
#define VH_NATIVE_SPU_H

#include <stddef.h>
#include <stdint.h>
#include "vh_audio_stream.h"
#include "vh_spu_reverb.h"

/* Diagnostic PC-port-style mixer: 20 music voice slots, 512-frame blocks.
 * Caller owns decoded PCM and keeps it alive until note terminates.
 * Not a game SEQ parser, reverb engine or hardware-cycle emulator.
 */
#define VH_NATIVE_MUSIC_VOICES 20u
#define VH_SPU_NEAREST 0u
#define VH_SPU_GAUSSIAN 1u

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
    int looped; /* true after crossing first repeat-loop boundary */
    int reverb_send; /* VH VagAtr.mode bit2 (per-voice EON) */
    float gain_left;
    float gain_right;
    VhAdsrState adsr;
    int active;
} VhNativeVoice;

typedef struct {
    VhNativeVoice voice[VH_NATIVE_MUSIC_VOICES];
    unsigned int steal_index;
    unsigned interpolation; /* default nearest, optional 4-tap Gaussian */
    int reverb_enabled;
    float reverb_depth;
    VhSpuReverb reverb;
    uint64_t frames_rendered;
} VhNativeSpu;

void vh_native_spu_reset(VhNativeSpu *spu);
/* Scene transition: discard every voice and borrowed PCM pointer while
 * keeping the STUDIO_C wet-tail history and current DSP configuration.
 * Stop/reinitialize the owning SEQ before using this function; all pending
 * output pages must also be handled by the caller. Resets per-scene counters.
 */
void vh_native_spu_clear_voices_keep_reverb(VhNativeSpu *spu);
/* Set VH_SPU_NEAREST (0) or VH_SPU_GAUSSIAN (1); -1 on invalid. */
int vh_native_spu_set_interpolation(VhNativeSpu *spu, unsigned mode);
/* Studio C wet level in [0,1]; disabled by default, preserving dry PCM. */
int vh_native_spu_set_reverb(VhNativeSpu *spu, int enabled, float depth);
/* Per-tone send (VagAtr.mode bit2): unrelated to global wet enable. */
int vh_native_spu_set_voice_reverb(VhNativeSpu *spu, unsigned slot, int enabled);
/* First free music slot, or round-robin steal among 20 occupied slots. */
int vh_native_spu_allocate_slot(VhNativeSpu *spu);
/* Returns 0 for success, -1 for invalid params; replaces existing slot. */
int vh_native_spu_note_on(
    VhNativeSpu *spu, unsigned slot, const int16_t *pcm, size_t frames,
    int64_t loop_start, int64_t loop_end, uint32_t pitch_step,
    uint16_t adsr1, uint16_t adsr2, float gain_left, float gain_right);
void vh_native_spu_note_off(VhNativeSpu *spu, unsigned slot);
int vh_native_spu_voice_active(const VhNativeSpu *spu, unsigned slot);

/* Stereo output, selectable Gaussian and STUDIO_C, PC-port ADSR.
 * One output-sample render call is reflected in frames_rendered.
 */
void vh_native_spu_render(VhNativeSpu *spu, int16_t *out_stereo, size_t frames);

/* Produce exactly 1..512 output frames iff ring has capacity. Otherwise
 * returns zero WITHOUT advancing the synth. Caller must synchronize ring
 * with callback access (SDL_LockAudioDevice on Switch).
 */
size_t vh_native_spu_pump(VhNativeSpu *spu, VhAudioStream *stream, size_t frames);

#endif
