#ifndef VH80_NATIVE_TIMELINE_H
#define VH80_NATIVE_TIMELINE_H
#include <stdint.h>
/* Opt-in bounded observer: input submissions and emulator VBlank only.
 * NOT native GP0 consumption, GPU completion, VRAM writes, or retail MAP02. */
enum { VH80_VBLANK=1, VH80_GP1_MMIO=2, VH80_GPU_DMA2=3, VH83_GP0_UNAI_HANDLED=4, VH84_UNAI_SAMPLE_DELTA=5, VH85_UNAI_STORE_COUNT=6, VH85_UNAI_SAME_STORE_COUNT=7,
  VH86_A0_STORES=8, VH86_A0_SAME=9, VH86_COPY_STORES=10, VH86_COPY_SAME=11,
  VH87_OVERLAP_STORES=12, VH87_OVERLAP_SAME=13,
  VH87_MASK_UPLOAD_STORES=14, VH87_MASK_UPLOAD_SAME=15,
  VH87_WRAP_STORES=16, VH87_WRAP_SAME=17,
  VH88_ASYNC_QUEUED=18, VH88_ASYNC_COMPLETED=19,
  VH88_ASYNC_STORES=20, VH88_ASYNC_SAME=21,
  VH89_COPY_QUEUED=22, VH89_COPY_COMPLETED=23,
  VH89_COPY_STORES=24, VH89_COPY_SAME=25,
  VH89_MASKED_COMPLETED=26,
  VH89_SYNC_STORES=27, VH89_SYNC_SAME=28,
  VH90_A0_QUEUED=29, VH90_A0_DONE=30, VH90_A0_STORES=31,
  VH90_A0_SAME=32, VH90_COPY_QUEUED=33, VH90_COPY_DONE=34,
  VH90_COPY_STORES=35, VH90_COPY_SAME=36, VH90_MASKED_COPIES=37,
  VH90_WORKER_STEPS=38, VH90_WORKER_ORDER=39,
  VH90_SYNC_A0=40, VH90_SYNC_COPY=41, VH90_SYNC_SAME=42,
  VH91_R1_A0_QUEUED=43,
  VH91_R2_A0_QUEUED=54,
  VH91_R1_A0_DONE=44,
  VH91_R2_A0_DONE=55,
  VH91_R1_A0_STORES=45,
  VH91_R2_A0_STORES=56,
  VH91_R1_COPY_QUEUED=46,
  VH91_R2_COPY_QUEUED=57,
  VH91_R1_COPY_DONE=47,
  VH91_R2_COPY_DONE=58,
  VH91_R1_COPY_STORES=48,
  VH91_R2_COPY_STORES=59,
  VH91_R1_COPY_SAME=49,
  VH91_R2_COPY_SAME=60,
  VH91_R1_MASKED_COPY=50,
  VH91_R2_MASKED_COPY=61,
  VH91_R1_SYNC_A0=51,
  VH91_R2_SYNC_A0=62,
  VH91_R1_SYNC_COPY=52,
  VH91_R2_SYNC_COPY=63,
  VH91_R1_SYNC_SAME=53,
  VH91_R2_SYNC_SAME=64,
  VH92_TRIED=65, VH92_ACCEPTED=66, VH92_IDLE_FALLBACK=67,
  VH92_FULL_FALLBACK=68, VH92_PEAK_WORDS=69,
  VH92_WORKER_DONE=70, VH92_WORKER_STORES=71,
  VH92_SYNC_STORES=72, VH92_PENDING=73,
  VH92_WORKER_SAME=74, VH92_SYNC_SAME=75,
  VH93_DETAIL_COUNT=76, VH93_AGG_COUNT=77, VH93_TOTAL_COUNT=78,
  VH94_CACHED_READS=79, VH94_INVALIDATED=80, VH94_VERIFIED_READS=81,
  VH95_ROUND_1=82, VH95_ROUND_2=83, VH95_ROUND_3=84,
  VH95_ROUND_4=85, VH95_ROUND_5=86, VH95_ROUND_6=87,
  VH95_ROUND_7=88, VH95_ROUND_8=89,
  VH95_PREFIXES=90, VH95_EXPORTS=91, VH95_MERGES=92,
  VH95_STALE_REFUSALS=93, VH95_STABLE_READS=94,
  VH96_DETAIL_REMAINING=95, VH96_AGG_REMAINING=96,
  VH96_SERIALIZED_TWICE=97,
  VH97_EPOCH=98, VH97_SCRUBBED=99, VH97_REPLAY=100,
  VH98_OLD_REFUSED=101, VH98_NEW_PUBLISHED=102,
  VH98_REPLAY_REFUSED=103,
  VH99_STAGE_REFUSED=104, VH99_FRESH_RECOVERED=105,
  VH99_OLD_UNMODIFIED=106,
  VH100_FIRST_DIR_SYNC=107, VH100_FINAL_DIR_SYNC=108,
  VH100_FAILURE_REFUSED=109,
  VH101_REOPEN_VERIFIED=110, VH101_PARENT_RESYNC=111,
  VH101_BAD_REOPEN_REFUSED=112,
  VH102_ANCHORED_COMMITS=113, VH102_PARENT_MATCHES=114,
  VH102_REDIRECT_REFUSED=115,
  VH103_SAFE_WALKS=116, VH103_VERIFIED_FILES=117,
  VH103_SYMLINK_REFUSED=118,
  VH104_DOUBLE_READS=119, VH104_MODIFIED_REFUSED=120,
  VH104_PUBLISHES=121 };
