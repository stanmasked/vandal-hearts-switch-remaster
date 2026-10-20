/* Stage354: 6144 deterministic host-only PCM pages through production
 * Stage353 decisions and unchanged Stage347 software lease semantics.
 * Synthetic service outcomes, NOT observed hardware or NeXium failures.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_exit_tail_checks_stage353.h"
#define PAGES 2048u
#define SAMPLES 256u
static uint64_t hash_pcm(const int16_t *p) {
    uint64_t h=UINT64_C(1469598103934665603);
    for(unsigned i=0;i<SAMPLES;i++) {
        h^=(uint16_t)p[i];
        h*=UINT64_C(1099511628211);
    }
    return h;
}
static void fill_pcm(int16_t *pcm,unsigned page) {
    for(unsigned i=0;i<SAMPLES;i++) {
        uint32_t x=page*UINT32_C(2654435761)+i*UINT32_C(2246822519);
        pcm[i]=(int16_t)(uint16_t)((x>>11)^x);
    }
}
static void check_csv(const VhAudioExitTailReason *reason,
                      const VhAudioExitOutputWitness *witness,
                      const VhAudioBufferLease *lease,uint64_t accepted,
                      unsigned expected_code) {
    VhAudioDiagnostics s={0};
    s.lease_pages_acquired=lease->pages_leased;
    s.lease_pages_released=lease->pages_released;
    s.abandoned_sessions=lease->abandoned_sessions;
    s.pages_submitted=accepted;
    FILE *f=tmpfile();
    assert(f);
    assert(vh_audio_tail_reason_write_csv(reason,witness,&s,f)==8);
    rewind(f);
    char line[96];
    assert(fgets(line,sizeof line,f) && !strcmp(line,"scope,value\n"));
    assert(fgets(line,sizeof line,f) &&
           !strcmp(line,"software_exit_tail_reason_only,1\n"));
    char expected[96];
    assert(fgets(line,sizeof line,f));
    assert(snprintf(expected,sizeof expected,"tail_reason_code,%u\n",
                    expected_code)>0);
    assert(!strcmp(line,expected));
    assert(fgets(line,sizeof line,f) && !strcmp(line,"tail_attempted,1\n"));
    assert(fgets(line,sizeof line,f));
    assert(snprintf(expected,sizeof expected,
                    "tail_descriptor_return_confirmed,%u\n",
                    (unsigned)(expected_code==VH_TAIL_RETURN_CONFIRMED))>0);
    assert(!strcmp(line,expected));
    assert(fgets(line,sizeof line,f) && !strcmp(line,"tail_lease_acquired,1\n"));
    assert(fgets(line,sizeof line,f));
    assert(snprintf(expected,sizeof expected,"lease_pages_acquired,%llu\n",
                    (unsigned long long)lease->pages_leased)>0);
    assert(!strcmp(line,expected));
    assert(fgets(line,sizeof line,f));
    assert(snprintf(expected,sizeof expected,"lease_pages_released,%llu\n",
                    (unsigned long long)lease->pages_released)>0);
    assert(!strcmp(line,expected));
    assert(fgets(line,sizeof line,f));
    assert(snprintf(expected,sizeof expected,"abandoned_sessions,%u\n",
                    lease->abandoned_sessions)>0);
    assert(!strcmp(line,expected));
    assert(fgetc(f)==EOF && !ferror(f));
    fclose(f);
}
static void stress(unsigned phase) {
    static int16_t pcm[SAMPLES];
    static int exact_token=0,foreign_token=0;
    VhAudioBufferLease lease={0};
    unsigned failures=0,successes=0,hits[7]={0};
    for(unsigned page=0;page<PAGES;page++) {
        assert(!lease.in_flight);
        fill_pcm(pcm,page+phase*PAGES);
        const uint64_t digest=hash_pcm(pcm);
        assert(!vh_audio_buffer_lease_begin(&lease,&exact_token));
        assert(lease.in_flight==&exact_token);
        VhAudioExitTailReason reason={0};
        VhAudioExitOutputWitness witness={0};
        vh_audio_tail_reason_reset(&reason);
        vh_audio_exit_output_reset(&witness);
        const unsigned kind=(page*5u+phase)%7u;
        ++hits[kind];
        int result=0;
        if(kind==0u) {
            result=vh_audio_tail_stage353_append_checked(&reason,1);
            assert(result==-1);
            assert(vh_audio_tail_reason_read(&reason)==VH_TAIL_APPEND_FAILED);
        } else {
            assert(!vh_audio_tail_stage353_append_checked(&reason,0));
            switch(kind) {
            case 1u:
                result=vh_audio_tail_stage353_wait_checked(
                    &reason,&lease,1,1u,&exact_token);
                assert(vh_audio_tail_reason_read(&reason)==VH_TAIL_WAIT_FAILED);
                break;
            case 2u:
                result=vh_audio_tail_stage353_wait_checked(
                    &reason,&lease,0,0u,&exact_token);
                assert(vh_audio_tail_reason_read(&reason)==VH_TAIL_WAIT_EMPTY);
                break;
            case 3u:
                result=vh_audio_tail_stage353_wait_checked(
                    &reason,&lease,0,1u,&foreign_token);
                assert(vh_audio_tail_reason_read(&reason)==VH_TAIL_RELEASE_MISMATCH);
                break;
            case 4u:
                result=vh_audio_tail_stage353_wait_checked(
                    &reason,&lease,0,1u,NULL);
                assert(vh_audio_tail_reason_read(&reason)==VH_TAIL_RELEASE_MISMATCH);
                break;
            case 5u:
                result=vh_audio_tail_stage353_wait_checked(
                    &reason,&lease,0,1u,&exact_token);
                break;
            default:
                result=vh_audio_tail_stage353_wait_checked(
                    &reason,&lease,0,2u,&exact_token);
                break;
            }
        }
        assert(hash_pcm(pcm)==digest);
        if(result) {
            ++failures;
            assert(lease.in_flight==&exact_token);
            assert(lease.pages_released==successes);
            assert(vh_audio_buffer_lease_begin(&lease,&foreign_token)==-1);
            /* Stop alone cannot grant PCM write ownership; only exit. */
            vh_audio_buffer_lease_session_closed(&lease);
            assert(!lease.in_flight && lease.abandoned_sessions==failures);
        } else {
            ++successes;
            assert(vh_audio_tail_reason_read(&reason)==VH_TAIL_RETURN_CONFIRMED);
            assert(!lease.in_flight);
            vh_audio_buffer_lease_session_closed(&lease);
        }
        assert(vh_audio_exit_output_tail(&witness,100u+page*10u,
                                         101u+page*10u,result==0)==1);
        assert(lease.pages_leased==page+1u);
        assert(lease.pages_released==successes);
        assert(lease.abandoned_sessions==failures);
        assert(lease.pages_leased==lease.pages_released+
               (uint64_t)lease.abandoned_sessions);
        check_csv(&reason,&witness,&lease,successes,
                  vh_audio_tail_reason_read(&reason));
        assert(hash_pcm(pcm)==digest);
    }
    assert(successes+failures==PAGES);
    assert(successes && failures);
    for(unsigned i=0;i<7u;i++) assert(hits[i]>0);
}
int main(void) {
    stress(0u);
    stress(3u);
    stress(6u);
    puts("Stage354: 6144 synthetic PCM pages, seven return categories, exact leases and CSV PASS");
    return 0;
}
