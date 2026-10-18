#include "vh_music_scene.h"

#include <stdint.h>
#include <string.h>

void vh_music_scene_init(VhMusicScene *scene, VhNativeSpu *spu) {
    if (!scene) return;
    memset(scene, 0, sizeof(*scene));
    scene->spu = spu;
}

int vh_music_scene_set_reverb_continuity(VhMusicScene *s, int enabled) {
    if (!s || !s->spu || (enabled != 0 && enabled != 1) ||
        s->stage != VH_MUSIC_SILENT || s->active.id || s->pending.id ||
        s->last_error)
        return -1;
    s->keep_reverb_across_cues = (unsigned)enabled;
    return 0;
}

int vh_music_scene_detach(VhMusicScene *s) {
    if (!s || !s->spu) return -1;
    /* This is the explicit point where caller-owned SEQ/VAB/PCM can
     * become freeable. Every SPU voice and reverb history is zeroed
     * BEFORE the director loses the borrowed source pointers.
     * The audout/SDL consumer must already be stopped and drained.
     */
    const unsigned interpolation = s->spu->interpolation;
    const int reverb_enabled = s->spu->reverb_enabled;
    const float reverb_depth = s->spu->reverb_depth;
    vh_native_spu_reset(s->spu);
    if (vh_native_spu_set_interpolation(s->spu, interpolation) ||
        vh_native_spu_set_reverb(s->spu, reverb_enabled, reverb_depth))
        return -1;
    const int had_cue = s->active.id || s->pending.id;
    memset(&s->seq, 0, sizeof(s->seq));
    memset(&s->active, 0, sizeof(s->active));
    memset(&s->pending, 0, sizeof(s->pending));
    s->stage = VH_MUSIC_SILENT;
    s->fade_blocks = s->fade_position = s->next_fade_in = 0u;
    s->last_error = 0;
    if (had_cue) ++s->switches;
    return 0;
}

uint32_t vh_music_scene_active_id(const VhMusicScene *scene) {
    return scene ? scene->active.id : 0u;
}

static int cue_is_valid(VhMusicScene *s, const VhMusicCue *cue) {
    if (!cue) return 1; /* explicit silence request */
    if (!cue->id || !cue->seq || !cue->seq_size || !cue->resolver ||
        cue->repeats > VH_SEQ_MAX_REPEATS) return 0;
    VhNativeSeq validation;
    /* vh_native_seq_init validates input but does not alter the SPU
     * or invoke the resolver. The staging struct is only ~3 KiB.
     */
    return vh_native_seq_init(&validation, cue->seq, cue->seq_size,
                              s->spu, cue->resolver, cue->context,
                              cue->repeats) == 0;
}

static int switch_to(VhMusicScene *s, const VhMusicCue *cue) {
    /* Every outgoing voice and reverb buffer is now inaudible.
     * Clear old pointers BEFORE the caller can release old bank PCM.
     * The incoming track gets new channel and voice ownership.
     */
    if (s->keep_reverb_across_cues && cue && cue->id) {
        /* Optional continuity between actual music cues only. First
         * validate and stage the replacement, then detach old PCM
         * voices without flushing the already accumulated wet tail. */
        if (vh_native_seq_switch_scene(&s->seq, cue->seq, cue->seq_size,
                                       s->spu, cue->resolver, cue->context,
                                       cue->repeats))
            return -1;
    } else {
        /* Historical default: discard the old wet history, and ALWAYS
         * clear it for explicit silence / bank unload. */
        const unsigned interpolation = s->spu->interpolation;
        const int reverb_on = s->spu->reverb_enabled;
        const float reverb_depth = s->spu->reverb_depth;
        vh_native_spu_reset(s->spu);
        if (vh_native_spu_set_interpolation(s->spu, interpolation) ||
            vh_native_spu_set_reverb(s->spu, reverb_on, reverb_depth))
            return -1;
        memset(&s->seq, 0, sizeof(s->seq));
        if (cue && cue->id &&
            vh_native_seq_init(&s->seq, cue->seq, cue->seq_size,
                               s->spu, cue->resolver, cue->context,
                               cue->repeats))
            return -1;
    }
    memset(&s->active, 0, sizeof(s->active));
    if (cue && cue->id) s->active = *cue;
    ++s->switches;
    return 0;
}

