#ifndef VH_AUDIO_SCENE_TRACE_H
#define VH_AUDIO_SCENE_TRACE_H

#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>

/* Bounded append-only, multi-producer event witness.
 * Producers reserve their own unique slot then release-publish ready.
 * No malloc, I/O, mutex, buffer/music pointers or overwrite in the
 * audio worker. Readers may only consume ready slots; full CSV dump
 * takes place after the audio worker is joined. */
#define VH_AUDIO_SCENE_TRACE_CAPACITY 64u

typedef enum {
    VH_SCENE_TRACE_INPUT = 1,  /* game-loop buttons observed */
    VH_SCENE_TRACE_POST = 2,   /* mailbox was about to be updated */
    VH_SCENE_TRACE_ACCEPT = 3, /* vh_music_scene_request returned 0 */
    VH_SCENE_TRACE_SUBMIT_CALL = 4, /* submit/recover call entered */
    VH_SCENE_TRACE_RELEASE_RETURN = 5, /* submit/recover returned success */
    VH_SCENE_TRACE_SUBMIT_ERROR = 6, /* submit/recover exhausted retries */
    VH_SCENE_TRACE_PCM_PAGE_NONZERO = 7, /* generated first 48-kHz page has nonzero signed samples */
    VH_SCENE_TRACE_PCM_PAGE_SILENT = 8 /* generated first 48-kHz page consists only of zeros */
} VhAudioSceneTraceKind;

typedef struct {
    atomic_uint ready;
    unsigned kind;
    unsigned serial;
    unsigned scene;
    uint64_t monotonic_ns;
} VhAudioSceneTraceSlot;

typedef struct {
    atomic_uint reserved;
    atomic_uint dropped;
    VhAudioSceneTraceSlot slot[VH_AUDIO_SCENE_TRACE_CAPACITY];
} VhAudioSceneTrace;

void vh_audio_scene_trace_init(VhAudioSceneTrace *trace);
/* Returns 1 recorded, 0 capacity exhausted, -1 invalid input. The
 * serial may be 0 if the mailbox was changing during an observed
 * acceptance; 0 MUST NOT be correlated to a user-input request. */
int vh_audio_scene_trace_record(VhAudioSceneTrace *trace,
                                VhAudioSceneTraceKind kind,
                                unsigned serial, unsigned scene,
                                uint64_t monotonic_ns);
/* Snapshot only finished rows. Returns 1 when ready, 0 absent/pending,
 * -1 invalid. Caller never touches slot internals. */
int vh_audio_scene_trace_snapshot(const VhAudioSceneTrace *trace,
                                  unsigned index,
                                  VhAudioSceneTraceSlot *out);
/* Writer called only after the producers joined; never from audio
 * callback, scene request, or input/framebuffer loop. Distinct event
 * kinds represent CALL and RETURN, not actual DAC output timing. */
int vh_audio_scene_trace_write_csv(const VhAudioSceneTrace *trace,
                                    FILE *out);
unsigned vh_audio_scene_trace_dropped(const VhAudioSceneTrace *trace);

#endif
