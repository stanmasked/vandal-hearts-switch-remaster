/* Decoded synthetic PS1-format VH/VB + pQES -> SPU/STUDIO_C ->
 * 48-kHz PCM -> exactly-once audout mock and A/B/DSP page telemetry.
 * No copyrighted content, physical audio service or PCM export.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_native_vab.h"
#include "vh_audio_resample.h"
#include "vh_audio_page_telemetry.h"
#include "vh_audio_report_pages.h"

#define VH_SIZE (32u+128u*16u+512u+512u)
/* Twelve alternating banks: eleven actual scene boundaries, including
 * recovery of one or two failed backend submissions on boundary pages. */
#define SCENES 12u
#define BLOCKS 8u
#define TOTAL (SCENES*BLOCKS)
#define HZ UINT64_C(19200000)
#define INIT_HASH UINT64_C(1469598103934665603)
#define HASH_MUL UINT64_C(1099511628211)

static uint8_t vh[2][VH_SIZE], vb[2][48];
static int16_t bank_pcm[2][56];
static VhNativeVab bank[2];
static VhNativeSeq seq;
static VhNativeSpu spu;
static VhAudioResample resampler;
/* The dry-service reference uses its OWN sequencer, mixer, wet-tail
 * history and long-lived resampler. Only the read-only decoded VH/VB
 * sample banks are shared; no audout callbacks touch this pipeline.
 * This is a differential SERVICE-ISOLATION reference, not an
 * independently implemented PS1 audio decoder. */