int vh_music_scene_request(VhMusicScene *s, const VhMusicCue *cue,
                           unsigned fade_blocks) {
    if (!s || !s->spu || s->last_error ||
        fade_blocks > VH_MUSIC_SCENE_MAX_FADE_BLOCKS)
        return -1;
    if (s->stage == VH_MUSIC_FADE_OUT ||
        s->stage == VH_MUSIC_FADE_IN ||
        s->stage == VH_MUSIC_SWITCH_PENDING)
        return -2;
    const uint32_t incoming_id = cue ? cue->id : 0u;
    if (incoming_id == s->active.id) return 0;
    if (!cue_is_valid(s, cue)) return -1;

    if (!fade_blocks || s->stage == VH_MUSIC_SILENT) {
        if (switch_to(s, cue)) {
            s->last_error = -1;
            return -1;
        }
        s->fade_blocks = fade_blocks;
        s->fade_position = 0;
        s->next_fade_in = 0;
        s->stage = incoming_id
            ? (fade_blocks ? VH_MUSIC_FADE_IN : VH_MUSIC_PLAYING)
            : VH_MUSIC_SILENT;
        return 0;
    }
    s->pending = cue ? *cue : (VhMusicCue){0};
    s->next_fade_in = fade_blocks;
    s->fade_blocks = fade_blocks;
    s->fade_position = 0;
    s->stage = VH_MUSIC_FADE_OUT;
    return 0;
}

static int16_t scale_pcm(int16_t sample, int32_t gain) {
    return (int16_t)(((int64_t)sample * gain) / 32768);
}

int vh_music_scene_render(VhMusicScene *s,
                          int16_t stereo[VH_AUDIO_BLOCK_FRAMES * 2u]) {
    if (!s || !s->spu || !stereo) return -1;
    if (s->last_error) {
        memset(stereo, 0, VH_AUDIO_BLOCK_FRAMES * 2u * sizeof(*stereo));
        return -1;
    }

    if (s->stage == VH_MUSIC_SWITCH_PENDING) {
        const VhMusicCue pending = s->pending;
        if (switch_to(s, pending.id ? &pending : NULL)) {
            s->last_error = -1;
            memset(stereo, 0, VH_AUDIO_BLOCK_FRAMES * 2u * sizeof(*stereo));
            return -1;
        }
        memset(&s->pending, 0, sizeof(s->pending));
        s->fade_blocks = s->next_fade_in;
        s->fade_position = 0;
        s->next_fade_in = 0;
        s->stage = s->active.id
            ? (s->fade_blocks ? VH_MUSIC_FADE_IN : VH_MUSIC_PLAYING)
            : VH_MUSIC_SILENT;
    }

    if (s->stage == VH_MUSIC_SILENT) {
        memset(stereo, 0, VH_AUDIO_BLOCK_FRAMES * 2u * sizeof(*stereo));
    } else {
        if (vh_native_seq_advance_block(&s->seq) < 0) {
            s->last_error = -1;
            memset(stereo, 0, VH_AUDIO_BLOCK_FRAMES * 2u * sizeof(*stereo));
            return -1;
        }
        vh_native_spu_render(s->spu, stereo, VH_AUDIO_BLOCK_FRAMES);

        if (s->stage == VH_MUSIC_FADE_IN ||
            s->stage == VH_MUSIC_FADE_OUT) {
            const int32_t total = (int32_t)s->fade_blocks;
            const int32_t progress = (int32_t)s->fade_position;
            const int32_t from = s->stage == VH_MUSIC_FADE_IN
                ? (int32_t)((int64_t)progress * 32768 / total)
                : (int32_t)((int64_t)(total - progress) * 32768 / total);
            const int32_t to = s->stage == VH_MUSIC_FADE_IN
                ? (int32_t)((int64_t)(progress + 1) * 32768 / total)
                : (int32_t)((int64_t)(total - progress - 1) * 32768 / total);
            for (unsigned i = 0; i < VH_AUDIO_BLOCK_FRAMES; ++i) {
                const int32_t gain = from + (int32_t)(
                    ((int64_t)(to - from) * (i + 1u)) /
                    VH_AUDIO_BLOCK_FRAMES);
                stereo[2u * i] = scale_pcm(stereo[2u * i], gain);
                stereo[2u * i + 1u] = scale_pcm(stereo[2u * i + 1u], gain);
            }
            ++s->fade_position;
            if (s->fade_position == s->fade_blocks) {
                s->stage = s->stage == VH_MUSIC_FADE_OUT
                    ? VH_MUSIC_SWITCH_PENDING : VH_MUSIC_PLAYING;
            }
        }
    }
    ++s->blocks_rendered;
    return 0;
}
