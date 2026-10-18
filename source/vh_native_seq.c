#include "vh_native_seq.h"

#include <limits.h>
#include <string.h>

/* A strict, bounded event parser. Playback and validation share it,
 * so successful initialization guarantees that every first-pass event
 * can be reached without reading outside the caller-owned SEQ bytes.
 */
typedef struct {
    const uint8_t *bytes;
    size_t length, pos;
    unsigned running;
} SeqReader;

typedef struct {
    unsigned kind; /* 0 ignored, 1 on, 2 off, 3 cc, 4 program, 5 tempo, 6 EOT */
    unsigned channel, a, b;
    uint32_t tempo;
} SeqEvent;

static int read_vlq(SeqReader *r, uint32_t *value) {
    uint32_t accum = 0;
    for (unsigned i = 0; i < 4; ++i) {
        if (r->pos >= r->length) return -1;
        unsigned byte = r->bytes[r->pos++];
        accum = (accum << 7) | (byte & 127u);
        if (!(byte & 128u)) {
            *value = accum;
            return 0;
        }
    }
    return -1;
}

static int data_byte(SeqReader *r, unsigned *out) {
    if (r->pos >= r->length || (r->bytes[r->pos] & 128u)) return -1;
    *out = r->bytes[r->pos++];
    return 0;
}

static int read_event(SeqReader *r, SeqEvent *e) {
    memset(e, 0, sizeof(*e));
    if (r->pos >= r->length) return -1;
    unsigned status = r->bytes[r->pos];
    if (status & 128u) {
        ++r->pos;
        r->running = status >= 0x80u && status <= 0xefu ? status : 0;
    } else {
        status = r->running;
        if (!status) return -1;
    }
    if (status == 0xffu) {
        unsigned meta;
        if (r->pos >= r->length) return -1;
        meta = r->bytes[r->pos++];
        if (meta == 0x2fu) {
            e->kind = 6;
            return 0;
        }
        if (meta != 0x51u || r->length - r->pos < 3u) return -1;
        e->kind = 5;
        e->tempo = ((uint32_t)r->bytes[r->pos] << 16)
                 | ((uint32_t)r->bytes[r->pos + 1] << 8)
                 | r->bytes[r->pos + 2];
        if (!e->tempo) e->tempo = 500000u;
        r->pos += 3u;
        return 0;
    }
    if (status < 0x80u || status > 0xefu) return -1;
    e->channel = status & 15u;
    const unsigned type = status & 0xf0u;
    if (data_byte(r, &e->a)) return -1;
    if (type != 0xc0u && type != 0xd0u) {
        if (data_byte(r, &e->b)) return -1;
    }
    if (type == 0x90u) e->kind = e->b ? 1 : 2;
    else if (type == 0x80u) e->kind = 2;
    else if (type == 0xb0u) e->kind = 3;
    else if (type == 0xc0u) e->kind = 4;
    return 0;
}

int vh_native_seq_audit(const uint8_t *bytes, size_t length,
                        VhSeqResolve resolve, void *context,
                        VhSeqAudit *report) {
    if (!bytes || !resolve || !report || length < 15u ||
        length > VH_SEQ_MAX_BYTES || memcmp(bytes, "pQES", 4u))
        return -1;
    VhSeqAudit staged = {0};
    uint8_t program[VH_SEQ_CHANNELS] = {0};
    uint8_t volume[VH_SEQ_CHANNELS], pan[VH_SEQ_CHANNELS];
    for (unsigned ch=0; ch<VH_SEQ_CHANNELS; ++ch) {
        volume[ch]=127u;
        pan[ch]=64u;
    }
    SeqReader reader = {bytes, length, 15u, 0u};
    for (unsigned i=0; i<VH_SEQ_MAX_EVENTS; ++i) {
        uint32_t delta=0;
        SeqEvent e;
        if (read_vlq(&reader,&delta) || read_event(&reader,&e))
            return -1;
        (void)delta;
        ++staged.events;
        if (e.kind==6u) {
            *report=staged; /* only publish after valid EOT */
            return 0;
        }
        switch (e.kind) {
        case 1: {
            ++staged.note_events;
            VhSeqTone tone={0};
            if (!resolve(context,program[e.channel],e.a,e.b,
                         volume[e.channel],pan[e.channel],&tone) &&
                tone.pcm && tone.frames) {
                ++staged.resolved_notes;
            } else {
                ++staged.missing_notes;
                if (!staged.has_missing) {
                    staged.first_missing_channel=e.channel;
                    staged.first_missing_program=program[e.channel];
                    staged.first_missing_note=e.a;
                    staged.has_missing=1;
                }
            }
            break;
        }
        case 3:
            if (e.a==7u || e.a==11u) volume[e.channel]=(uint8_t)e.b;
            else if (e.a==10u) pan[e.channel]=(uint8_t)e.b;
            break;
        case 4:
            program[e.channel]=(uint8_t)e.a;
            ++staged.program_changes;
            break;
        case 5:
            ++staged.tempo_changes;
            break;
        default:
            break;
        }
    }
    return -1;
}

