#include "vh_native_spu.h"
#include "vh_spu_gaussian.h"

#include <limits.h>
#include <math.h>
#include <string.h>

static int16_t clip16(double s) {
    if (s > INT16_MAX) return INT16_MAX;
    if (s < INT16_MIN) return INT16_MIN;
    return (int16_t)s; /* truncate toward zero like the Python dry mixer */
}

static int64_t floor_div(int64_t value, int64_t divisor) {
    if (value >= 0) return value / divisor;
    return -((-value + divisor - 1) / divisor);
}

static void rate_step(VhAdsrState *a, unsigned shift, unsigned step,
                      int exponential, int decreasing, int all_ones) {
    if (all_ones) return;
    int64_t delta = 7 - (int64_t)step;
    if (decreasing) delta = ~delta;
    if (shift < 11) delta *= INT64_C(1) << (11u - shift);
    int increment = 0x8000;
    if (shift > 11) increment >>= shift - 11u;
    if (exponential && !decreasing && a->level > 0x6000) {
        if (shift < 10) delta = floor_div(delta, 4);
        else if (shift >= 11) increment >>= 2;
        else {
            delta = floor_div(delta, 2);
            increment >>= 1;
        }
    } else if (exponential && decreasing) {
        delta = (delta * a->level) / 0x8000; /* C truncates toward zero */
        if (a->phase == VH_ADSR_RELEASE && delta == 0 && a->level > 0)
            delta = -1;
    }
    if (increment < 1) increment = 1;
    const int64_t counter = (int64_t)a->counter + increment;
    a->counter = (int)(counter & 0x7FFF);
    if (!(counter & 0x8000)) return;
    int64_t level = (int64_t)a->level + delta;
    if (level < 0) level = 0;
    if (!decreasing && level > 0x7FFF) level = 0x7FFF;
    a->level = (int)level;
}

static int adsr_advance(VhAdsrState *a) {
    const uint16_t adsr1 = a->adsr1, adsr2 = a->adsr2;
    switch (a->phase) {
        case VH_ADSR_ATTACK: {
            const unsigned ar = (adsr1 >> 8) & 0x7Fu;
            rate_step(a, ar >> 2, ar & 3u, !!(adsr1 & 0x8000u), 0,
                      ar == 0x7Fu);
            if (a->level >= 0x7FFF) {
                a->level = 0x7FFF;
                a->phase = VH_ADSR_DECAY;
            }
            break;
        }
        case VH_ADSR_DECAY: {
            const int target = ((adsr1 & 15) + 1) << 11;
            const int saturate_target = target > 0x7FFF ? 0x7FFF : target;
            if (a->level <= saturate_target) {
                a->level = saturate_target;
                a->phase = VH_ADSR_SUSTAIN;
            } else {
                rate_step(a, (adsr1 >> 4) & 15u, 0, 1, 1, 0);
                if (a->level <= saturate_target) {
                    a->level = saturate_target;
                    a->phase = VH_ADSR_SUSTAIN;
                }
            }
            break;
        }
        case VH_ADSR_SUSTAIN: {
            const unsigned sr = (adsr2 >> 6) & 0x7Fu;
            const int decrease = !!(adsr2 & 0x4000u);
            rate_step(a, sr >> 2, sr & 3u, !!(adsr2 & 0x8000u),
                      decrease, sr == 0x7Fu);
            if (decrease && a->level <= 0) {
                a->phase = VH_ADSR_OFF;
                return 0;
            }
            break;
        }
        case VH_ADSR_RELEASE:
            if (a->level <= 0) {
                a->phase = VH_ADSR_OFF;
                return 0;
            }
            rate_step(a, adsr2 & 31u, 0, !!(adsr2 & 0x20u), 1,
                      (adsr2 & 31u) == 31u);
            if (a->level <= 0) {
                a->phase = VH_ADSR_OFF;
                return 0;
            }
            break;
        default:
            return 0;
    }
    return 1;
}

void vh_native_spu_reset(VhNativeSpu *spu) {
    if (spu) memset(spu, 0, sizeof(*spu));
}

void vh_native_spu_clear_voices_keep_reverb(VhNativeSpu *spu) {
    if (!spu) return;
    /* Preserve the FIR/delay work area and wet settings without copying
     * the large reverb buffer onto the Switch thread stack.
     */
    memset(spu->voice, 0, sizeof(spu->voice));
    spu->steal_index = 0;
    spu->frames_rendered = 0;
}

int vh_native_spu_set_interpolation(VhNativeSpu *spu, unsigned mode) {
    if (!spu || (mode != VH_SPU_NEAREST && mode != VH_SPU_GAUSSIAN))
        return -1;
    spu->interpolation = mode;
    return 0;
}

int vh_native_spu_set_reverb(VhNativeSpu *spu, int enabled, float depth) {
    if (!spu || !isfinite(depth) || depth < 0.0f || depth > 1.0f)
        return -1;
    spu->reverb_enabled = !!enabled;
    spu->reverb_depth = depth;
    return 0;
}

int vh_native_spu_set_voice_reverb(VhNativeSpu *spu, unsigned slot,
                                   int enabled) {
    if (!spu || slot >= VH_NATIVE_MUSIC_VOICES) return -1;
    spu->voice[slot].reverb_send = !!enabled;
    return 0;
}

