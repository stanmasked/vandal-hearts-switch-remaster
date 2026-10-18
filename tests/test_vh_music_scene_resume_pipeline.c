/* Synthetic integration: two-scene director -> SPU -> 48-kHz PCM ->
 * restart ramp -> exactly-once callback/replay.  No physical audout.
 * A callback-free reference renderer independently generates each page.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_music_scene.h"
#include "vh_audio_resample.h"
#include "vh_audio_output_ramp.h"
#include "vh_audio_output_recovery.h"

#define BLOCKS 64u
#define HASH_INIT UINT64_C(1469598103934665603)
#define HASH_MULT UINT64_C(1099511628211)
#define HDR 'p','Q','E','S',0,0,0,0,1,0xe0,7,0xa1,0x20,0,0

static const uint8_t first_song[]={
    HDR,0,0xc0,7,0,0x90,60,110,0x87,0x68,0x80,60,0,
    0,0xff,0x2f
};
static const uint8_t second_song[]={
    HDR,0,0xc0,9,0,0x90,64,105,0x87,0x68,0x80,64,0,
    0,0xff,0x2f
};
static int16_t first_bank[128],second_bank[128];
static VhNativeSpu source_spu,oracle_spu;
static VhMusicScene source_scene,oracle_scene;
static VhAudioResample source_rate,oracle_rate;
static VhAudioOutputRamp source_ramp,oracle_ramp;
static int16_t source_raw[VH_AUDIO_BLOCK_FRAMES*2u];
static int16_t oracle_raw[VH_AUDIO_BLOCK_FRAMES*2u];
static int16_t source_pcm[VH_AUDIO_RESAMPLE_MAX_FRAMES*2u];
static int16_t oracle_pcm[VH_AUDIO_RESAMPLE_MAX_FRAMES*2u];

static int resolve(void *opaque,unsigned program,unsigned note,
                   unsigned velocity,unsigned volume,unsigned pan,
                   VhSeqTone *tone) {
    (void)opaque;(void)velocity;(void)volume;(void)pan;
    memset(tone,0,sizeof *tone);
    if(program==7u && note==60u) tone->pcm=first_bank;
    else if(program==9u && note==64u) tone->pcm=second_bank;
    else return -1;
    tone->frames=128u;
    tone->loop_start=0;
    tone->loop_end=128;
    tone->pitch_step=4096u;
    tone->adsr1=15u;
    tone->adsr2=0u;
    tone->gain_left=0.75f;
    tone->gain_right=0.5f;
    tone->reverb_send=1u;
    return 0;
}
static uint64_t hash_pcm(const int16_t *p,size_t n) {
    uint64_t h=HASH_INIT;
    for(size_t i=0;i<n*2u;i++) {
        h^=(uint16_t)p[i];
        h*=HASH_MULT;
    }
    return h;
}
typedef struct {
    int opened,playing;
    unsigned failures_left,tries;
    unsigned stops,closes,opens,starts;
    unsigned fail_opens_left,fail_starts_left,fail_stops_left;
    uint64_t submissions,accepted,rolling_hash;
    const int16_t *page;
    size_t frames;
    uint64_t page_hash;
} Device;
static int submit(void *opaque,const int16_t *pcm,size_t frames) {
    Device *d=opaque;
    assert(d->opened && d->playing && pcm==source_pcm);
    assert(frames>=555u && frames<=559u);
    const uint64_t digest=hash_pcm(pcm,frames);
    if(!d->tries) {
        d->page=pcm;
        d->frames=frames;
        d->page_hash=digest;
    } else {
        assert(d->page==pcm && d->frames==frames &&
               d->page_hash==digest);
    }
    ++d->tries;
    ++d->submissions;
    if(d->failures_left) {
        --d->failures_left;
        return -1;
    }
    ++d->accepted;
    d->rolling_hash=(d->rolling_hash^digest)*HASH_MULT;
    return 0;
}
static int stop(void *opaque) {
    Device *d=opaque;
    ++d->stops;
    if(d->fail_stops_left) {
        --d->fail_stops_left;
        return -1; /* stop not confirmed: do not close the backend */
    }
    d->playing=0;
    return 0;
}
static void close_out(void *opaque) {
    Device *d=opaque;
    assert(!d->playing);
    /* Idempotent close: retry follows an already-failed open. */
    if(!d->opened) return;
    ++d->closes;
    d->opened=0;
}
static int open_out(void *opaque) {
    Device *d=opaque;
    assert(!d->opened);
    ++d->opens;
    if(d->fail_opens_left) {
        --d->fail_opens_left;
        return -1;
    }
    d->opened=1;
    return 0;
}
static int start(void *opaque) {
    Device *d=opaque;
    assert(d->opened && !d->playing);
    ++d->starts;
    if(d->fail_starts_left) {
        --d->fail_starts_left;
        return -1;
    }
    d->playing=1;
    return 0;
}
static void request_both(const VhMusicCue *cue,unsigned fade) {
    assert(vh_music_scene_request(&source_scene,cue,fade)==0);
    assert(vh_music_scene_request(&oracle_scene,cue,fade)==0);
}
int main(void) {
    for(unsigned i=0;i<128u;i++) {
        first_bank[i]=(int16_t)(8000+(int)i*31);
        second_bank[i]=(int16_t)(-9000-(int)i*29);
    }
    vh_native_spu_reset(&source_spu);
    vh_native_spu_reset(&oracle_spu);
    assert(!vh_native_spu_set_reverb(&source_spu,1,0.5f));
    assert(!vh_native_spu_set_reverb(&oracle_spu,1,0.5f));
    vh_music_scene_init(&source_scene,&source_spu);
    vh_music_scene_init(&oracle_scene,&oracle_spu);
    vh_audio_resample_reset(&source_rate);
    vh_audio_resample_reset(&oracle_rate);
    vh_audio_output_ramp_arm(&source_ramp);
    vh_audio_output_ramp_arm(&oracle_ramp);

    const VhMusicCue a={101u,first_song,sizeof first_song,0u,resolve,NULL};
    const VhMusicCue b={202u,second_song,sizeof second_song,0u,resolve,NULL};
    request_both(&a,0u);

    Device dev={.opened=1,.playing=1,.rolling_hash=HASH_INIT};
    const VhAudioOutputOps ops={
        &dev,submit,stop,close_out,open_out,start
    };
    VhAudioOutputRecovery stats={0};
    uint64_t reference_hash=HASH_INIT;
    uint64_t returned_frames=0;
    unsigned recovered_pages=0u,failures=0u;
    unsigned switched=0u,silent=0u,signalled=0u;
    unsigned ramp_due=1u,ramp_exercised=0u;
    for(unsigned block=0u;block<BLOCKS;block++) {
        if(block==12u) request_both(&b,3u);
        if(block==30u) request_both(NULL,2u);
        if(block==38u) request_both(&a,2u);
        assert(vh_music_scene_render(&source_scene,source_raw)==0);
        assert(vh_music_scene_render(&oracle_scene,oracle_raw)==0);
        assert(!memcmp(source_raw,oracle_raw,sizeof source_raw));
        const size_t frames=vh_audio_resample_process(
            &source_rate,source_raw,VH_AUDIO_BLOCK_FRAMES,
            source_pcm,VH_AUDIO_RESAMPLE_MAX_FRAMES);
        const size_t oracle_frames=vh_audio_resample_process(
            &oracle_rate,oracle_raw,VH_AUDIO_BLOCK_FRAMES,
            oracle_pcm,VH_AUDIO_RESAMPLE_MAX_FRAMES);
        assert(frames==oracle_frames && frames>=555u && frames<=559u);
        assert(!memcmp(source_pcm,oracle_pcm,frames*2u*sizeof(int16_t)));
        assert(!vh_audio_output_ramp_apply(&source_ramp,source_pcm,frames));
        assert(!vh_audio_output_ramp_apply(&oracle_ramp,oracle_pcm,frames));
        assert(!memcmp(source_pcm,oracle_pcm,frames*2u*sizeof(int16_t)));
        if(ramp_due) {
            /* The first page after each successful start/reopen fades
             * from silence; a submit retry may NOT rearm the ramp. */
            assert(source_pcm[0]==0 && source_pcm[1]==0);
            assert(source_ramp.position==VH_AUDIO_OUTPUT_RAMP_FRAMES);
            ++ramp_exercised;
            ramp_due=0u;
        }
        const uint64_t expected=((uint64_t)(block+1u)*
            VH_AUDIO_BLOCK_FRAMES-1u)*VH_NATIVE_AUDOUT_RATE/
            VH_AUDIO_SAMPLE_RATE+1u;
        returned_frames+=frames;
        assert(returned_frames==expected);
        assert(source_rate.input_frames==
               (uint64_t)(block+1u)*VH_AUDIO_BLOCK_FRAMES);
        assert(!memcmp(&source_rate,&oracle_rate,sizeof source_rate));
        assert(source_scene.stage==oracle_scene.stage &&
               source_scene.switches==oracle_scene.switches &&
               vh_music_scene_active_id(&source_scene)==
               vh_music_scene_active_id(&oracle_scene));
        if(source_scene.switches>1u) switched=1u;
        unsigned nonzero=0u;
        for(size_t i=0;i<2u*frames;i++)
            nonzero+=(source_pcm[i]!=0);
        if(nonzero) ++signalled; else ++silent;

        const VhMusicScene saved_scene=source_scene;
        const VhNativeSpu saved_spu=source_spu;
        const VhAudioResample saved_rate=source_rate;
        const VhAudioOutputRamp saved_ramp=source_ramp;
        const uint64_t digest=hash_pcm(source_pcm,frames);
        const uint64_t before_submits=dev.submissions;
        dev.tries=0u;
        dev.failures_left=block%12u==11u?(block==35u?2u:1u):0u;
        failures+=dev.failures_left;
        recovered_pages+=(dev.failures_left!=0);
        if(block==51u) {
            /* A failed submit followed by REFUSED stop is neither a
             * returned descriptor nor permission to close/reopen.
             * Explicitly resend the identical prepared PCM page,
             * without re-rendering/advancing SEQ or rearming ramp. */
            ++failures;
            const VhAudioOutputRecovery before=stats;
            const unsigned closes=dev.closes,opens=dev.opens;
            const unsigned starts=dev.starts;
            const uint64_t delivered=dev.accepted;
            dev.failures_left=1u;
            dev.fail_stops_left=1u;
            assert(vh_audio_output_submit_recover(
                &ops,&stats,source_pcm,frames)==-1);
            assert(!dev.failures_left && !dev.fail_stops_left);
            assert(dev.opened && dev.playing &&
                   dev.closes==closes && dev.opens==opens &&
                   dev.starts==starts);
            assert(dev.accepted==delivered &&
                   dev.submissions==before_submits+1u);
            assert(stats.pages_submitted==before.pages_submitted &&
                   stats.frames_submitted==before.frames_submitted &&
                   stats.restart_attempts==before.restart_attempts &&
                   stats.recoveries==before.recoveries &&
                   stats.submit_failures==before.submit_failures+1u);
            assert(hash_pcm(source_pcm,frames)==digest);
            assert(!memcmp(&source_scene,&saved_scene,
                           sizeof saved_scene));
            assert(!memcmp(&source_spu,&saved_spu,sizeof saved_spu));
            assert(!memcmp(&source_rate,&saved_rate,sizeof saved_rate));
            assert(!memcmp(&source_ramp,&saved_ramp,sizeof saved_ramp));
        }
        assert(vh_audio_output_submit_recover(
            &ops,&stats,source_pcm,frames)==0);
        assert(dev.submissions==before_submits+
               (uint64_t)(block==51u?2u:
                 block%12u==11u?(block==35u?3u:2u):1u));
        assert(hash_pcm(source_pcm,frames)==digest);
        assert(!memcmp(&source_scene,&saved_scene,sizeof saved_scene));
        assert(!memcmp(&source_spu,&saved_spu,sizeof saved_spu));
        assert(!memcmp(&source_rate,&saved_rate,sizeof saved_rate));
        assert(!memcmp(&source_ramp,&saved_ramp,sizeof saved_ramp));
        reference_hash=(reference_hash^hash_pcm(oracle_pcm,frames))*HASH_MULT;
        assert(dev.rolling_hash==reference_hash);
        assert(dev.accepted==block+1u);
        if(block==13u || block==29u || block==48u) {
            const uint64_t old_pages=stats.pages_submitted;
            const uint64_t old_frames=stats.frames_submitted;
            const uint64_t old_hash=dev.rolling_hash;
            const VhAudioResample old_rate=source_rate;
            const VhNativeSpu old_spu=source_spu;
            const VhMusicScene old_scene=source_scene;
            if(block==48u) {
                /* First refuse a stop while the device is PLAYING.
                 * This forbids releasing a live audout descriptor,
                 * closing the service or advancing musical clocks. */
                const VhAudioOutputRecovery before=stats;
                const unsigned closes=dev.closes,opens=dev.opens;
                const unsigned starts=dev.starts;
                dev.fail_stops_left=1u;
                assert(vh_audio_output_resume_recover(
                    &ops,&stats,1)==-1);
                assert(dev.opened && dev.playing &&
                       !dev.fail_stops_left);
                assert(dev.closes==closes && dev.opens==opens &&
                       dev.starts==starts);
                assert(!memcmp(&stats,&before,sizeof before));
                assert(stats.pages_submitted==old_pages &&
                       stats.frames_submitted==old_frames &&
                       dev.rolling_hash==old_hash);
                assert(!memcmp(&source_scene,&old_scene,
                               sizeof old_scene));
                assert(!memcmp(&source_spu,&old_spu,sizeof old_spu));
                assert(!memcmp(&source_rate,&old_rate,
                               sizeof old_rate));
            }
            assert(!stop(&dev));
            if(block==48u) {
                /* Next refuse stop while it is ALREADY STOPPED.
                 * A forced reopen still must not release anything
                 * after a failed stop, until explicitly retried. */
                const VhAudioOutputRecovery before=stats;
                const unsigned closes=dev.closes,opens=dev.opens;
                const unsigned starts=dev.starts;
                dev.fail_stops_left=1u;
                assert(vh_audio_output_resume_recover(
                    &ops,&stats,1)==-1);
                assert(dev.opened && !dev.playing &&
                       !dev.fail_stops_left);
                assert(dev.closes==closes && dev.opens==opens &&
                       dev.starts==starts);
                assert(!memcmp(&stats,&before,sizeof before));
                assert(stats.pages_submitted==old_pages &&
                       stats.frames_submitted==old_frames &&
                       dev.rolling_hash==old_hash);
                assert(!memcmp(&source_scene,&old_scene,
                               sizeof old_scene));
                assert(!memcmp(&source_spu,&old_spu,sizeof old_spu));
                assert(!memcmp(&source_rate,&old_rate,
                               sizeof old_rate));
            }
            if(block==13u) dev.fail_starts_left=1u;
            if(block==29u) dev.fail_opens_left=1u;
            assert(!vh_audio_output_resume_recover(
                &ops,&stats,(int)(block!=13u)));
            assert(dev.opened && dev.playing);
            assert(stats.pages_submitted==old_pages &&
                   stats.frames_submitted==old_frames &&
                   dev.rolling_hash==old_hash);
            assert(!memcmp(&source_scene,&old_scene,sizeof old_scene));
            assert(!memcmp(&source_spu,&old_spu,sizeof old_spu));
            assert(!memcmp(&source_rate,&old_rate,sizeof old_rate));
            vh_audio_output_ramp_arm(&source_ramp);
            vh_audio_output_ramp_arm(&oracle_ramp);
            ramp_due=1u;
        }
    }
    assert(ramp_exercised==4u);
    assert(switched && signalled>12u && silent>=4u);
    assert(stats.pages_submitted==BLOCKS &&
           stats.frames_submitted==returned_frames);
    assert(stats.submit_failures==failures &&
           stats.restart_attempts==failures-1u &&
           stats.recoveries==recovered_pages);
    assert(stats.resume_restarts==4u && stats.resume_failures==2u &&
           stats.resume_recoveries==3u);
    assert(dev.submissions==BLOCKS+failures);
    assert(dev.accepted==BLOCKS && dev.rolling_hash==reference_hash);
    assert(!vh_audio_output_stop_close(&ops));
    assert(!dev.opened && !dev.playing);
    puts("music director + 48k ramp + exact-page retry/resume: PASS (synthetic)");
    return 0;
}