static void stop_note(VhNativeSeq *s, unsigned channel, unsigned note) {
    int slot = s->note_slot[channel][note];
    if (slot < 0 || slot >= (int)VH_NATIVE_MUSIC_VOICES) return;
    s->note_slot[channel][note] = -1;
    if (s->owner_ch[slot] == (int)channel &&
        s->owner_note[slot] == (int)note) {
        vh_native_spu_note_off(s->spu, (unsigned)slot);
        s->owner_ch[slot] = -1;
        s->owner_note[slot] = -1;
        ++s->note_offs;
    }
}

static void stop_all(VhNativeSeq *s, int channel) {
    for (unsigned ch = 0; ch < VH_SEQ_CHANNELS; ++ch) {
        if (channel >= 0 && ch != (unsigned)channel) continue;
        for (unsigned note = 0; note < VH_SEQ_NOTES; ++note)
            stop_note(s, ch, note);
    }
}

static int dispatch(VhNativeSeq *s, const SeqEvent *event) {
    const unsigned ch = event->channel;
    switch (event->kind) {
    case 1: {
        VhSeqTone tone;
        memset(&tone, 0, sizeof(tone));
        if (s->resolver(s->context, s->programs[ch], event->a,
                        event->b, s->volumes[ch], s->pans[ch], &tone))
            return 0; /* bank has no matching tone */
        stop_note(s, ch, event->a); /* note retrigger */
        int slot = vh_native_spu_allocate_slot(s->spu);
        if (slot < 0) return -1;
        const int old_ch = s->owner_ch[slot];
        const int old_note = s->owner_note[slot];
        if (old_ch >= 0 && old_note >= 0 &&
            s->note_slot[old_ch][old_note] == slot)
            s->note_slot[old_ch][old_note] = -1;
        if (vh_native_spu_note_on(
            s->spu, (unsigned)slot, tone.pcm, tone.frames, tone.loop_start,
            tone.loop_end, tone.pitch_step, tone.adsr1, tone.adsr2,
            tone.gain_left, tone.gain_right))
            return -1;
        if (vh_native_spu_set_voice_reverb(
                s->spu, (unsigned)slot, !!tone.reverb_send))
            return -1;
        s->note_slot[ch][event->a] = (int8_t)slot;
        s->owner_ch[slot] = (int8_t)ch;
        s->owner_note[slot] = (int8_t)event->a;
        ++s->note_ons;
        break;
    }
    case 2:
        stop_note(s, ch, event->a);
        break;
    case 3:
        if (event->a == 7u || event->a == 11u)
            s->volumes[ch] = (uint8_t)event->b;
        else if (event->a == 10u)
            s->pans[ch] = (uint8_t)event->b;
        else if (event->a == 0x78u || event->a == 0x7bu)
            stop_all(s, (int)ch);
        break;
    case 4:
        s->programs[ch] = (uint8_t)event->a;
        break;
    case 5:
        s->tempo = event->tempo;
        break;
    default:
        break;
    }
    return 0;
}

void vh_native_seq_stop(VhNativeSeq *s) {
    if (!s || !s->spu) return;
    s->playing = 0;
    stop_all(s, -1);
}

int vh_native_seq_init(VhNativeSeq *s, const uint8_t *bytes, size_t length,
                       VhNativeSpu *spu, VhSeqResolve resolve,
                       void *context, unsigned repeat_count) {
    if (!s || !bytes || !spu || !resolve || length < 15u ||
        length > VH_SEQ_MAX_BYTES || repeat_count > VH_SEQ_MAX_REPEATS ||
        memcmp(bytes, "pQES", 4u)) return -1;

    SeqReader reader = {bytes, length, 15u, 0u};
    uint64_t ticks = 0;
    int ended = 0;
    for (unsigned count = 0; count < VH_SEQ_MAX_EVENTS; ++count) {
        uint32_t delta = 0;
        SeqEvent event;
        if (read_vlq(&reader, &delta) || read_event(&reader, &event)) return -1;
        ticks += delta;
        if (event.kind == 6u) { ended = 1; break; }
    }
    if (!ended || (!repeat_count && !ticks)) return -1;

    VhNativeSeq prepared;
    memset(&prepared, 0, sizeof(prepared));
    prepared.bytes = bytes;
    prepared.length = length;
    prepared.pos = 15u;
    prepared.ppqn = (uint16_t)(((unsigned)bytes[8] << 8) | bytes[9]);
    if (!prepared.ppqn) prepared.ppqn = 480u;
    prepared.tempo = ((uint32_t)bytes[10] << 16) |
                     ((uint32_t)bytes[11] << 8) | bytes[12];
    if (!prepared.tempo) prepared.tempo = 500000u;
    prepared.repeat_remaining = repeat_count;
    prepared.spu = spu;
    prepared.resolver = resolve;
    prepared.context = context;
    prepared.playing = 1;
    for (unsigned ch = 0; ch < VH_SEQ_CHANNELS; ++ch) {
        prepared.volumes[ch] = 127;
        prepared.pans[ch] = 64;
        for (unsigned note = 0; note < VH_SEQ_NOTES; ++note)
            prepared.note_slot[ch][note] = -1;
    }
    for (unsigned slot = 0; slot < VH_NATIVE_MUSIC_VOICES; ++slot) {
        prepared.owner_ch[slot] = -1;
        prepared.owner_note[slot] = -1;
    }
    reader.pos = 15u;
    if (read_vlq(&reader, &prepared.pending_delta)) return -1;
    prepared.pos = reader.pos;
    *s = prepared;
    return 0;
}