#define VH80_CAPACITY_DETAIL 4096u
#define VH80_CAPACITY_AGGREGATE 256u
#define VH80_TOTAL_CAPACITY (VH80_CAPACITY_DETAIL+VH80_CAPACITY_AGGREGATE)
typedef struct {
    uint32_t sequence, kind, value, cycle, frame;
} vh80_event;
#ifdef __cplusplus
extern "C" {
#endif
void vh80_record(uint32_t kind,uint32_t value,uint32_t cycle,uint32_t frame);
void vh80_reset(void);
/* Enable only after authenticated synthetic fixture acceptance. */
void vh84_set_sampling(int enabled);
int vh84_sampling_enabled(void);
void vh85_reset_command(void);
void vh85_note_store(uint32_t before, uint32_t after);
unsigned int vh85_store_count(void);
unsigned int vh85_same_store_count(void);
unsigned int vh85_write_overflow(void);
/* Observes synchronous gpulib logical 16-bit stores on opt-in fixture. */
enum { VH86_A0_UPLOAD=1, VH86_VRAM_COPY=2 };
void vh86_reset(void);
void vh86_note_store(uint32_t source,uint32_t old_value,uint32_t new_value);
uint32_t vh86_store_count(uint32_t source);
uint32_t vh86_same_store_count(uint32_t source);
uint32_t vh86_write_overflow(void);
unsigned int vh80_count(void);
unsigned int vh80_detailed_count(void);
unsigned int vh80_aggregate_count(void);
unsigned int vh80_dropped(void);
const vh80_event *vh80_events(void);
/* Zero-copy cached merged view. Rebuild ONLY after a successful append/reset.
 * Explicit integrity check recomputes source/merge equality; no raw digest export.
 * These functions must be called by the host AFTER native GPUfreeze. */
unsigned int vh94_merge_runs(void);
unsigned int vh94_cache_hits(void);
unsigned int vh94_verify_runs(void);
int vh94_snapshot_check(void);
/* Monotone observer lifetime identifier; reset scrubs both source lanes
 * AND prior merged cache. Only invoke reset after GPU workers stop. */
unsigned int vh97_reset_epoch(void);
int vh97_buffers_erased(void);
#ifdef __cplusplus
}
#endif
#endif
