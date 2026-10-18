#include "vh_native_vab.h"
#include "vh_spu_adpcm.h"

#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

/* The VH header and program/tone tables are little-endian. The 16-tone
 * block is stored only for populated programs, in program-number order.
 */
static uint16_t le16(const uint8_t *p) {
    return (uint16_t)((unsigned)p[0] | ((unsigned)p[1] << 8));
}

static void pan_factors(unsigned pan, float *left, float *right) {
    if (pan > 127u) pan = 127u;
    *left = pan < 64u ? 1.f : (float)(127u - pan) / 63.f;
    *right = pan < 64u ? (float)pan / 63.f : 1.f;
}

static int load_prepared_vab(VhNativeVab *prepared, const uint8_t *vh, size_t vh_size,
                       const uint8_t *vb, size_t vb_size,
                       int16_t *pcm_arena, size_t pcm_capacity) {
    if (!prepared || !vh || !vb || !pcm_arena || vh_size < 32u + 128u * 16u ||
        memcmp(vh, "pBAV", 4u)) return -1;
    const uint32_t declared_size =
        (uint32_t)vh[12] | ((uint32_t)vh[13] << 8) |
        ((uint32_t)vh[14] << 16) | ((uint32_t)vh[15] << 24);
    const unsigned num_programs = le16(vh + 18);
    const unsigned num_vags = le16(vh + 22);
    if ((declared_size && declared_size < 32u) ||
        num_programs > VH_VAB_PROGRAMS || num_vags > 255u ||
        vh[24] > 127u) return -1;

    memset(prepared, 0, sizeof(*prepared));
    prepared->master_volume = vh[24];
    prepared->vag_count = (uint16_t)num_vags;
    prepared->seq_left = prepared->seq_right = 127u;
    unsigned packed_blocks = 0;
    unsigned active_tones = 0;
    unsigned highest_program = 0;
    for (unsigned p = 0; p < VH_VAB_PROGRAMS; ++p) {
        const uint8_t *record = vh + 32u + p * 16u;
        const unsigned count = record[0];
        if (count > VH_VAB_TONES_PER_PROGRAM ||
            record[1] > 127u || record[4] > 127u) return -1;
        /* PC-port SsVabOpenHeadSticky copies ProgAtr mvol/mpan even
         * for nTone==0. Empty programs can alias a following packed
         * block but retain their OWN gain and pan attributes. */
        prepared->program_tones[p] = (uint8_t)count;
        prepared->program_volume[p] = record[1];
        prepared->program_pan[p] = record[4];
        if (!count) continue;
        ++packed_blocks;
        active_tones += count;
        highest_program = p;
    }
    if (!active_tones) return -1;
    const size_t tone_base = 32u + VH_VAB_PROGRAMS * 16u;
    const size_t size_table_offset =
        tone_base + (size_t)packed_blocks * VH_VAB_TONES_PER_PROGRAM * 32u;
    if (size_table_offset > vh_size ||
        vh_size - size_table_offset < VH_VAB_SAMPLES * 2u) return -1;

    unsigned packed_index = 0;
    uint8_t referenced[VH_VAB_SAMPLES] = {0};
    /* Mirror SsVabOpenHeadSticky's packed-block indexing:
     * - Every program through the last populated program has 16
     *   selectable slots, even when nTone is less than 16.
     * - Empty programs inherit the next populated block because
     *   block[p] is assigned BEFORE the populated-block counter moves.
     *
     * Unlike the reference, never publish a selectable record whose
     * VAG, key range or sample bytes cannot be validated. A nonzero
     * orphan slot is still potentially audible and must be checked.
     */
    for (unsigned p = 0; p <= highest_program; ++p) {
        const unsigned count = prepared->program_tones[p];
        for (unsigned t = 0; t < VH_VAB_TONES_PER_PROGRAM; ++t) {
            const uint8_t *record = vh + tone_base
                                  + (size_t)packed_index * 512u
                                  + (size_t)t * 32u;
            const int active = t < count;
            const int16_t vag = (int16_t)le16(record + 22);
            if (!active && vag <= 0) continue;
            const unsigned low = record[6], high = record[7];
            const int16_t parent = (int16_t)le16(record + 20);
            if (low > 127u || high > 127u || low > high ||
                (active && parent != (int16_t)p) ||
                vag < 1 || vag > (int)num_vags ||
                record[2] > 127u || record[3] > 127u) return -1;
            VhVabTone *dst = &prepared->tones[p][t];
            dst->present = 1;
            dst->low = (uint8_t)low;
            dst->high = (uint8_t)high;
            dst->center = (int8_t)record[4];
            dst->fine = (int8_t)record[5];
            dst->volume = record[2];
            dst->pan = record[3];
            dst->mode = record[1];
            dst->adsr1 = le16(record + 16);
            dst->adsr2 = le16(record + 18);
            dst->vag = (uint16_t)vag;
            referenced[(unsigned)vag] = 1;
        }
        if (count) ++packed_index;
    }

    const uint8_t *sizes = vh + size_table_offset;
    size_t vb_offset = 0, required_frames = 0;
    for (unsigned i = 0; i <= num_vags; ++i) {
        const size_t sample_bytes = (size_t)le16(sizes + 2u * i) * 8u;
        if (sample_bytes && sample_bytes % VH_SPU_ADPCM_BLOCK_BYTES) return -1;
        if (vb_offset > vb_size || sample_bytes > vb_size - vb_offset)
            return -1;
        if (i > 0 && referenced[i]) {
            if (!sample_bytes) return -1;
            VhVabSample *dst = &prepared->samples[i];
            dst->vb_offset = vb_offset;
            dst->adpcm_bytes = sample_bytes;
            const size_t count =
                sample_bytes / VH_SPU_ADPCM_BLOCK_BYTES * VH_SPU_ADPCM_BLOCK_FRAMES;
            if (count > pcm_capacity - required_frames) return -1;
            dst->frames = count;
            required_frames += count;
            /* Validate ALL referenced ADPCM headers before publishing any
             * bank metadata or writing to the caller-owned PCM arena.
             */
            for (size_t offset = 0; offset < sample_bytes; offset += 16u) {
                const uint8_t *block = vb + vb_offset + offset;
                if ((block[0] >> 4) > 4u || (block[0] & 15u) > 12u ||
                    (block[1] & (uint8_t)~7u)) return -1;
            }
        }
        vb_offset += sample_bytes;
    }

    size_t cursor = 0;
    for (unsigned i = 1; i <= num_vags; ++i) {
        if (!referenced[i]) continue;
        VhVabSample *sample = &prepared->samples[i];
        VhSpuAdpcmInfo meta;
        if (vh_spu_adpcm_decode(
                vb + sample->vb_offset, sample->adpcm_bytes,
                pcm_arena + cursor, pcm_capacity - cursor, &meta)) return -1;
        sample->pcm = pcm_arena + cursor;
        sample->frames = meta.frames;
        sample->loop_start = meta.loop_start_frame;
        sample->loop_end = meta.loop_end_frame;
        cursor += meta.frames;
    }
    prepared->required_pcm_frames = required_frames;
    prepared->active = 1;
    return 0;
}

