#ifndef VH_MUSIC_SCENE_H
#define VH_MUSIC_SCENE_H

#include <stddef.h>
#include <stdint.h>
#include "vh_native_seq.h"

/* Portable gameplay-to-music contract. The game/main thread issues
 * scene requests; the audio producer owns render() and transitions.
 * Calls must be externally serialized; do not use from SDL callbacks.
 * Source SEQ, bank and decoded PCM must remain alive until the old
 * scene has fully faded out and been replaced.
 */
#define VH_MUSIC_SCENE_MAX_FADE_BLOCKS 4096u
typedef struct {
    uint32_t id; /* nonzero stable scene identifier */
    const uint8_t *seq;
    size_t seq_size;
    unsigned repeats; /* 0 infinite, otherwise 1..64 */
    VhSeqResolve resolver;
    void *context;
} VhMusicCue;

typedef enum {
    VH_MUSIC_SILENT = 0,
    VH_MUSIC_PLAYING,
    VH_MUSIC_FADE_OUT,
    VH_MUSIC_FADE_IN,
    VH_MUSIC_SWITCH_PENDING
} VhMusicStage;

typedef struct {
    VhNativeSpu *spu; /* caller-owned */
    VhNativeSeq seq;
    VhMusicCue active, pending; /* borrowed cue data, not owned */
    VhMusicStage stage;
    unsigned fade_blocks, fade_position, next_fade_in;
    uint64_t blocks_rendered;
    uint32_t switches;
    int last_error;
    unsigned keep_reverb_across_cues; /* opt-in; defaults to 0 */
} VhMusicScene;

void vh_music_scene_init(VhMusicScene *scene, VhNativeSpu *spu);

/* Opt in to preserving STUDIO_C tail between two NON-SILENT music cues.
 * Legacy default (0) resets wet history, and explicit silence/detach
 * always resets it. Must be configured on a silent, idle director before
 * any music request; caller must serialize with the audio producer.
 * Returns -1 without mutation for invalid/busy scenes or flag values.
 */
int vh_music_scene_set_reverb_continuity(VhMusicScene *scene, int enabled);

/* cue==NULL: stop music. A repeated active scene ID does not restart.
 * Validate any new pQES before mutating the current scene/synth.
 * fade_blocks 0 switches immediately; otherwise fade old down,
 * replace at silence on a 512-frame boundary and fade new up.
 * Returns 0 accepted, -1 invalid, -2 fade already in progress.
 */
int vh_music_scene_request(VhMusicScene *scene, const VhMusicCue *cue,
                           unsigned fade_blocks);

/* Produce exactly one interleaved 512-frame stereo PCM block. Performs
 * native SEQ advancement BEFORE mixing. On failure returns -1 and
 * produces silence. During silence outputs zeros and keeps clocks
 * suitable for the independent 44.1->48k audout resampler.
 */
int vh_music_scene_render(VhMusicScene *scene,
                          int16_t stereo[VH_AUDIO_BLOCK_FRAMES * 2u]);

/* Explicit audio-owner teardown: detach every borrowed cue/SEQ and
 * decoded PCM voice, even while a fade or pending switch is underway.
 * Stop/drain the output backend and serialize with render() before
 * invoking this. After return, caller may release its SEQ/VAB/PCM
 * storage; it must not call render() concurrently with an unload.
 * Preserves SPU interpolation/reverb configuration, scene block tally.
 * Idempotent; returns -1 if scene/SPU is uninitialized.
 */
int vh_music_scene_detach(VhMusicScene *scene);

uint32_t vh_music_scene_active_id(const VhMusicScene *scene);

#endif
