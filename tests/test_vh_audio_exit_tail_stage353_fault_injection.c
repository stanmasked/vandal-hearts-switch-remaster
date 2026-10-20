/* Stage353: inject service outcomes into EXACT portable helpers used by
 * the production bounded exit-tail path. Pure C11/GCC/Clang/UBSan; this
 * simulates libnx return values and is not physical/Switch audio evidence.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_exit_tail_checks_stage353.h"

typedef struct {
    VhAudioBufferLease lease;
    VhAudioExitTailReason reason;
    int owned_descriptor;
    int foreign_descriptor;
    unsigned append_calls,wait_calls;
    uint64_t prior_page_hash;
} Harness;

static void initialize(Harness *h) {
    memset(h,0,sizeof(*h));
    vh_audio_tail_reason_reset(&h->reason);
    h->prior_page_hash=UINT64_C(0x77d3405a14e25b19);
}

static void submit_for_tail(Harness *h) {
    assert(!vh_audio_buffer_lease_begin(
        &h->lease,&h->owned_descriptor));
    assert(h->lease.in_flight==&h->owned_descriptor);
    assert(h->lease.pages_leased==1);
    assert(h->lease.pages_released==0);
}

static int mocked_append(Harness *h,int failed) {
    ++h->append_calls; /* exactly one original service call */
    return vh_audio_tail_stage353_append_checked(&h->reason,failed);
}

static int mocked_wait(Harness *h,int failed,unsigned count,const void *released) {
    ++h->wait_calls; /* exactly one original bounded service call */
    return vh_audio_tail_stage353_wait_checked(
        &h->reason,&h->lease,failed,count,released);
}

/* Reconcile each injected branch through the unmodified Stage351
 * post-join CSV writer, not merely an asserted enum value.
 * This is a host-only fake source and cannot replace original NeXium CSV.
 */
static void verify_after_join_csv(const Harness *h,unsigned code,int returned) {
    VhAudioExitOutputWitness witness={0};
    vh_audio_exit_output_reset(&witness);
    assert(vh_audio_exit_output_tail(&witness,100,110,returned)==1);
    VhAudioDiagnostics final={0};
    final.lease_pages_acquired=h->lease.pages_leased;
    final.lease_pages_released=h->lease.pages_released;
    final.abandoned_sessions=h->lease.abandoned_sessions;
    final.lease_mismatches=h->lease.mismatched_releases;
    final.lease_busy_begin_rejections=h->lease.busy_begin_rejections;
    final.pages_submitted=h->lease.pages_released;
    FILE *csv=tmpfile();
    assert(csv);
    assert(vh_audio_tail_reason_write_csv(
        &h->reason,&witness,&final,csv)==8);
    rewind(csv);
    const char *const names[]={
        "scope,value","software_exit_tail_reason_only,1",
        "tail_reason_code,","tail_attempted,1",
        "tail_descriptor_return_confirmed,","tail_lease_acquired,1",
        "lease_pages_acquired,","lease_pages_released,",
        "abandoned_sessions,"
    };
    char row[96];
    for(unsigned i=0;i<9u;i++) {
        assert(fgets(row,sizeof row,csv));
        if(i==2u) {
            unsigned parsed=999u;
            assert(sscanf(row,"tail_reason_code,%u",&parsed)==1);
            assert(parsed==code);
        }
        else if(i==4u) {
            unsigned parsed=999u;
            assert(sscanf(row,"tail_descriptor_return_confirmed,%u",
                          &parsed)==1 && parsed==(unsigned)returned);
        }
        else if(i>=6u) {
            assert(strncmp(row,names[i],strlen(names[i]))==0);
        }
        else {
            const size_t length=strlen(names[i]);
            assert(strncmp(row,names[i],length)==0);
        }
    }
    assert(fgetc(csv)==EOF && !ferror(csv));
    fclose(csv);
}

static void fail_closed(Harness *h,unsigned code) {
    assert(vh_audio_tail_reason_read(&h->reason)==code);
    assert(h->lease.in_flight==&h->owned_descriptor);
    assert(h->lease.pages_released==0);
    assert(h->prior_page_hash==UINT64_C(0x77d3405a14e25b19));
    /* A stopped service is not proof of released PCM ownership. */
    assert(vh_audio_buffer_lease_begin(
        &h->lease,&h->foreign_descriptor)==-1);
    assert(h->lease.busy_begin_rejections==1);
    /* The only lawful way to dispose an ambiguous PCM page is to
     * close/exit the entire old session before writing it again. */
    vh_audio_buffer_lease_session_closed(&h->lease);
    assert(!h->lease.in_flight);
    assert(h->lease.abandoned_sessions==1);
    assert(h->lease.pages_leased==1);
    assert(h->lease.pages_released==0);
    assert(!vh_audio_buffer_lease_begin(
        &h->lease,&h->owned_descriptor));
    assert(!vh_audio_buffer_lease_release(
        &h->lease,&h->owned_descriptor));
    assert(h->lease.pages_leased==2);
    assert(h->lease.pages_released==1);
    verify_after_join_csv(h,code,0);
}

