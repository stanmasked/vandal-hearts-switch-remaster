#include "vh81_event_jsonl.h"
#include "vh80_native_timeline.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>

int vh81_format_jsonl(char *output,size_t capacity) {
    unsigned int n=vh80_count(),prev=0,edges=0;
    size_t used=0;
    const vh80_event *events;
    if(!output || capacity==0)return -1;
    /* Clear prior longer JSONL, also for fail-closed export attempts. */
    memset(output,0,capacity);
    if(vh80_dropped()!=0 || n==0 || n>VH80_TOTAL_CAPACITY)return -1;
    events=vh80_events();
    for(unsigned int i=0;i<n;i++) {
        const vh80_event *e=&events[i];
        const char *kind;
        int written;
        if(e->sequence==0 || (i && (prev==UINT32_MAX || e->sequence!=prev+1))) return -1;
        prev=e->sequence;
        if(e->kind==VH80_VBLANK) { kind="vblank";edges++; }
        else if(e->kind==VH80_GP1_MMIO) kind="gp1_mmio";
        else if(e->kind==VH80_GPU_DMA2) kind="gpu_dma2_start";
        else if(e->kind==VH83_GP0_UNAI_HANDLED) kind="gp0_unai_handled";
        else if(e->kind==VH84_UNAI_SAMPLE_DELTA) kind="unai_sample_delta";
        else if(e->kind==VH85_UNAI_STORE_COUNT) kind="unai_store_count";
        else if(e->kind==VH85_UNAI_SAME_STORE_COUNT) kind="unai_same_store_count";
        else if(e->kind==VH86_A0_STORES) kind="gpulib_a0_store_count";
        else if(e->kind==VH86_A0_SAME) kind="gpulib_a0_same_count";
        else if(e->kind==VH86_COPY_STORES) kind="gpulib_copy_store_count";
        else if(e->kind==VH86_COPY_SAME) kind="gpulib_copy_same_count";
        else if(e->kind==VH87_OVERLAP_STORES) kind="gpulib_overlap_store_count";
        else if(e->kind==VH87_OVERLAP_SAME) kind="gpulib_overlap_same_count";
        else if(e->kind==VH87_MASK_UPLOAD_STORES) kind="gpulib_mask_upload_store_count";
        else if(e->kind==VH87_MASK_UPLOAD_SAME) kind="gpulib_mask_upload_same_count";
        else if(e->kind==VH87_WRAP_STORES) kind="gpulib_wrap_store_count";
        else if(e->kind==VH87_WRAP_SAME) kind="gpulib_wrap_same_count";
        else if(e->kind==VH88_ASYNC_QUEUED) kind="async_dma_queued";
        else if(e->kind==VH88_ASYNC_COMPLETED) kind="async_dma_completed";
        else if(e->kind==VH88_ASYNC_STORES) kind="async_dma_store_count";
        else if(e->kind==VH88_ASYNC_SAME) kind="async_dma_same_count";
        else if(e->kind==VH89_COPY_QUEUED) kind="async_copy_queued";
        else if(e->kind==VH89_COPY_COMPLETED) kind="async_copy_completed";
        else if(e->kind==VH89_COPY_STORES) kind="async_copy_store_count";
        else if(e->kind==VH89_COPY_SAME) kind="async_copy_same_count";
        else if(e->kind==VH89_MASKED_COMPLETED) kind="async_copy_masked_completed";
        else if(e->kind==VH89_SYNC_STORES) kind="post_async_sync_copy_stores";
        else if(e->kind==VH89_SYNC_SAME) kind="post_async_sync_copy_same";
        else if(e->kind==VH90_A0_QUEUED) kind="mixed_a0_queued";
        else if(e->kind==VH90_A0_DONE) kind="mixed_a0_completed";
        else if(e->kind==VH90_A0_STORES) kind="mixed_a0_store_count";
        else if(e->kind==VH90_A0_SAME) kind="mixed_a0_same_count";
        else if(e->kind==VH90_COPY_QUEUED) kind="mixed_copy_queued";
        else if(e->kind==VH90_COPY_DONE) kind="mixed_copy_completed";
        else if(e->kind==VH90_COPY_STORES) kind="mixed_copy_store_count";
        else if(e->kind==VH90_COPY_SAME) kind="mixed_copy_same_count";
        else if(e->kind==VH90_MASKED_COPIES) kind="mixed_masked_copies";
        else if(e->kind==VH90_WORKER_STEPS) kind="mixed_worker_steps";
        else if(e->kind==VH90_WORKER_ORDER) kind="mixed_worker_order";
        else if(e->kind==VH90_SYNC_A0) kind="mixed_sync_a0_store_count";
        else if(e->kind==VH90_SYNC_COPY) kind="mixed_sync_copy_store_count";
        else if(e->kind==VH90_SYNC_SAME) kind="mixed_sync_copy_same_count";
        else if(e->kind==VH91_R1_A0_QUEUED) kind="cycle1_a0_queued";
        else if(e->kind==VH91_R2_A0_QUEUED) kind="cycle2_a0_queued";
        else if(e->kind==VH91_R1_A0_DONE) kind="cycle1_a0_done";
        else if(e->kind==VH91_R2_A0_DONE) kind="cycle2_a0_done";
        else if(e->kind==VH91_R1_A0_STORES) kind="cycle1_a0_stores";
        else if(e->kind==VH91_R2_A0_STORES) kind="cycle2_a0_stores";
        else if(e->kind==VH91_R1_COPY_QUEUED) kind="cycle1_copy_queued";
        else if(e->kind==VH91_R2_COPY_QUEUED) kind="cycle2_copy_queued";
        else if(e->kind==VH91_R1_COPY_DONE) kind="cycle1_copy_done";
        else if(e->kind==VH91_R2_COPY_DONE) kind="cycle2_copy_done";
        else if(e->kind==VH91_R1_COPY_STORES) kind="cycle1_copy_stores";
        else if(e->kind==VH91_R2_COPY_STORES) kind="cycle2_copy_stores";
        else if(e->kind==VH91_R1_COPY_SAME) kind="cycle1_copy_same";
        else if(e->kind==VH91_R2_COPY_SAME) kind="cycle2_copy_same";
        else if(e->kind==VH91_R1_MASKED_COPY) kind="cycle1_masked_copy";
        else if(e->kind==VH91_R2_MASKED_COPY) kind="cycle2_masked_copy";
        else if(e->kind==VH91_R1_SYNC_A0) kind="cycle1_sync_a0";
        else if(e->kind==VH91_R2_SYNC_A0) kind="cycle2_sync_a0";
        else if(e->kind==VH91_R1_SYNC_COPY) kind="cycle1_sync_copy";
        else if(e->kind==VH91_R2_SYNC_COPY) kind="cycle2_sync_copy";
        else if(e->kind==VH91_R1_SYNC_SAME) kind="cycle1_sync_same";
        else if(e->kind==VH91_R2_SYNC_SAME) kind="cycle2_sync_same";
        else if(e->kind==VH92_TRIED) kind="pressure_tried";
        else if(e->kind==VH92_ACCEPTED) kind="pressure_accepted";
        else if(e->kind==VH92_IDLE_FALLBACK) kind="pressure_idle_fallback";
        else if(e->kind==VH92_FULL_FALLBACK) kind="pressure_full_fallback";
        else if(e->kind==VH92_PEAK_WORDS) kind="pressure_peak_words";
        else if(e->kind==VH92_WORKER_DONE) kind="pressure_worker_completed";
        else if(e->kind==VH92_WORKER_STORES) kind="pressure_worker_stores";
        else if(e->kind==VH92_SYNC_STORES) kind="pressure_sync_stores";
        else if(e->kind==VH92_PENDING) kind="pressure_pending_words";
        else if(e->kind==VH92_WORKER_SAME) kind="pressure_worker_same";
        else if(e->kind==VH92_SYNC_SAME) kind="pressure_sync_same";
        else if(e->kind==VH93_DETAIL_COUNT) kind="lane_detail_events";
        else if(e->kind==VH93_AGG_COUNT) kind="lane_aggregate_events";
        else if(e->kind==VH93_TOTAL_COUNT) kind="lane_total_events";
        else if(e->kind==VH94_CACHED_READS) kind="snapshot_cached_reads";
        else if(e->kind==VH94_INVALIDATED) kind="snapshot_invalidation_proven";
        else if(e->kind==VH94_VERIFIED_READS) kind="snapshot_verified_reads";
        else if(e->kind>=VH95_ROUND_1 && e->kind<=VH95_ROUND_8) {
            static const char *const names[8]={
                "append_round_1","append_round_2","append_round_3",
                "append_round_4","append_round_5","append_round_6",
                "append_round_7","append_round_8"
            };
            kind=names[e->kind-VH95_ROUND_1];
        }
        else if(e->kind==VH95_PREFIXES) kind="append_prefix_checks";
        else if(e->kind==VH95_EXPORTS) kind="append_memory_exports";
        else if(e->kind==VH95_MERGES) kind="append_exact_rebuilds";
        else if(e->kind==VH95_STALE_REFUSALS) kind="append_stale_refusals";
        else if(e->kind==VH95_STABLE_READS) kind="append_stable_reads";
        else if(e->kind==VH96_DETAIL_REMAINING) kind="boundary_detail_remaining";
        else if(e->kind==VH96_AGG_REMAINING) kind="boundary_aggregate_remaining";
        else if(e->kind==VH96_SERIALIZED_TWICE) kind="boundary_identical_serializations";
        else if(e->kind==VH97_EPOCH) kind="reset_observer_epoch";
        else if(e->kind==VH97_SCRUBBED) kind="reset_serializer_scrubbed_bytes";
        else if(e->kind==VH97_REPLAY) kind="reset_stable_replays";
        else if(e->kind==VH98_OLD_REFUSED) kind="recovery_old_path_refused";
        else if(e->kind==VH98_NEW_PUBLISHED) kind="recovery_new_path_published";
        else if(e->kind==VH98_REPLAY_REFUSED) kind="recovery_replay_refused";
        else if(e->kind==VH99_STAGE_REFUSED) kind="interrupted_stage_refused";
        else if(e->kind==VH99_FRESH_RECOVERED) kind="interrupted_fresh_published";
        else if(e->kind==VH99_OLD_UNMODIFIED) kind="interrupted_stage_preserved";
        else if(e->kind==VH100_FIRST_DIR_SYNC) kind="durability_post_link_directory_sync";
        else if(e->kind==VH100_FINAL_DIR_SYNC) kind="durability_post_unlink_directory_sync";
        else if(e->kind==VH100_FAILURE_REFUSED) kind="durability_replay_refused";
        else if(e->kind==VH101_REOPEN_VERIFIED) kind="reopened_private_commits";
        else if(e->kind==VH101_PARENT_RESYNC) kind="reopened_private_parent_syncs";
        else if(e->kind==VH101_BAD_REOPEN_REFUSED) kind="reopened_bad_bytes_refused";
        else if(e->kind==VH102_ANCHORED_COMMITS) kind="anchored_private_commits";
        else if(e->kind==VH102_PARENT_MATCHES) kind="anchored_parent_identity_checks";
        else if(e->kind==VH102_REDIRECT_REFUSED) kind="anchored_duplicate_refused";
        else if(e->kind==VH103_SAFE_WALKS) kind="safe_parent_component_walks";
        else if(e->kind==VH103_VERIFIED_FILES) kind="safe_final_inode_verified";
        else if(e->kind==VH103_SYMLINK_REFUSED) kind="safe_parent_symlink_refused";
        else return -1;
        if(used>=capacity) return -1;
        /* GPU DMA2 is an address, NOT an executed GP0 command. */
        written=snprintf(output+used,capacity-used,
          "{\"kind\":\"%s\",\"seq\":%u,\"value\":%u,\"cycle\":%u,\"frame\":%u}\n",
          kind,e->sequence,e->value,e->cycle,e->frame);
        if(written<0 || (size_t)written>=capacity-used) {
            output[0]='\0';
            return -1;
        }
        used+=(size_t)written;
    }
    /* Recheck merged snapshot against BOTH immutable source lanes before
     * allowing the private publisher to create an exclusive output. */
    if(edges<2 || used>INT_MAX || vh94_snapshot_check()!=0) {
        output[0]='\0';return -1;
    }
    return (int)used;
}
