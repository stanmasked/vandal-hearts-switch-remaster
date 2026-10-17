#ifndef VH_AUDOUT_QUEUE_TELEMETRY_H
#define VH_AUDOUT_QUEUE_TELEMETRY_H
#include <stdint.h>
#include <stdio.h>

/* Owner-thread-only, fixed-size 1-second buckets; no allocation, I/O,
 * atomics or libnx dependencies in the PCM path. Full-session totals
 * are retained even when the oldest bucket is evicted. */
#define VH_AUDOUT_QUEUE_BUCKETS 128u
#define VH_AUDOUT_QUEUE_SAMPLE_EVERY 16u
/* Inclusive lower bounds of latency bands (nanoseconds). */
#define VH_AUDOUT_LT25_NS UINT64_C(25000000)
#define VH_AUDOUT_LT40_NS UINT64_C(40000000)
#define VH_AUDOUT_LT50_NS UINT64_C(50000000)
#define VH_AUDOUT_LATENCY_BANDS 4u
typedef struct {
    uint64_t second;
    uint64_t attempts, returns, failures, max_call_ns;
    uint64_t latency_bins[VH_AUDOUT_LATENCY_BANDS];
    uint32_t queue_ok, queue_errors, queue_min, queue_max;
    int valid;
} VhAudoutQueueBucket;
typedef struct {
    uint64_t origin_ns, last_second;
    uint64_t attempts, returns, failures, max_call_ns;
    uint64_t latency_bins[VH_AUDOUT_LATENCY_BANDS];
    uint64_t queue_ok, queue_errors, overwritten_windows, clock_errors;
    uint32_t queue_min, queue_max;
    VhAudoutQueueBucket bucket[VH_AUDOUT_QUEUE_BUCKETS];
} VhAudoutQueueTelemetry;
void vh_audout_queue_reset(VhAudoutQueueTelemetry *t);
/* Probe ONLY before a normal audoutPlayBuffer; 1/16 calls. */
int vh_audout_queue_probe_due(const VhAudoutQueueTelemetry *t);
/* Exactly one observation per attempted audoutPlayBuffer. queue_status
 * -1 = no query; 0 = query failed; 1 = query returned queue_count.
 * These are service pre-submit snapshots, NEVER DAC queue occupancy
 * throughout the blocking call or proof of/against audible underruns.
 * returned = exact descriptor released, not audible playback. */
void vh_audout_queue_record(VhAudoutQueueTelemetry *t,
                            uint64_t begin_ns, uint64_t end_ns,
                            int returned, int queue_status,
                            uint32_t queue_count);
/* Only after the audio owner has joined. Does not mutate t.
 * Includes a full-session TOTAL and chronological retained windows. */
int vh_audout_queue_write_csv(const VhAudoutQueueTelemetry *t, FILE *out);
/* Byte-exact independent reread of canonical CSV, including EOF. */
int vh_audout_queue_verify_csv(const VhAudoutQueueTelemetry *t,FILE *in);
/* Separate v1 latency histogram transport: exact per-call band counters,
 * per second plus total; the proven Stage-269 CSV stays byte-compatible. */
int vh_audout_latency_write_csv(const VhAudoutQueueTelemetry *t,FILE *out);
int vh_audout_latency_verify_csv(const VhAudoutQueueTelemetry *t,FILE *in);
/* Stage 273 separate absolute guest-clock anchor: same monotonic ns
 * source as scene INPUT events, never inferred from host PCM markers. */
int vh_audout_clock_write_csv(const VhAudoutQueueTelemetry *t,FILE *out);
int vh_audout_clock_verify_csv(const VhAudoutQueueTelemetry *t,FILE *in);
#endif
