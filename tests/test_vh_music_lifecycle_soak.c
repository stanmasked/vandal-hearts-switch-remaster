/* 512-block HOME/sleep/scene-switch/reverb/shutdown audio owner soak.
 * This is a deterministic host simulation, NOT an audout hardware test.
 * Assets are synthesized in memory and freed after a serialized detach.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "vh_audio_output_recovery.h"
#include "vh_audio_output_ramp.h"
#include "vh_audio_output_edges.h"
#include "vh_audio_diag_journal.h"
#include "vh_audio_resample.h"
#include "vh_game_music_mailbox.h"
#include "vh_music_scene.h"

#define SEQ_HDR 'p','Q','E','S',0,0,0,0,1,0xe0,7,0xa1,0x20,0,0
#define BLOCKS 512u
#define SLEEP_INTERVAL 8u
static const uint8_t field_seq[]={
    SEQ_HDR,0,0xc0,7,0,0x90,60,110,0x81,0x70,0x80,60,0,
    0x81,0x70,0xff,0x2f
};
static const uint8_t selected_seq[]={
    SEQ_HDR,0,0xc0,7,0,0x90,67,110,0x81,0x70,0x80,67,0,
    0x81,0x70,0xff,0x2f
};
static int16_t *owned_sample;

static int synth(void *unused, unsigned program, unsigned note,
                 unsigned velocity, unsigned volume, unsigned pan,
                 VhSeqTone *tone) {
    (void)unused; (void)pan;
    if (!owned_sample || !tone || program!=7u ||
        (note!=60u && note!=67u)) return -1;
    memset(tone,0,sizeof *tone);
    tone->pcm=owned_sample;
    tone->frames=128u;
    tone->loop_start=0;
    tone->loop_end=128;
    tone->pitch_step=note==60u ? 4096u : 6144u;
    tone->adsr1=15u;
    tone->reverb_send=1;
    tone->gain_left=.4f*(float)velocity/127.f;
    tone->gain_right=.35f*(float)volume/127.f;
    return 0;
}
static const VhMusicCue field_cue={
    VH_GAME_MUSIC_FIELD,field_seq,sizeof field_seq,0,synth,NULL
};
static const VhMusicCue selected_cue={
    VH_GAME_MUSIC_HERO_SELECTED,selected_seq,
    sizeof selected_seq,0,synth,NULL
};

typedef struct {
    int opened, playing;
    unsigned submit_fails_left, start_fails_left;
    unsigned starts, stops, closes, opens, submits;
    unsigned page_attempts, accepted_pages;
    const int16_t *page_pointer;
    size_t page_frames;
    uint64_t fingerprint, accepted_digest;
} FakeAudout;
typedef struct {
    VhNativeSpu spu;
    VhMusicScene scene;
    VhAudioResample resampler;
    VhGameMusicMailbox mailbox;
    VhAudioOutputRecovery recovery;
    VhAudioDiagJournal journal;
    VhAudioDiagnostics telemetry;
    VhAudioOutputRamp ramp;
    FakeAudout backend;
    unsigned handled_serial, accepted_scene;
    uint64_t output_frames;
    int16_t input[VH_AUDIO_BLOCK_FRAMES*2u];
    int16_t output[VH_AUDIO_RESAMPLE_MAX_FRAMES*2u];
    size_t output_count;
} MusicOwner;
static MusicOwner owner[2];
static VhNativeSpu paused_spu[2];
static VhMusicScene paused_scene[2];
static VhAudioResample paused_resampler[2];

static uint64_t fingerprint(const int16_t *pcm, size_t frames) {
    uint64_t v=UINT64_C(1469598103934665603);
    for(size_t i=0;i<frames*2u;i++) {
        v ^= (uint16_t)pcm[i];
        v *= UINT64_C(1099511628211);
    }
    return v;
}
static int do_submit(void *raw,const int16_t *pcm,size_t frames) {
    FakeAudout *d=raw;
    assert(d->opened && d->playing && frames>0u);
    uint64_t hash=fingerprint(pcm,frames);
    if(!d->page_attempts) {
        d->page_pointer=pcm;
        d->page_frames=frames;
        d->fingerprint=hash;
    } else {
        assert(d->page_pointer==pcm && d->page_frames==frames);
        assert(d->fingerprint==hash);
    }
    ++d->page_attempts;
    ++d->submits;
    if(d->submit_fails_left) {
        --d->submit_fails_left;
        return -1;
    }
    d->accepted_digest ^= hash;
    d->accepted_digest *= UINT64_C(1099511628211);
    ++d->accepted_pages;
    return 0;
}
static int do_stop(void *raw) {
    FakeAudout *d=raw;
    ++d->stops;
    d->playing=0;
    return 0;
}
static void do_close(void *raw) {
    FakeAudout *d=raw;
    if(d->opened) ++d->closes;
    d->opened=0;
    d->playing=0;
}
static int do_open(void *raw) {
    FakeAudout *d=raw;
    assert(!d->opened);
    ++d->opens;
    d->opened=1;
    return 0;
}
static int do_start(void *raw) {
    FakeAudout *d=raw;
    assert(d->opened && !d->playing);
    ++d->starts;
    if(d->start_fails_left) {
        --d->start_fails_left;
        return -1;
    }
    d->playing=1;
    return 0;
}
static VhAudioOutputOps ops_for(FakeAudout *d) {
    VhAudioOutputOps x={d,do_submit,do_stop,do_close,do_open,do_start};
    return x;
}
static void init_owner(MusicOwner *o) {
    memset(o,0,sizeof *o);
    vh_native_spu_reset(&o->spu);
    assert(vh_native_spu_set_interpolation(&o->spu,VH_SPU_GAUSSIAN)==0);
    assert(vh_native_spu_set_reverb(&o->spu,1,.5f)==0);
    vh_music_scene_init(&o->scene,&o->spu);
    vh_audio_resample_reset(&o->resampler);
    vh_game_music_mailbox_init(&o->mailbox,VH_GAME_MUSIC_FIELD);
    o->backend.opened=1;
    o->backend.playing=1;
    o->backend.accepted_digest=UINT64_C(1469598103934665603);
}
static void audio_turn(MusicOwner *o,unsigned injected_faults) {
    assert(vh_game_music_mailbox_running(&o->mailbox));
    assert(vh_game_music_mailbox_focused(&o->mailbox));
    assert(o->backend.opened && o->backend.playing);
    const unsigned desired=vh_game_music_mailbox_read(&o->mailbox);
    if(desired!=o->accepted_scene) {
        const VhMusicCue *cue=desired==VH_GAME_MUSIC_FIELD
            ? &field_cue :
            desired==VH_GAME_MUSIC_HERO_SELECTED ? &selected_cue : NULL;
        const int rc=vh_music_scene_request(&o->scene,cue,
                                            o->accepted_scene ? 4u : 0u);
        assert(rc==0 || rc==-2);
        if(rc==0) o->accepted_scene=desired;
    }
    assert(vh_music_scene_render(&o->scene,o->input)==0);
    o->output_count=vh_audio_resample_process(
        &o->resampler,o->input,VH_AUDIO_BLOCK_FRAMES,
        o->output,VH_AUDIO_RESAMPLE_MAX_FRAMES);
    assert(o->output_count>=555u && o->output_count<=559u);
    assert(!vh_audio_output_ramp_apply(
        &o->ramp,o->output,o->output_count));
    assert(o->ramp.position==VH_AUDIO_OUTPUT_RAMP_FRAMES);
    /* Apply once to the newly produced page. A failed output
     * submission retries these exact bytes, not another fade. */
    o->backend.page_attempts=0;
    o->backend.submit_fails_left=injected_faults;
    VhAudioOutputOps ops=ops_for(&o->backend);
    assert(vh_audio_output_submit_recover(
        &ops,&o->recovery,o->output,o->output_count)==0);
    o->output_frames+=o->output_count;
}
/* Publish the SAME numeric counters that the native audio owner
 * exposes to the on-console HUD. This host fixture deliberately
 * synthesizes completion time, not physical libnx/hardware latency.
 * Snapshots are collected by the game-side journal after PCM or
 * applet state transitions, never during the PCM submission callback.
 */