/* Stage parsed bank metadata on the heap: the tone matrix is large
 * enough to put avoidable pressure on Switch thread stacks. Only a fully
 * validated and decoded bank may replace the caller's metadata.
 */
int vh_native_vab_load(VhNativeVab *bank, const uint8_t *vh, size_t vh_size,
                       const uint8_t *vb, size_t vb_size,
                       int16_t *pcm_arena, size_t pcm_capacity) {
    if (!bank) return -1;
    VhNativeVab *staged = (VhNativeVab *)malloc(sizeof(*staged));
    if (!staged) return -1;
    const int result = load_prepared_vab(staged, vh, vh_size, vb, vb_size,
                                         pcm_arena, pcm_capacity);
    if (result == 0) *bank = *staged;
    free(staged);
    return result;
}

int vh_native_vab_resolve(void *context, unsigned program, unsigned note,
                          unsigned velocity, unsigned channel_volume,
                          unsigned channel_pan, VhSeqTone *out) {
    VhNativeVab *bank = context;
    if (!bank || !bank->active || !out || program > 127u || note > 127u ||
        velocity > 127u || channel_volume > 127u || channel_pan > 127u ||
        bank->seq_left > 127u || bank->seq_right > 127u) return -1;
    const VhVabTone *found = NULL;
    unsigned selected_program = 0, selected_tone = 0;
    /* Requested-program range match, then the first global range match.
     * Final fallback minimizes distance to key_min, preserving table order.
     */
    for (unsigned t = 0; t < VH_VAB_TONES_PER_PROGRAM; ++t) {
        const VhVabTone *tone = &bank->tones[program][t];
        if (tone->present && tone->low <= note && note <= tone->high) {
            found = tone;
            selected_program = program;
            selected_tone = t;
            break;
        }
    }
    if (!found) {
        unsigned best_dist = UINT32_MAX;
        for (unsigned p = 0; p < VH_VAB_PROGRAMS; ++p) {
            for (unsigned t = 0; t < VH_VAB_TONES_PER_PROGRAM; ++t) {
                const VhVabTone *tone = &bank->tones[p][t];
                if (!tone->present) continue;
                if (tone->low <= note && note <= tone->high) {
                    found = tone;
                    selected_program = p;
                    selected_tone = t;
                    goto selected;
                }
                const unsigned dist = tone->low > note ?
                    tone->low - note : note - tone->low;
                if (dist < best_dist) {
                    best_dist = dist;
                    found = tone;
                    selected_program = p;
                    selected_tone = t;
                }
            }
        }
    }
selected:
    if (!found) return -1;
    const VhVabSample *sample = &bank->samples[found->vag];
    if (!sample->pcm || !sample->frames) return -1;
    const float semitones = (float)((int)note - (int)found->center) -
                            (float)found->fine / 128.f;
    const float ratio = powf(2.f, semitones / 12.f);
    const float step = ratio * 4096.f;
    const uint32_t pitch = step <= 1.f ? 1u :
                           (step >= 16384.f ? 16384u : (uint32_t)step);

    int gain = (int)velocity * (int)channel_volume / 127;
    gain = gain * bank->master_volume / 127;
    gain = gain * bank->program_volume[selected_program] / 127;
    gain = gain * found->volume / 127;
    float tone_l, tone_r, program_l, program_r, channel_l, channel_r;
    pan_factors(found->pan, &tone_l, &tone_r);
    pan_factors(bank->program_pan[selected_program], &program_l, &program_r);
    pan_factors(channel_pan, &channel_l, &channel_r);
    const float l = (float)(gain * bank->seq_left / 127) / 127.f *
                    tone_l * program_l * channel_l;
    const float r = (float)(gain * bank->seq_right / 127) / 127.f *
                    tone_r * program_r * channel_r;
    out->pcm = sample->pcm;
    out->frames = sample->frames;
    out->loop_start = sample->loop_start;
    out->loop_end = sample->loop_end;
    out->pitch_step = pitch;
    out->adsr1 = found->adsr1;
    out->adsr2 = found->adsr2;
    out->reverb_send = !!(found->mode & 4u);
    out->gain_left = l * l * 1.012f;
    out->gain_right = r * r * 1.012f;
    bank->selected_program = selected_program;
    bank->selected_tone = selected_tone;
    bank->selected_vag = found->vag;
    return 0;
}
