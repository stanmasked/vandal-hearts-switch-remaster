/* Fault-injected output restart: never re-render SEQ, SPU or resampler
 * while retrying an immutable 48-kHz PCM page. Host only, no libnx.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_output_recovery.h"
#include "vh_audio_resample.h"
#include "vh_native_seq.h"

typedef struct {
    unsigned opened, playing, failures_left, submissions, accepted;
    unsigned opens, closes, stops, starts, attempts_this_page;
    int fail_stop, fail_open, fail_start;
    const int16_t *page_pointer;
    size_t page_frames;
    uint64_t page_hash, checksum;
} Mock;

static uint64_t hash_page(const int16_t *pcm, size_t frames) {
    uint64_t h=UINT64_C(1469598103934665603);
    for (size_t i=0;i<frames*2u;i++) {
        h^=(uint16_t)pcm[i];
        h*=UINT64_C(1099511628211);
    }
    return h;
}
static int submit(void *ctx,const int16_t *pcm,size_t frames) {
    Mock *m=ctx;
    assert(m->opened && m->playing && pcm && frames);
    const uint64_t hash=hash_page(pcm,frames);
    if (!m->attempts_this_page) {
        m->page_pointer=pcm;
        m->page_frames=frames;
        m->page_hash=hash;
    } else {
        assert(m->page_pointer==pcm);
        assert(m->page_frames==frames && m->page_hash==hash);
    }
    ++m->attempts_this_page;
    ++m->submissions;
    if (m->failures_left) {
        --m->failures_left;
        return -1;
    }
    ++m->accepted;
    m->checksum=(m->checksum ^ hash)*UINT64_C(1099511628211);
    return 0;
}
static int stop(void *ctx) {
    Mock *m=ctx;
    ++m->stops;
    if (m->fail_stop) return -1;
    m->playing=0;
    return 0;
}
static void close_device(void *ctx) {
    Mock *m=ctx;
    assert(!m->playing);
    ++m->closes;
    m->opened=0;
}
static int open_device(void *ctx) {
    Mock *m=ctx;
    ++m->opens;
    if (m->fail_open) return -1;
    m->opened=1;
    return 0;
}
static int start(void *ctx) {
    Mock *m=ctx;
    ++m->starts;
    if (m->fail_start) return -1;
    assert(m->opened && !m->playing);
    m->playing=1;
    return 0;
}
static VhAudioOutputOps callbacks(Mock *m) {
    const VhAudioOutputOps ops={
        m,submit,stop,close_device,open_device,start
    };
    return ops;
}
static void begin_page(Mock *m,unsigned failures) {
    m->failures_left=failures;
    m->attempts_this_page=0;
    m->page_pointer=NULL;
    m->page_frames=0;
    m->page_hash=0;
}
static const uint8_t song[]={
    'p','Q','E','S',0,0,0,0,1,0xe0,7,0xa1,0x20,0,0,
    0,0xc0,7,0,0x90,60,110,0x81,0x70,0x80,60,0,
    0x81,0x70,0xff,0x2f
};
static int16_t sample[128], src[512u*2u], dst[640u*2u];
static VhNativeSpu spu;
static VhNativeSeq seq;
static VhAudioResample resampler;
static int resolve(void *ctx,unsigned program,unsigned note,
                   unsigned velocity,unsigned volume,unsigned pan,
                   VhSeqTone *out) {
    (void)ctx;(void)velocity;(void)volume;(void)pan;
    if (!out || program!=7u || note!=60u) return -1;
    memset(out,0,sizeof *out);
    out->pcm=sample;
    out->frames=128u;
    out->loop_start=0;
    out->loop_end=128;
    out->pitch_step=4096u;
    out->adsr1=15;
    out->gain_left=.7f;
    out->gain_right=.4f;
    out->reverb_send=1;
    return 0;
}
int main(void) {
    Mock device={.opened=1,.playing=1,
                 .checksum=UINT64_C(1469598103934665603)};
    VhAudioOutputOps ops=callbacks(&device);
    VhAudioOutputRecovery stats={0};
    assert(vh_audio_output_submit_recover(NULL,&stats,dst,10u)==-1);
    assert(vh_audio_output_submit_recover(&ops,NULL,dst,10u)==-1);
    assert(vh_audio_output_submit_recover(&ops,&stats,NULL,10u)==-1);
    assert(vh_audio_output_submit_recover(&ops,&stats,dst,0u)==-1);
    assert(vh_audio_output_submit_recover(
               &ops,&stats,dst,VH_AUDIO_RESAMPLE_MAX_FRAMES+1u)==-1);
    assert(device.submissions==0u && stats.pages_submitted==0u);
    for(unsigned i=0;i<128u;i++)
        sample[i]=(int16_t)((int)i*113-7000);
    vh_native_spu_reset(&spu);
    assert(vh_native_spu_set_reverb(&spu,1,.5f)==0);
    vh_audio_resample_reset(&resampler);
    assert(vh_native_seq_init(&seq,song,sizeof song,&spu,resolve,NULL,0)==0);
    for (unsigned block=0;block<64u;block++) {
        assert(vh_native_seq_advance_block(&seq)>=0);
        vh_native_spu_render(&spu,src,512u);
        const size_t frames=vh_audio_resample_process(
            &resampler,src,512u,dst,640u);
        assert(frames>=555u && frames<=559u);
        const uint64_t old_spu=spu.frames_rendered;
        const uint64_t old_in=resampler.input_frames;
        const uint64_t old_tick=resampler.next_output_tick;
        const uint64_t old_notes=seq.note_ons;
        const unsigned failures=(block%17u==5u)?2u:
                                (block%11u==3u)?1u:0u;
        begin_page(&device,failures);
        assert(vh_audio_output_submit_recover(
            &ops,&stats,dst,frames)==0);
        assert(device.attempts_this_page==failures+1u);
        assert(stats.pages_submitted==block+1u);
        assert(spu.frames_rendered==old_spu);
        assert(resampler.input_frames==old_in);
        assert(resampler.next_output_tick==old_tick);
        assert(seq.note_ons==old_notes);
        assert(old_in==(uint64_t)(block+1u)*512u);
    }
    assert(device.accepted==64u);
    assert(stats.frames_submitted==resampler.next_output_tick/44100u);
    assert(stats.recoveries>0u && stats.submit_failures>0u);

    /* Three failed submissions exceed the two permitted restarts.
     * An external caller can later submit the same prepared page again,
     * but no SEQ/SPU/resampling is performed by the recovery helper.
     */
    const uint64_t old_clock=spu.frames_rendered;
    const uint64_t old_input=resampler.input_frames;
    const uint64_t old_pages=stats.pages_submitted;
    const uint64_t page_hash=hash_page(dst,557u);
    begin_page(&device,3u);
    assert(vh_audio_output_submit_recover(&ops,&stats,dst,557u)==-1);
    assert(device.attempts_this_page==3u);
    assert(stats.pages_submitted==old_pages);
    assert(hash_page(dst,557u)==page_hash);
    assert(spu.frames_rendered==old_clock);
    assert(resampler.input_frames==old_input);
    begin_page(&device,0u);
    assert(vh_audio_output_submit_recover(&ops,&stats,dst,557u)==0);
    assert(stats.pages_submitted==old_pages+1u);

    /* Restart failure must never mark the rejected page as accepted. */
    begin_page(&device,1u);
    device.fail_stop=1;
    const uint64_t accepted=stats.pages_submitted;
    assert(vh_audio_output_submit_recover(&ops,&stats,dst,557u)==-1);
    assert(stats.pages_submitted==accepted);
    assert(spu.frames_rendered==old_clock);
    /* An unsuccessful stop/open/start cannot claim page delivery. */
    for(unsigned stage=0;stage<3u;stage++) {
        Mock broken={.opened=1,.playing=1};
        VhAudioOutputOps bad=callbacks(&broken);
        VhAudioOutputRecovery counts={0};
        begin_page(&broken,1u);
        broken.fail_stop=stage==0u;
        broken.fail_open=stage==1u;
        broken.fail_start=stage==2u;
        assert(vh_audio_output_submit_recover(
            &bad,&counts,dst,557u)==-1);
        assert(counts.pages_submitted==0u);
        assert(counts.frames_submitted==0u);
        assert(broken.submissions==1u);
        assert(spu.frames_rendered==old_clock);
        assert(resampler.input_frames==old_input);
    }
    /* HOME/sleep resume must not generate a new PCM page. */
    Mock paused={.opened=1,.playing=0};
    VhAudioOutputOps pause_ops=callbacks(&paused);
    VhAudioOutputRecovery pause_stats={0};
    const uint64_t old_notes=seq.note_ons;
    assert(vh_audio_output_resume_recover(&pause_ops,&pause_stats,1)==0);
    assert(paused.opened && paused.playing);
    assert(paused.opens==1u && paused.starts==1u);
    assert(pause_stats.pages_submitted==0u);
    assert(pause_stats.resume_recoveries==1u);
    assert(spu.frames_rendered==old_clock);
    assert(resampler.input_frames==old_input);
    assert(seq.note_ons==old_notes);
    printf("audout recovery: %u accepted pages, %u restarts, clock stable PASS\n",
           device.accepted,stats.restart_attempts);
    return 0;
}
