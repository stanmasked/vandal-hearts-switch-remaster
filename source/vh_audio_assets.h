#ifndef VH_AUDIO_ASSETS_H
#define VH_AUDIO_ASSETS_H

#include <stddef.h>
#include <stdint.h>
#include "vh_native_vab.h"

/* Local, user-provided data only. Never embed or ship proprietary files.
 * Fixed filenames prevent filename traversal through untrusted metadata.
 * Everything is loaded before SDL2 audio callback starts.
 */
#define VH_AUDIO_ASSET_SEQ_FILENAME "music.seq"
#define VH_AUDIO_ASSET_VH_FILENAME "music.vh"
#define VH_AUDIO_ASSET_VB_FILENAME "music.vb"
#define VH_AUDIO_ASSET_MAX_SEQ_BYTES VH_SEQ_MAX_BYTES
#define VH_AUDIO_ASSET_MAX_VH_BYTES (32u + 128u * 16u + 128u * 512u + 512u)
#define VH_AUDIO_ASSET_MAX_VB_BYTES (8u * 1024u * 1024u)
#define VH_AUDIO_ASSET_MAX_PATH 512u

enum {
    VH_AUDIO_ASSET_OK = 0,
    VH_AUDIO_ASSET_MISSING = 1, /* all three files absent */
    VH_AUDIO_ASSET_ERROR = -1   /* partial set, invalid or unsafe */
};

typedef struct {
    uint8_t *seq;
    size_t seq_size;
    uint8_t *vh;
    size_t vh_size;
    uint8_t *vb;
    size_t vb_size;
    int16_t *pcm;
    size_t pcm_capacity; /* mono samples */
    VhNativeVab bank;    /* sample pointers refer to pcm */
} VhAudioAssets;

/* Read-only, all-or-nothing initialization from a directory with
 * music.seq, music.vh, music.vb. Caller must zero-initialize *assets.
 * A failed load leaves *assets unchanged. MISSING only if none exist.
 *
 * No access inside the audio callback. Caller must stop and close the
 * audio device/SEQ voices before calling vh_audio_assets_close().
 */
int vh_audio_assets_load(VhAudioAssets *assets, const char *directory);
/* Optional stricter size limit for a second preloaded bank. Input bound
 * is checked before allocating compressed VB and decoded PCM arrays.
 * Existing single-bank users keep the original 8-MiB upper bound.
 */
int vh_audio_assets_load_bounded(VhAudioAssets *assets,
                                 const char *directory, size_t max_vb_bytes);
void vh_audio_assets_close(VhAudioAssets *assets);

#endif