int vh_native_seq_switch_scene(VhNativeSeq *seq,
                               const uint8_t *bytes, size_t length,
                               VhNativeSpu *spu, VhSeqResolve resolve,
                               void *context, unsigned repeat_count) {
    if (!seq || !spu || (seq->spu && seq->spu != spu)) return -1;

    /* Initialization validates the complete first SEQ pass without
     * changing SPU or current playback. Never clear voices for bad music.
     */
    VhNativeSeq prepared;
    if (vh_native_seq_init(&prepared, bytes, length, spu, resolve,
                           context, repeat_count))
        return -1;

    if (seq->spu == spu)
        vh_native_seq_stop(seq);
    vh_native_spu_clear_voices_keep_reverb(spu);
    *seq = prepared;
    return 0;
}

int vh_native_seq_advance_block(VhNativeSeq *s) {
    if (!s || !s->spu || !s->resolver || s->last_error) return -1;
    if (!s->playing) return 0;
    /* Snapshot tempo: FF51 within this block affects subsequent blocks. */
    s->tick_budget += 512.0 * s->ppqn * 1000000.0 /
                      (44100.0 * (double)s->tempo);
    ++s->blocks_advanced;
    int processed = 0;
    while (s->tick_budget >= (double)s->pending_delta) {
        if (++processed > (int)VH_SEQ_MAX_EVENTS) {
            s->last_error = -1;
            vh_native_seq_stop(s);
            return -1;
        }
        s->tick_budget -= (double)s->pending_delta;
        SeqReader r = {s->bytes, s->length, s->pos, s->running};
        SeqEvent event;
        if (read_event(&r, &event)) {
            s->last_error = -1;
            vh_native_seq_stop(s);
            return -1;
        }
        s->pos = r.pos;
        s->running = r.running;
        ++s->dispatched_events;
        if (event.kind == 6u) {
            ++s->cycles_completed;
            if (s->repeat_remaining &&
                s->cycles_completed >= s->repeat_remaining) {
                vh_native_seq_stop(s);
                break;
            }
            /* Clean FF2F seam: retained tempo and held notes. */
            s->tick_budget = 0.0;
            s->pos = 15u;
            s->running = 0u;
            r.pos = 15u;
            r.running = 0u;
            if (read_vlq(&r, &s->pending_delta)) {
                s->last_error = -1;
                vh_native_seq_stop(s);
                return -1;
            }
            s->pos = r.pos;
            continue;
        }
        if (dispatch(s, &event)) {
            s->last_error = -1;
            vh_native_seq_stop(s);
            return -1;
        }
        r.pos = s->pos;
        if (read_vlq(&r, &s->pending_delta)) {
            s->last_error = -1;
            vh_native_seq_stop(s);
            return -1;
        }
        s->pos = r.pos;
    }
    return processed;
}

int vh_native_seq_pump(VhNativeSeq *s, VhAudioStream *ring) {
    if (!s || !s->spu || !ring || s->last_error) return -1;
    if (vh_audio_stream_queued(ring) >
        VH_AUDIO_RING_FRAMES - VH_AUDIO_BLOCK_FRAMES) return 0;
    if (vh_native_seq_advance_block(s) < 0) return -1;
    int16_t pcm[VH_AUDIO_BLOCK_FRAMES * VH_AUDIO_CHANNELS];
    vh_native_spu_render(s->spu, pcm, VH_AUDIO_BLOCK_FRAMES);
    return vh_audio_stream_write(ring, pcm, VH_AUDIO_BLOCK_FRAMES) ==
        VH_AUDIO_BLOCK_FRAMES ? (int)VH_AUDIO_BLOCK_FRAMES : -1;
}
