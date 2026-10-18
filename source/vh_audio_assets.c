#include "vh_audio_assets.h"
#include "vh_spu_adpcm.h"

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void dispose(VhAudioAssets *a) {
    free(a->seq);
    free(a->vh);
    free(a->vb);
    free(a->pcm);
    memset(a, 0, sizeof(*a));
}

void vh_audio_assets_close(VhAudioAssets *assets) {
    if (assets) dispose(assets);
}

/* A new file must fit entirely within its published maximum size.
 * ftell failure and seek errors are rejected; no truncating reads.
 * Error 1 is reserved for ENOENT, not permission or I/O errors.
 */
static int read_file(const char *directory, const char *filename,
                     size_t max_bytes, uint8_t **data, size_t *length) {
    char path[VH_AUDIO_ASSET_MAX_PATH];
    const int count = snprintf(path, sizeof(path), "%s/%s",
                               directory, filename);
    if (count < 0 || (size_t)count >= sizeof(path)) return -1;
    FILE *file = fopen(path, "rb");
    if (!file) return errno == ENOENT ? 1 : -1;
    int result = -1;
    if (fseek(file, 0, SEEK_END) != 0) goto done;
    const long bytes = ftell(file);
    if (bytes <= 0 || (unsigned long)bytes > max_bytes) goto done;
    if (fseek(file, 0, SEEK_SET) != 0) goto done;
    uint8_t *buffer = (uint8_t *)malloc((size_t)bytes);
    if (!buffer) goto done;
    const size_t got = fread(buffer, 1, (size_t)bytes, file);
    if (got != (size_t)bytes || ferror(file)) {
        free(buffer);
        goto done;
    }
    *data = buffer;
    *length = got;
    result = 0;
done:
    if (fclose(file) != 0 && result == 0) result = -1;
    if (result != 0) {
        free(*data);
        *data = NULL;
        *length = 0;
    }
    return result;
}

static int fail_load(VhAudioAssets *pending, int status) {
    dispose(pending);
    free(pending);
    return status;
}

int vh_audio_assets_load_bounded(VhAudioAssets *assets,
                                 const char *directory, size_t max_vb_bytes) {
    if (!max_vb_bytes) return VH_AUDIO_ASSET_ERROR;
    if (max_vb_bytes > VH_AUDIO_ASSET_MAX_VB_BYTES)
        max_vb_bytes = VH_AUDIO_ASSET_MAX_VB_BYTES;
    if (!assets || !directory || !*directory ||
        assets->seq || assets->vh || assets->vb || assets->pcm)
        return VH_AUDIO_ASSET_ERROR;

    /* Large VAB metadata stays off the Switch thread stack. */
    VhAudioAssets *pending = (VhAudioAssets *)calloc(1, sizeof(*pending));
    if (!pending) return VH_AUDIO_ASSET_ERROR;
    const int a = read_file(directory, VH_AUDIO_ASSET_SEQ_FILENAME,
                            VH_AUDIO_ASSET_MAX_SEQ_BYTES,
                            &pending->seq, &pending->seq_size);
    const int b = read_file(directory, VH_AUDIO_ASSET_VH_FILENAME,
                            VH_AUDIO_ASSET_MAX_VH_BYTES,
                            &pending->vh, &pending->vh_size);
    const int c = read_file(directory, VH_AUDIO_ASSET_VB_FILENAME,
                            max_vb_bytes,
                            &pending->vb, &pending->vb_size);
    if (a || b || c) {
        const int missing = (a == 1 && b == 1 && c == 1);
        return fail_load(pending, missing ? VH_AUDIO_ASSET_MISSING : VH_AUDIO_ASSET_ERROR);
    }
    /* The conservative upper bound is 28 mono PCM frames per 16 bytes
     * of compressed VB. VH/VB importer decodes only referenced samples.
     */
    const size_t blocks = pending->vb_size / VH_SPU_ADPCM_BLOCK_BYTES;
    if (!blocks || blocks > SIZE_MAX / VH_SPU_ADPCM_BLOCK_FRAMES) {
        return fail_load(pending, VH_AUDIO_ASSET_ERROR);
    }
    pending->pcm_capacity = blocks * VH_SPU_ADPCM_BLOCK_FRAMES;
    if (pending->pcm_capacity > SIZE_MAX / sizeof(int16_t)) {
        return fail_load(pending, VH_AUDIO_ASSET_ERROR);
    }
    pending->pcm = (int16_t *)calloc(pending->pcm_capacity, sizeof(int16_t));
    if (!pending->pcm ||
        vh_native_vab_load(&pending->bank, pending->vh, pending->vh_size,
                           pending->vb, pending->vb_size, pending->pcm,
                           pending->pcm_capacity)) {
        return fail_load(pending, VH_AUDIO_ASSET_ERROR);
    }

    /* Validate full pQES before publishing borrowed pointers to the
     * bank, and before opening the audio device. This is read-only.
     */
    VhNativeSeq validation;
    /* SPU now owns the STUDIO_C work buffer. Do not place ~30 KiB of
     * temporary synth state on the restricted Switch main-thread stack.
     */
    VhNativeSpu *silent = (VhNativeSpu *)calloc(1, sizeof(*silent));
    if (!silent) return fail_load(pending, VH_AUDIO_ASSET_ERROR);
    const int valid_seq = vh_native_seq_init(
        &validation, pending->seq, pending->seq_size,
        silent, vh_native_vab_resolve, &pending->bank,
        0 /* caller-controlled repeat, parser validates before playback */);
    free(silent);
    if (valid_seq) return fail_load(pending, VH_AUDIO_ASSET_ERROR);
    *assets = *pending;
    free(pending);
    return VH_AUDIO_ASSET_OK;
}

int vh_audio_assets_load(VhAudioAssets *assets, const char *directory) {
    return vh_audio_assets_load_bounded(
        assets, directory, VH_AUDIO_ASSET_MAX_VB_BYTES);
}
