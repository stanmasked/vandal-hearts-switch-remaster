#ifndef VH_NATIVE_SEQ_H
#define VH_NATIVE_SEQ_H

#include <stddef.h>
#include <stdint.h>
#include "vh_native_spu.h"

/* Sony single-track pQES SEQ; not SMF. Same 512-frame
 * advance-BEFORE-render order as the reference software PC port.
 * This code does not parse VAB banks or provide copyrighted samples.
 */
#define VH_SEQ_CHANNELS 16u
#define VH_SEQ_NOTES 128u
#define VH_SEQ_MAX_BYTES 262144u
#define VH_SEQ_MAX_EVENTS 20000u
#define VH_SEQ_MAX_REPEATS 64u

typedef struct {
    const int16_t *pcm;  /* caller-owned; keep valid while playing */
    size_t frames;
    int64_t loop_start, loop_end;
    uint32_t pitch_step;
    uint16_t adsr1, adsr2;
    unsigned reverb_send; /* selected VAB tone VagAtr.mode bit2 */
    float gain_left, gain_right;
} VhSeqTone;

/* Resolve program/note/velocity/channel controls into already decoded
 * sample and gains. Return 0 to play; nonzero to skip that note.
 * A future VAB-backed resolver will replace synthetic fixtures.
 */
typedef int (*VhSeqResolve)(void *context, unsigned program, unsigned note,
                            unsigned velocity, unsigned channel_volume,
                            unsigned channel_pan, VhSeqTone *out);

typedef struct {
    const uint8_t *bytes;
    size_t length, pos;
    uint16_t ppqn;
    uint32_t tempo;
    uint32_t pending_delta;
    double tick_budget;
    unsigned running;
    uint32_t repeat_remaining; /* 0 means infinite */
    uint32_t cycles_completed;
    uint64_t blocks_advanced, dispatched_events, note_ons, note_offs;
    int playing;
    int last_error;
    uint8_t programs[VH_SEQ_CHANNELS];
    uint8_t volumes[VH_SEQ_CHANNELS];
    uint8_t pans[VH_SEQ_CHANNELS];
    int8_t note_slot[VH_SEQ_CHANNELS][VH_SEQ_NOTES];
    int8_t owner_ch[VH_NATIVE_MUSIC_VOICES];
    int8_t owner_note[VH_NATIVE_MUSIC_VOICES];
    VhNativeSpu *spu;
    VhSeqResolve resolver;
    void *context;
} VhNativeSeq;

/* Inspect a single SEQ pass without advancing SPU or allocating voices.
 * Resolver errors are counted as missing notes; malformed SEQ fails.
 * Use on the loading thread, not while an audio callback is running.
 */
typedef struct {
    uint32_t events, note_events, resolved_notes, missing_notes;
    uint32_t program_changes, tempo_changes;
    unsigned first_missing_program, first_missing_note;
    unsigned first_missing_channel;
    int has_missing;
} VhSeqAudit;

int vh_native_seq_audit(const uint8_t *bytes, size_t length,
                        VhSeqResolve resolve, void *context,
                        VhSeqAudit *report);

/* Validate all events through first FF 2F (up to 256 KiB), then reset
 * playback. repeat_count 1..64 = finite, 0 = loop until caller stops.
 * Invalid inputs return -1 before mutating *seq or *spu.
 */
int vh_native_seq_init(VhNativeSeq *seq, const uint8_t *bytes, size_t length,
                       VhNativeSpu *spu, VhSeqResolve resolve,
                       void *context, unsigned repeat_count);

/* Atomically switch to a separately loaded/validated SEQ and VAB resolver.
 * Validate the next SEQ before touching playback. On failure, preserve
 * the old SEQ, voices and reverb unchanged. On success, remove all old
 * bank PCM references, keep STUDIO_C history/configuration and start the
 * new SEQ at frame zero. The 44.1->48k resampler is caller-owned and is
 * intentionally not reset. Caller must synchronize with audio playback,
 * keep the new bank's PCM alive, and handle already-submitted audout pages.
 * An active SEQ must retain its original SPU instance; mismatches fail.
 */
int vh_native_seq_switch_scene(VhNativeSeq *seq,
                               const uint8_t *bytes, size_t length,
                               VhNativeSpu *spu, VhSeqResolve resolve,
                               void *context, unsigned repeat_count);

/* Adds 512-frame musical tick budget and dispatches all due events
 * BEFORE PCM synthesis. Return count, or -1 on malformed state.
 */
int vh_native_seq_advance_block(VhNativeSeq *seq);

/* Check space first; then advance SEQ, render 512 SPU frames and enqueue.
 * No sequencer or SPU advancement on FIFO backpressure.
 * Caller must synchronize ring access with the SDL callback.
 * Returns 512 on success, 0 on full ring, -1 on invalid/error.
 */
int vh_native_seq_pump(VhNativeSeq *seq, VhAudioStream *ring);

/* Release held notes and stop further scheduling (ADSR tails continue). */
void vh_native_seq_stop(VhNativeSeq *seq);

#endif