static VhNativeSeq oracle_seq;
static VhNativeSpu oracle_spu;
static VhAudioResample oracle_resampler;
static int16_t src[VH_AUDIO_BLOCK_FRAMES*2u];
static int16_t dst[VH_AUDIO_RESAMPLE_MAX_FRAMES*2u];
static int16_t oracle_src[VH_AUDIO_BLOCK_FRAMES*2u];
static int16_t oracle_dst[VH_AUDIO_RESAMPLE_MAX_FRAMES*2u];
static const uint8_t song[]={
    'p','Q','E','S',0,0,0,0,1,0xe0,7,0xa1,0x20,0,0,
    0,0xc0,7,0,0x90,60,110,0x81,0x70,0x80,60,0,
    0x81,0x70,0xff,0x2f
};
static void make_bank(unsigned b) {
    uint8_t *h=vh[b],*v=vb[b];
    memcpy(h,"pBAV",4u);
    h[18]=8;h[20]=1;h[22]=1;h[24]=127;
    const size_t p=32u+7u*16u;
    h[p]=1;h[p+1]=127;h[p+4]=64;
    const size_t t=32u+128u*16u;
    h[t+1]=4; /* Real tone send to STUDIO_C wet processing. */
    h[t+2]=127;h[t+3]=64;h[t+4]=60;
    h[t+6]=40;h[t+7]=100;h[t+16]=15;
    h[t+20]=7;h[t+22]=1;
    h[t+512]=2;h[t+514]=4;
    v[16]=2;v[17]=4;
    memset(v+18,b ? 0x44 : 0x22,14u);
    v[32]=2;v[33]=3;
    memset(v+34,b ? 0xdd : 0xee,14u);
    assert(vh_native_vab_load(
        &bank[b],h,VH_SIZE,v,48u,bank_pcm[b],56u)==0);
}
static uint64_t hash_pcm(const int16_t *pcm,size_t frames) {
    uint64_t h=INIT_HASH;
    for(size_t i=0;i<frames*2u;i++) {
        h^=(uint16_t)pcm[i];
        h*=HASH_MUL;
    }
    return h;
}
typedef struct {
    unsigned open,playing;
    unsigned tries_this_page,failures_left;
    uint64_t submitted,accepted,returned_hash;
    const int16_t *page_addr;
    size_t page_frames;
    uint64_t page_hash;
    VhAudioSubmitTiming timing;
} SimOut;
static void new_page(SimOut *d,unsigned fails) {
    d->tries_this_page=0u;
    d->failures_left=fails;
    d->page_addr=NULL;
    d->page_frames=0u;
    d->page_hash=0u;
}
static int submit(void *ctx,const int16_t *pcm,size_t frames) {
    SimOut *d=ctx;
    assert(d->open && d->playing && pcm && frames>0u);
    const uint64_t h=hash_pcm(pcm,frames);
    if (!d->tries_this_page) {
        d->page_addr=pcm;d->page_frames=frames;d->page_hash=h;
    } else {
        assert(d->page_addr==pcm && d->page_frames==frames &&
               d->page_hash==h);
    }
    ++d->tries_this_page;
    ++d->submitted;
    unsigned fail=(unsigned)(d->failures_left!=0u);
    if(fail) --d->failures_left;
    const uint64_t nominal=(uint64_t)frames*HZ/48000u;
    const uint64_t ticks=d->submitted%4u==0u
        ? nominal*3u : d->submitted%3u==0u
        ? nominal+nominal/2u : nominal/2u;
    assert(vh_audio_output_record_submit_timing(
        &d->timing,ticks,HZ,frames,!fail)==0);
    if(fail) return -1;
    ++d->accepted;
    d->returned_hash=(d->returned_hash^h)*HASH_MUL;
    return 0;
}
static int stop(void *ctx) {
    SimOut *d=ctx;
    d->playing=0u;
    return 0;
}
static void close_out(void *ctx) {
    SimOut *d=ctx;
    assert(!d->playing);
    d->open=0u;
}
static int open_out(void *ctx) {
    SimOut *d=ctx;
    assert(!d->open);
    d->open=1u;
    return 0;
}
static int start(void *ctx) {
    SimOut *d=ctx;
    assert(d->open && !d->playing);
    d->playing=1u;
    return 0;
}
static void verify_returned(
    const VhAudioSceneWaits *waits,const VhAudioPcmSeams *seams,
    const VhAudioComputeWaitJoin *joint,
    const VhAudioListeningMarks *marks,uint64_t pages,
    uint64_t boundaries) {
    assert(vh_audio_output_verify_pcm_seams(seams,waits,pages)==0);
    assert(vh_audio_last_returned_page_verify(seams,marks,pages)==0);
    assert(vh_audio_listening_verify(marks,pages)==0);
    assert(joint->ordinary.returned==pages-boundaries &&
           joint->first_after_switch.returned==boundaries);
    assert(vh_audio_listening_verify_dsp_totals(
        marks,joint->ordinary.dsp_over+
                  joint->first_after_switch.dsp_over,
        joint->ordinary.both_over_2x+
                  joint->first_after_switch.both_over_2x,
        joint->ordinary.both_over_4x+
                  joint->first_after_switch.both_over_4x)==0);
}
int main(void) {
    make_bank(0u);make_bank(1u);
    assert(bank[0].samples[1].pcm!=bank[1].samples[1].pcm);
    VhSeqTone tone0={0},tone1={0};
    assert(vh_native_vab_resolve(&bank[0],7u,60u,110u,127u,64u,
                                 &tone0)==0);
    assert(vh_native_vab_resolve(&bank[1],7u,60u,110u,127u,64u,
                                 &tone1)==0);
    assert(tone0.reverb_send==1u && tone1.reverb_send==1u);
    assert(tone0.pcm!=tone1.pcm);
    assert(memcmp(bank_pcm[0],bank_pcm[1],sizeof bank_pcm[0])!=0);
    vh_native_spu_reset(&spu);
    assert(vh_native_spu_set_reverb(&spu,1,0.5f)==0);
    vh_audio_resample_reset(&resampler);
    assert(vh_native_seq_init(&seq,song,sizeof song,&spu,
                vh_native_vab_resolve,&bank[0],0)==0);
    vh_native_spu_reset(&oracle_spu);
    assert(vh_native_spu_set_reverb(&oracle_spu,1,0.5f)==0);
    vh_audio_resample_reset(&oracle_resampler);
    assert(vh_native_seq_init(&oracle_seq,song,sizeof song,
                &oracle_spu,vh_native_vab_resolve,&bank[0],0)==0);
    assert(&oracle_spu!=&spu && &oracle_resampler!=&resampler);
    SimOut d={.open=1u,.playing=1u,.returned_hash=INIT_HASH};
    const VhAudioOutputOps ops={
        .context=&d,.submit=submit,.stop=stop,
        .close=close_out,.open=open_out,.start=start
    };
    VhAudioOutputRecovery recovery={0};
    VhAudioSceneWaits waits={0};
    VhAudioPcmSeams seams={0};
    VhAudioComputeWaitJoin joint={0};
    VhAudioListeningMarks marks={0};
    uint64_t accepted_hash=INIT_HASH,output_frames=0u;
    uint64_t oracle_hash=INIT_HASH,oracle_frames=0u;
    uint64_t bank_hash[2]={0u,0u};
    uint64_t oracle_bank_hash[2]={0u,0u};
    unsigned oracle_boundary_checks=0u;
    uint32_t max_oracle_scene_seam=0u;
    int16_t oracle_last_l=0,oracle_last_r=0;
    uint64_t boundaries=0u,expected_failed_attempts=0u;
    assert(VH_AUDIO_OUTPUT_RESTART_LIMIT>=2u);

    for(unsigned page=0u;page<TOTAL;page++) {
        const unsigned scene=page/BLOCKS;
        const unsigned boundary=(unsigned)(page && page%BLOCKS==0u);
        if(boundary) {
            /* A real SEQ/VAB scene switch must occur only AFTER
             * the prior output page has returned. Stop+resume must
             * never itself submit another PCM page. */
            const VhAudioSubmitTiming saved_timing=d.timing;
            const VhAudioPcmSeams saved_seams=seams;
            const VhAudioComputeWaitJoin saved_joint=joint;
            const VhAudioListeningMarks saved_marks=marks;
            const uint64_t prior_calls=d.submitted;
            const uint64_t prior_hash=d.returned_hash;
            const uint64_t prior_resampled=resampler.input_frames;
            const int old_cursor=spu.reverb.cursor;
            const int16_t wet_tail=spu.reverb.work[0];
            const int oracle_cursor=oracle_spu.reverb.cursor;
            const int16_t oracle_tail=oracle_spu.reverb.work[0];
            const uint64_t oracle_input=oracle_resampler.input_frames;
            const uint64_t oracle_blocks=oracle_seq.blocks_advanced;
            assert(ops.stop(ops.context)==0);
            assert(vh_audio_output_resume_recover(
                &ops,&recovery,1)==0);
            assert(d.submitted==prior_calls && d.returned_hash==prior_hash);
            assert(!memcmp(&d.timing,&saved_timing,sizeof saved_timing));
            assert(!memcmp(&seams,&saved_seams,sizeof saved_seams));
            assert(!memcmp(&joint,&saved_joint,sizeof saved_joint));
            assert(!memcmp(&marks,&saved_marks,sizeof saved_marks));
            assert(resampler.input_frames==prior_resampled);
            assert(oracle_resampler.input_frames==oracle_input);
            assert(oracle_seq.blocks_advanced==oracle_blocks);
            assert(vh_native_seq_switch_scene(
                &seq,song,sizeof song,&spu,
                vh_native_vab_resolve,&bank[scene%2u],0)==0);
            /* No device callbacks are used by the dry oracle. A
             * second independent state machine switches the SAME
             * decoded bank and must preserve its wet reverb tail. */
            assert(vh_native_seq_switch_scene(
                &oracle_seq,song,sizeof song,&oracle_spu,
                vh_native_vab_resolve,&bank[scene%2u],0)==0);
            assert(oracle_spu.frames_rendered==0u);
            assert(oracle_spu.reverb.cursor==oracle_cursor);
            assert(oracle_spu.reverb.work[0]==oracle_tail);
            assert(spu.frames_rendered==0u);
            assert(spu.reverb.cursor==old_cursor);
            assert(spu.reverb.work[0]==wet_tail);
            for(unsigned voice=0u;voice<VH_NATIVE_MUSIC_VOICES;voice++)
                assert(!spu.voice[voice].active &&
                       !spu.voice[voice].pcm);
            ++boundaries;
        }
        assert(vh_native_seq_advance_block(&seq)>=0);
        assert(vh_native_seq_advance_block(&oracle_seq)>=0);
        assert(oracle_seq.note_ons==seq.note_ons);
        assert(oracle_seq.blocks_advanced==seq.blocks_advanced);
        if(page%BLOCKS==0u) {
            unsigned valid=0u;
            for(unsigned v=0u;v<VH_NATIVE_MUSIC_VOICES;v++) {
                if(spu.voice[v].pcm) {
                    assert(spu.voice[v].pcm==
                           bank[scene%2u].samples[1].pcm);
                    ++valid;
                }
            }
            assert(valid>0u);
            for(unsigned v=0u;v<VH_NATIVE_MUSIC_VOICES;v++)
                if(oracle_spu.voice[v].pcm)
                    assert(oracle_spu.voice[v].pcm==
                           bank[scene%2u].samples[1].pcm);
        }
        vh_native_spu_render(&spu,src,VH_AUDIO_BLOCK_FRAMES);
        vh_native_spu_render(&oracle_spu,oracle_src,
                             VH_AUDIO_BLOCK_FRAMES);
        assert(memcmp(src,oracle_src,sizeof src)==0);
        const size_t frames=vh_audio_resample_process(
            &resampler,src,VH_AUDIO_BLOCK_FRAMES,
            dst,VH_AUDIO_RESAMPLE_MAX_FRAMES);
        assert(frames>=555u && frames<=559u);
        const size_t reference_frames=vh_audio_resample_process(
            &oracle_resampler,oracle_src,VH_AUDIO_BLOCK_FRAMES,
            oracle_dst,VH_AUDIO_RESAMPLE_MAX_FRAMES);
        assert(reference_frames==frames);
        /* The acceptance/resend pipeline may not change a single
         * stereo output sample relative to a callback-free render. */
        assert(memcmp(dst,oracle_dst,frames*2u*sizeof(int16_t))==0);
        output_frames+=frames;
        oracle_frames+=reference_frames;
        const uint64_t hash=hash_pcm(dst,frames);
        const uint64_t ref_hash=hash_pcm(oracle_dst,reference_frames);
        assert(hash==ref_hash);
        oracle_hash=(oracle_hash^ref_hash)*HASH_MUL;
        oracle_bank_hash[scene%2u]+=ref_hash;
        if(boundary) {
            const int32_t dl=(int32_t)oracle_dst[0]-oracle_last_l;
            const int32_t dr=(int32_t)oracle_dst[1]-oracle_last_r;
            const uint32_t jump_l=(uint32_t)(dl<0?-dl:dl);
            const uint32_t jump_r=(uint32_t)(dr<0?-dr:dr);
            const uint32_t jump=jump_l>jump_r?jump_l:jump_r;
            assert(jump<=65535u);
            if(jump>max_oracle_scene_seam) max_oracle_scene_seam=jump;
            ++oracle_boundary_checks;
        }
        oracle_last_l=oracle_dst[2u*(reference_frames-1u)];
        oracle_last_r=oracle_dst[2u*(reference_frames-1u)+1u];
        const uint64_t old_input=resampler.input_frames;
        const uint64_t old_frames=spu.frames_rendered;
        const uint64_t old_notes=seq.note_ons;
        const VhAudioSubmitTiming before=d.timing;
        /* Each new bank gets a recoverable failure; every third
         * boundary consumes BOTH available restart attempts. One
         * ordinary page also retries. No retry may advance SEQ/SPU,
         * create a duplicate PCM page or shift resampler phase. */
        const unsigned fails=boundary
            ? 1u+(unsigned)(scene%3u==0u)
            : (unsigned)(page==5u);
        new_page(&d,fails);
        assert(vh_audio_output_submit_recover(
            &ops,&recovery,dst,frames)==0);
        expected_failed_attempts+=fails;
        assert(d.tries_this_page==1u+fails && d.page_hash==hash);
        assert(d.page_addr==dst && d.page_frames==frames);
        assert(d.submitted==page+1u+expected_failed_attempts);
        assert(d.accepted==page+1u);
        assert(recovery.submit_failures==expected_failed_attempts);
        assert(recovery.restart_attempts==expected_failed_attempts);
        assert(recovery.recoveries==boundaries+
               (unsigned)(page>=5u));
        assert(hash_pcm(dst,frames)==hash);
        assert(memcmp(dst,oracle_dst,frames*2u*sizeof(int16_t))==0);
        assert(resampler.input_frames==old_input &&
               spu.frames_rendered==old_frames &&
               seq.note_ons==old_notes);
        assert(vh_audio_returned_page_telemetry_record(
            &waits,&seams,&joint,&marks,dst,frames,boundary,
            &before,&d.timing,HZ,(unsigned)(page%7u==0u))==0);
        accepted_hash=(accepted_hash^hash)*HASH_MUL;
        bank_hash[scene%2u]+=hash;
        assert(d.returned_hash==accepted_hash);
        assert(d.returned_hash==oracle_hash);
        assert(recovery.pages_submitted==page+1u);
        assert(marks.recent[page%VH_LISTEN_RECENT_PAGES]
            .scene_boundary==boundary);
        /* The listening ring stores a boolean "retried" mark;
         * the exact number of failed attempts is independently
         * reconciled through d.submitted and recovery counters. */
        assert(marks.recent[page%VH_LISTEN_RECENT_PAGES]
            .retry==(unsigned)(fails!=0u));
        /* Boundary metadata is independently derived from the
         * callback-free 48-kHz sample stream, including wet tails. */
        if(boundary) assert(seams.last_abs_step<=65535u);
        verify_returned(&waits,&seams,&joint,&marks,page+1u,boundaries);
        assert(waits.first_after_switch.pages==boundaries);
        assert(vh_audio_output_verify_run(
            &waits,&recovery,&d.timing,page+1u,boundaries,
            TOTAL,BLOCKS,0)==0);
    }
    assert(boundaries==SCENES-1u && d.accepted==TOTAL);
    assert(expected_failed_attempts==15u);
    assert(recovery.resume_recoveries==boundaries &&
           recovery.resume_restarts==boundaries);
    assert(bank_hash[0]!=bank_hash[1]);
    assert(bank_hash[0]==oracle_bank_hash[0] &&
           bank_hash[1]==oracle_bank_hash[1]);
    assert(oracle_frames==output_frames);
    assert(oracle_hash==accepted_hash);
    assert(oracle_boundary_checks==SCENES-1u);
    assert(max_oracle_scene_seam<=65535u);
    assert(oracle_resampler.input_frames==resampler.input_frames);
    /* A controlled single-sample mutation must be detectable by
     * direct comparison and per-page fingerprint. Restore the
     * unaltered buffer before the terminal failure scenario. */
    const int16_t sample_before=oracle_dst[3];
    oracle_dst[3]=(int16_t)(sample_before^1);
    assert(oracle_dst[3]!=dst[3]);
    assert(memcmp(dst,oracle_dst,
                  2u*VH_AUDIO_RESAMPLE_MAX_FRAMES*
                  sizeof(int16_t))!=0);
    oracle_dst[3]=sample_before;
    assert(memcmp(dst,oracle_dst,
                  2u*VH_AUDIO_RESAMPLE_MAX_FRAMES*
                  sizeof(int16_t))==0);
    assert(recovery.recoveries==SCENES &&
           recovery.submit_failures==expected_failed_attempts);
    assert(d.submitted==TOTAL+expected_failed_attempts);
    assert(recovery.frames_submitted==output_frames);
    assert(resampler.input_frames==(uint64_t)TOTAL*VH_AUDIO_BLOCK_FRAMES);
    assert(vh_audio_output_verify_run(
        &waits,&recovery,&d.timing,TOTAL,boundaries,TOTAL,BLOCKS,1)==1);
    assert(vh_audio_report_evidence(1,0,0,0,0)==VH_AUDIO_REPORT_FULL);

    /* Final page was rendered but NEVER delivered. A failed audout
     * page has no seam, no DSP returned event and no A/B ring entry.
     * The scene switches and prior accepted samples remain intact. */
    assert(vh_native_seq_advance_block(&seq)>=0);
    assert(vh_native_seq_advance_block(&oracle_seq)>=0);
    vh_native_spu_render(&spu,src,VH_AUDIO_BLOCK_FRAMES);
    vh_native_spu_render(&oracle_spu,oracle_src,
                         VH_AUDIO_BLOCK_FRAMES);
    assert(memcmp(src,oracle_src,sizeof src)==0);
    const size_t lost_frames=vh_audio_resample_process(
        &resampler,src,VH_AUDIO_BLOCK_FRAMES,
        dst,VH_AUDIO_RESAMPLE_MAX_FRAMES);
    assert(lost_frames>=555u && lost_frames<=559u);
    const size_t lost_reference_frames=vh_audio_resample_process(
        &oracle_resampler,oracle_src,VH_AUDIO_BLOCK_FRAMES,
        oracle_dst,VH_AUDIO_RESAMPLE_MAX_FRAMES);
    assert(lost_reference_frames==lost_frames);
    assert(memcmp(dst,oracle_dst,
                  lost_frames*2u*sizeof(int16_t))==0);
    const uint64_t final_hash=hash_pcm(dst,lost_frames);
    const uint64_t oracle_hash_before_failure=oracle_hash;
    const VhAudioPcmSeams last_seams=seams;
    const VhAudioComputeWaitJoin last_joint=joint;
    const VhAudioListeningMarks last_marks=marks;
    const VhAudioSubmitTiming failed_before=d.timing;
    new_page(&d,VH_AUDIO_OUTPUT_RESTART_LIMIT+1u);
    assert(vh_audio_output_submit_recover(
        &ops,&recovery,dst,lost_frames)==-1);
    assert(d.tries_this_page==VH_AUDIO_OUTPUT_RESTART_LIMIT+1u);
    assert(vh_audio_output_record_scene_page(
        &waits,&failed_before,&d.timing,HZ,lost_frames,0,0)==0);
    assert(hash_pcm(dst,lost_frames)==final_hash);
    assert(d.accepted==TOTAL && d.returned_hash==accepted_hash);
    assert(oracle_hash==oracle_hash_before_failure);
    assert(recovery.pages_submitted==TOTAL);
    assert(!memcmp(&seams,&last_seams,sizeof seams));
    assert(!memcmp(&joint,&last_joint,sizeof joint));
    assert(!memcmp(&marks,&last_marks,sizeof marks));
    verify_returned(&waits,&seams,&joint,&marks,TOTAL,boundaries);
    assert(waits.ordinary.failed_pages==1u);
    assert(vh_audio_output_verify_run(
        &waits,&recovery,&d.timing,TOTAL,boundaries,
        TOTAL+1u,BLOCKS,0)==0);
    assert(vh_audio_report_evidence(0,0,0,0,0)==
           VH_AUDIO_REPORT_INCOMPLETE);
    assert(vh_audio_output_stop_close(&ops)==0);
    assert(!d.open && !d.playing);
    puts("decoded VH/VB SEQ audout scene transaction: PASS (12 scenes, 15 recovered submit faults)");
    return 0;
}