int vh_native_spu_allocate_slot(VhNativeSpu *spu) {
    if (!spu) return -1;
    for (unsigned slot = 0; slot < VH_NATIVE_MUSIC_VOICES; ++slot) {
        if (!spu->voice[slot].active) return (int)slot;
    }
    const unsigned selected = spu->steal_index;
    spu->steal_index = (selected + 1u) % VH_NATIVE_MUSIC_VOICES;
    return (int)selected;
}

int vh_native_spu_note_on(
    VhNativeSpu *spu, unsigned slot, const int16_t *pcm, size_t frames,
    int64_t loop_start, int64_t loop_end, uint32_t pitch_step,
    uint16_t adsr1, uint16_t adsr2, float gain_left, float gain_right) {
    if (!spu || slot >= VH_NATIVE_MUSIC_VOICES || !pcm || !frames ||
        frames > SIZE_MAX / 2u || frames > UINT64_MAX / 4096u ||
        !(isfinite(gain_left) && isfinite(gain_right)) ||
        gain_left < 0.0f || gain_left > 2.0f ||
        gain_right < 0.0f || gain_right > 2.0f)
        return -1;
    if (loop_end > loop_start &&
        (loop_start < 0 || loop_end < 0 || (uint64_t)loop_end > frames))
        return -1;
    VhNativeVoice *voice = &spu->voice[slot];
    memset(voice, 0, sizeof(*voice));
    voice->pcm = pcm;
    voice->frames = frames;
    voice->loop_start = loop_start;
    voice->loop_end = loop_end;
    voice->pitch_step = pitch_step < 1 ? 1 :
                        (pitch_step > 0x4000u ? 0x4000u : pitch_step);
    voice->gain_left = gain_left;
    voice->gain_right = gain_right;
    voice->adsr.adsr1 = adsr1;
    voice->adsr.adsr2 = adsr2;
    voice->adsr.phase = VH_ADSR_ATTACK;
    voice->active = 1;
    return 0;
}

void vh_native_spu_note_off(VhNativeSpu *spu, unsigned slot) {
    if (!spu || slot >= VH_NATIVE_MUSIC_VOICES) return;
    VhNativeVoice *v = &spu->voice[slot];
    if (v->active && v->adsr.phase != VH_ADSR_OFF)
        v->adsr.phase = VH_ADSR_RELEASE;
}

int vh_native_spu_voice_active(const VhNativeSpu *spu, unsigned slot) {
    return spu && slot < VH_NATIVE_MUSIC_VOICES && spu->voice[slot].active;
}

void vh_native_spu_render(VhNativeSpu *spu, int16_t *out_stereo, size_t frames) {
    if (!out_stereo || frames > SIZE_MAX / 2u) return;
    if (!spu) {
        memset(out_stereo, 0, frames * 2u * sizeof(int16_t));
        return;
    }
    for (size_t frame = 0; frame < frames; ++frame) {
        double left = 0.0, right = 0.0;
        double send_left = 0.0, send_right = 0.0;
        for (unsigned slot = 0; slot < VH_NATIVE_MUSIC_VOICES; ++slot) {
            VhNativeVoice *v = &spu->voice[slot];
            if (!v->active) continue;
            const size_t index = (size_t)(v->phase >> 12);
            if (index >= v->frames || !adsr_advance(&v->adsr)) {
                v->active = 0;
                continue;
            }
            const int16_t fetched = spu->interpolation == VH_SPU_GAUSSIAN
                ? vh_spu_gaussian_sample(v->pcm, v->frames, v->phase,
                                         v->loop_start, v->loop_end, v->looped)
                : v->pcm[index];
            const double current =
                (double)fetched * v->adsr.level / 32767.0;
            const double vl = current * v->gain_left;
            const double vr = current * v->gain_right;
            left += vl;
            right += vr;
            if (v->reverb_send) {
                send_left += vl;
                send_right += vr;
            }
            v->phase += v->pitch_step;
            if (v->loop_end > v->loop_start && v->loop_start >= 0) {
                const uint64_t end = (uint64_t)v->loop_end << 12;
                if (v->phase >= end) {
                    const uint64_t length =
                        (uint64_t)(v->loop_end - v->loop_start) << 12;
                    const uint64_t wraps = (v->phase - end) / length + 1;
                    v->phase -= wraps * length;
                    v->looped = 1;
                }
            } else if (v->phase >> 12 >= v->frames) {
                v->active = 0;
            }
        }
        if (spu->reverb_enabled) {
            int wet_l = 0, wet_r = 0;
            /* Keep the FIR/work-buffer advancing during silence so the
             * reverb tail decays instead of freezing at Note Off.
             * As in the PC reference, truncate the dry mix and send
             * independently before passing it to the reverb network.
             */
            vh_spu_reverb_process(
                &spu->reverb, (int)send_left, (int)send_right,
                spu->reverb_depth, &wet_l, &wet_r);
            left = (int)left + wet_l;
            right = (int)right + wet_r;
        }
        out_stereo[2 * frame] = clip16(left);
        out_stereo[2 * frame + 1] = clip16(right);
    }
    spu->frames_rendered += frames;
}

size_t vh_native_spu_pump(VhNativeSpu *spu, VhAudioStream *stream, size_t frames) {
    if (!spu || !stream || !frames || frames > VH_AUDIO_BLOCK_FRAMES) return 0;
    if (vh_audio_stream_queued(stream) > VH_AUDIO_RING_FRAMES - frames)
        return 0;
    int16_t block[VH_AUDIO_BLOCK_FRAMES * 2u];
    vh_native_spu_render(spu, block, frames);
    return vh_audio_stream_write(stream, block, frames);
}