static void test_append_failure_keeps_lease_and_skips_wait(void) {
    Harness h;initialize(&h);submit_for_tail(&h);
    assert(mocked_append(&h,1)==-1);
    assert(h.append_calls==1 && h.wait_calls==0);
    fail_closed(&h,VH_TAIL_APPEND_FAILED);
}

static void test_failed_wait_keeps_lease_even_if_pointer_returned(void) {
    Harness h;initialize(&h);submit_for_tail(&h);
    assert(!mocked_append(&h,0));
    assert(mocked_wait(&h,1,1,&h.owned_descriptor)==-1);
    assert(h.append_calls==1 && h.wait_calls==1);
    fail_closed(&h,VH_TAIL_WAIT_FAILED);
}

static void test_empty_wait_keeps_lease(void) {
    Harness h;initialize(&h);submit_for_tail(&h);
    assert(!mocked_append(&h,0));
    assert(mocked_wait(&h,0,0,&h.owned_descriptor)==-1);
    assert(h.append_calls==1 && h.wait_calls==1);
    fail_closed(&h,VH_TAIL_WAIT_EMPTY);
}

static void test_wrong_descriptor_keeps_lease(void) {
    Harness h;initialize(&h);submit_for_tail(&h);
    assert(!mocked_append(&h,0));
    assert(mocked_wait(&h,0,1,&h.foreign_descriptor)==-1);
    assert(h.lease.mismatched_releases==1);
    assert(h.append_calls==1 && h.wait_calls==1);
    fail_closed(&h,VH_TAIL_RELEASE_MISMATCH);
}

static void test_null_release_keeps_lease(void) {
    Harness h;initialize(&h);submit_for_tail(&h);
    assert(!mocked_append(&h,0));
    assert(mocked_wait(&h,0,1,NULL)==-1);
    assert(h.lease.mismatched_releases==1);
    fail_closed(&h,VH_TAIL_RELEASE_MISMATCH);
}

static void test_successful_exact_return_releases_lease(void) {
    Harness h;initialize(&h);submit_for_tail(&h);
    assert(!mocked_append(&h,0));
    assert(!mocked_wait(&h,0,1,&h.owned_descriptor));
    assert(h.append_calls==1 && h.wait_calls==1);
    assert(vh_audio_tail_reason_read(&h.reason)==VH_TAIL_RETURN_CONFIRMED);
    assert(!h.lease.in_flight);
    assert(h.lease.pages_leased==1 && h.lease.pages_released==1);
    vh_audio_buffer_lease_session_closed(&h.lease);
    assert(h.lease.abandoned_sessions==0);
    verify_after_join_csv(&h,VH_TAIL_RETURN_CONFIRMED,1);
}

static void test_multiple_count_still_checks_exact_descriptor(void) {
    Harness h;initialize(&h);submit_for_tail(&h);
    assert(!mocked_append(&h,0));
    assert(!mocked_wait(&h,0,2,&h.owned_descriptor));
    assert(!h.lease.in_flight);
    assert(h.lease.pages_released==1);
}

static void test_all_codes_are_distinct_and_stable(void) {
    assert(VH_TAIL_NOT_ATTEMPTED==0);
    assert(VH_TAIL_PRECONDITION_FAILED==1);
    assert(VH_TAIL_LEASE_BUSY==2);
    assert(VH_TAIL_APPEND_FAILED==3);
    assert(VH_TAIL_WAIT_FAILED==4);
    assert(VH_TAIL_WAIT_EMPTY==5);
    assert(VH_TAIL_RELEASE_MISMATCH==6);
    assert(VH_TAIL_RETURN_CONFIRMED==7);
}

int main(void) {
    test_all_codes_are_distinct_and_stable();
    test_append_failure_keeps_lease_and_skips_wait();
    test_failed_wait_keeps_lease_even_if_pointer_returned();
    test_empty_wait_keeps_lease();
    test_wrong_descriptor_keeps_lease();
    test_null_release_keeps_lease();
    test_successful_exact_return_releases_lease();
    test_multiple_count_still_checks_exact_descriptor();
    puts("Stage353 real shared tail decision logic, seven safe paths PASS");
    return 0;
}