static void journal_sample(MusicOwner *o,uint64_t elapsed_ms,int status) {
    VhAudioDiagnostics *d=&o->telemetry;
    const VhAudioOutputRecovery *r=&o->recovery;
    d->status=status;
    d->pages_submitted=r->pages_submitted;
    d->frames_submitted=r->frames_submitted;
    d->submit_failures=r->submit_failures;
    d->restart_attempts=r->restart_attempts;
    d->recoveries=r->recoveries;
    d->resume_failures=r->resume_failures;
    d->resume_restarts=r->resume_restarts;
    d->resume_recoveries=r->resume_recoveries;
    assert(vh_audio_diag_journal_sample(&o->journal,elapsed_ms,d)>=0);
}

static void assert_frozen(const MusicOwner *o,unsigned which) {
    assert(!memcmp(&o->spu,&paused_spu[which],sizeof o->spu));
    assert(!memcmp(&o->scene,&paused_scene[which],sizeof o->scene));
    assert(!memcmp(&o->resampler,&paused_resampler[which],
                   sizeof o->resampler));
}
static void stress(const char *csv_prefix) {
    owned_sample=malloc(128u*sizeof *owned_sample);
    assert(owned_sample);
    for(unsigned i=0;i<128u;i++)
        owned_sample[i]=(int16_t)((int)i*137-8000);
    init_owner(&owner[0]);
    init_owner(&owner[1]);
    journal_sample(&owner[0],0u,1);
    journal_sample(&owner[1],0u,1);
    unsigned sleep_events=0, resume_start_faults=0, submit_faults=0;
    unsigned fade_blocks_seen=0, wet_reverb_seen=0;
    for(unsigned block=0;block<BLOCKS;block++) {
        if(block && block%SLEEP_INTERVAL==0u) {
            ++sleep_events;
            const int home_serial=(sleep_events%2u)==0u;
            const unsigned requested=(sleep_events%3u)==0u
                ? VH_GAME_MUSIC_HERO_SELECTED : VH_GAME_MUSIC_FIELD;
            for(unsigned i=0;i<2u;i++) {
                MusicOwner *o=&owner[i];
                vh_game_music_mailbox_set_focus(&o->mailbox,0);
                assert(do_stop(&o->backend)==0);
                journal_sample(o,(uint64_t)block*12u-1u,2);
                memcpy(&paused_spu[i],&o->spu,sizeof o->spu);
                memcpy(&paused_scene[i],&o->scene,sizeof o->scene);
                memcpy(&paused_resampler[i],&o->resampler,
                       sizeof o->resampler);
            }
            for(unsigned paused=0;paused<23u;paused++) {
                for(unsigned i=0;i<2u;i++) {
                    MusicOwner *o=&owner[i];
                    vh_game_music_mailbox_post(&o->mailbox,
                        paused==22u ? requested :
                        (paused%2u ? VH_GAME_MUSIC_FIELD :
                         VH_GAME_MUSIC_HERO_SELECTED));
                    assert(!vh_game_music_mailbox_focused(&o->mailbox));
                    assert_frozen(o,i);
                    assert(!o->backend.playing);
                }
            }
            for(unsigned i=0;i<2u;i++) {
                MusicOwner *o=&owner[i];
                if(home_serial)
                    vh_game_music_mailbox_on_resume(&o->mailbox,1);
                else
                    vh_game_music_mailbox_set_focus(&o->mailbox,1);
                const unsigned serial=vh_game_music_mailbox_resume_serial(
                    &o->mailbox);
                const int force_reopen=serial!=o->handled_serial;
                if(force_reopen) {
                    o->handled_serial=serial;
                    ++o->telemetry.resume_events;
                }
                if(i==1u && sleep_events%5u==0u) {
                    ++resume_start_faults;
                    o->backend.start_fails_left=1u;
                }
                VhAudioOutputOps ops=ops_for(&o->backend);
                assert(vh_audio_output_resume_recover(
                    &ops,&o->recovery,force_reopen)==0);
                assert(o->backend.opened && o->backend.playing);
                assert_frozen(o,i);
                /* One fake completed-buffer acknowledgement per
                 * successful start; no real console clock is read. */
                ++o->telemetry.confirmed_resumes;
                o->telemetry.last_confirmed_us=12000u;
                if (o->telemetry.last_confirmed_us>
                    o->telemetry.worst_confirmed_us)
                    o->telemetry.worst_confirmed_us=
                        o->telemetry.last_confirmed_us;
                journal_sample(o,(uint64_t)block*12u,1);
                vh_audio_output_ramp_arm(&o->ramp);
                assert(o->ramp.position==0u);
            }
        }
        const unsigned faults=block%37u==7u ? 2u :
                              block%13u==3u ? 1u : 0u;
        if(faults) submit_faults+=faults;
        audio_turn(&owner[0],0);
        audio_turn(&owner[1],faults);
        journal_sample(&owner[0],(uint64_t)(block+1u)*12u,1);
        journal_sample(&owner[1],(uint64_t)(block+1u)*12u,1);
        assert(owner[0].accepted_scene==owner[1].accepted_scene);
        assert(owner[0].scene.active.id==owner[1].scene.active.id);
        assert(owner[0].scene.stage==owner[1].scene.stage);
        assert(owner[0].scene.fade_position==owner[1].scene.fade_position);
        assert(owner[0].scene.seq.note_ons==owner[1].scene.seq.note_ons);
        assert(owner[0].scene.seq.cycles_completed==
               owner[1].scene.seq.cycles_completed);
        assert(owner[0].spu.frames_rendered==owner[1].spu.frames_rendered);
        assert(owner[0].spu.reverb.cursor==owner[1].spu.reverb.cursor);
        assert(!memcmp(owner[0].spu.reverb.work,
                       owner[1].spu.reverb.work,
                       sizeof owner[0].spu.reverb.work));
        assert(owner[0].resampler.next_output_tick==
               owner[1].resampler.next_output_tick);
        assert(owner[0].output_count==owner[1].output_count);
        assert(owner[0].ramp.position==owner[1].ramp.position);
        assert(!memcmp(owner[0].output,owner[1].output,
                       owner[0].output_count*2u*sizeof(int16_t)));
        assert(owner[0].backend.accepted_digest==
               owner[1].backend.accepted_digest);
        assert(owner[0].scene.blocks_rendered==block+1u);
        if(owner[0].scene.stage==VH_MUSIC_FADE_OUT ||
           owner[0].scene.stage==VH_MUSIC_FADE_IN ||
           owner[0].scene.stage==VH_MUSIC_SWITCH_PENDING)
            ++fade_blocks_seen;
        if(block%8u==0u) {
            for(size_t j=0;j<VH_REV_SAMPLES;j++) {
                if(owner[0].spu.reverb.work[j]!=0) {
                    ++wet_reverb_seen;
                    break;
                }
            }
        }
    }
    assert(fade_blocks_seen>0u && wet_reverb_seen>0u);
    assert(owner[0].scene.switches>4u);
    assert(owner[0].scene.switches==owner[1].scene.switches);
    assert(sleep_events==(BLOCKS-1u)/SLEEP_INTERVAL);
    assert(resume_start_faults>0 && submit_faults>0);
    assert(owner[1].recovery.submit_failures==submit_faults);
    assert(owner[1].recovery.resume_failures==resume_start_faults);
    assert(owner[0].recovery.submit_failures==0);
    assert(owner[0].backend.accepted_pages==BLOCKS &&
           owner[1].backend.accepted_pages==BLOCKS);
    assert(owner[0].output_frames==owner[1].output_frames);
    const uint64_t finished_clock=owner[0].resampler.input_frames;
    assert(finished_clock==(uint64_t)BLOCKS*512u);
    /* Cooperative exit: a 96-frame PCM fade to digital zero uses
     * only the most recently confirmed output sample. Unlike a new
     * SEQ block, this must not touch SPU voices, the reverb buffer,
     * the scene position or the resampler time. The HOME/focus-loss
     * path deliberately skips output of this tail. */
    int16_t stop_tail[2][VH_AUDIO_STOP_TAIL_FRAMES*2u];
    const uint64_t final_44k[2]={
        owner[0].resampler.input_frames,owner[1].resampler.input_frames
    };
    const uint64_t final_rendered[2]={
        owner[0].scene.blocks_rendered,owner[1].scene.blocks_rendered
    };
    for(unsigned i=0;i<2u;i++) {
        MusicOwner *o=&owner[i];
        const size_t count=o->output_count;
        assert(count>0u);
        assert(!vh_audio_stop_tail_build(stop_tail[i],
            VH_AUDIO_STOP_TAIL_FRAMES,
            o->output[2u*count-2u],o->output[2u*count-1u]));
        assert(stop_tail[i][0]==o->output[2u*count-2u]);
        assert(stop_tail[i][1]==o->output[2u*count-1u]);
        assert(stop_tail[i][(VH_AUDIO_STOP_TAIL_FRAMES-1u)*2u]==0);
        assert(stop_tail[i][(VH_AUDIO_STOP_TAIL_FRAMES-1u)*2u+1u]==0);
        assert(o->resampler.input_frames==final_44k[i]);
        assert(o->scene.blocks_rendered==final_rendered[i]);
    }
    assert(!memcmp(stop_tail[0],stop_tail[1],sizeof stop_tail[0]));
    /* Every captured row must come from actual host audio-owner
     * counters; no handcrafted CSV fixtures in this integration test.
     * A 512-page soak cannot satisfy the 1000-page comparison gate:
     * cross-version tooling MUST return INCONCLUSIVE. */
    for(unsigned i=0;i<2u;i++) {
        MusicOwner *o=&owner[i];
        assert(o->journal.count>0u);
        assert(o->journal.count<=VH_AUDIO_DIAG_JOURNAL_CAPACITY);
        assert(o->journal.total>=o->journal.count);
        assert(o->telemetry.pages_submitted==BLOCKS);
        assert(o->telemetry.frames_submitted==owner[0].output_frames);
        assert(o->telemetry.resume_events==sleep_events/2u);
        assert(o->telemetry.confirmed_resumes==sleep_events);
        assert(o->telemetry.resume_restarts==o->recovery.resume_restarts);
        assert(o->telemetry.resume_failures==o->recovery.resume_failures);
    }
    assert(owner[0].telemetry.submit_failures==0u);
    assert(owner[1].telemetry.submit_failures==submit_faults);
    for(unsigned i=0;i<2u;i++) {
        MusicOwner *o=&owner[i];
        vh_game_music_mailbox_stop(&o->mailbox);
        assert(!vh_game_music_mailbox_running(&o->mailbox));
        assert(do_stop(&o->backend)==0);
        do_close(&o->backend);
        assert(vh_music_scene_detach(&o->scene)==0);
        assert(o->scene.seq.bytes==NULL && o->scene.active.context==NULL);
        assert(o->scene.pending.context==NULL);
        assert(o->scene.stage==VH_MUSIC_SILENT);
        assert(o->spu.interpolation==VH_SPU_GAUSSIAN);
        assert(o->spu.reverb_enabled && o->spu.reverb_depth==.5f);
        for(unsigned v=0;v<VH_NATIVE_MUSIC_VOICES;v++) {
            assert(!o->spu.voice[v].active);
            assert(o->spu.voice[v].pcm==NULL);
        }
        for(size_t j=0;j<VH_REV_SAMPLES;j++)
            assert(o->spu.reverb.work[j]==0);
    }
    /* Optional host-only CSV export, strictly AFTER both audio
     * devices are closed and music contexts detached. Unchanged
     * default invocation writes no files. */
    for(unsigned i=0;i<2u;i++) {
        MusicOwner *o=&owner[i];
        o->telemetry.status=0;
        assert(vh_audio_diag_journal_finish(
            &o->journal,(uint64_t)BLOCKS*12u+1u,
            &o->telemetry)==1);
        if(csv_prefix) {
            char path[512];
            const int n=snprintf(path,sizeof path,"%s-%s.csv",csv_prefix,
                                 i==0 ? "clean":"fault");
            assert(n>0 && (size_t)n<sizeof path);
            FILE *file=fopen(path,"wb");
            assert(file);
            assert(vh_audio_diag_journal_write_csv(&o->journal,file)==
                   (int)o->journal.count);
            assert(fclose(file)==0);
        }
    }
    free(owned_sample);
    owned_sample=NULL;
    for(unsigned i=0;i<2u;i++) {
        memset(owner[i].input,0x7f,sizeof owner[i].input);
        assert(vh_music_scene_render(&owner[i].scene,owner[i].input)==0);
        for(size_t j=0;j<VH_AUDIO_BLOCK_FRAMES*2u;j++)
            assert(owner[i].input[j]==0);
        assert(vh_music_scene_detach(&owner[i].scene)==0);
    }
    printf("HOME/sleep + scene + reverb soak: %u blocks, "
           "%u pauses, %u resume start faults, %u PCM retries PASS\n",
           BLOCKS,sleep_events,resume_start_faults,submit_faults);
}
int main(int argc,char **argv) {
    /* Optional out-of-game reference artifacts for the Python
     * analyzer and cohort comparator. Never activated on Switch. */
    if(argc==1) stress(NULL);
    else if(argc==3 && strcmp(argv[1],"--csv-prefix")==0)
        stress(argv[2]);
    else {
        fputs("usage: test_vh_music_lifecycle_soak "
              "[--csv-prefix path-prefix]\\n",stderr);
        return 2;
    }
    return 0;
}
