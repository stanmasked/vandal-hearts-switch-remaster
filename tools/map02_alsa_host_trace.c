/*
 * MAP02 opt-in Linux host-only ALSA probe, not Switch guest/source code.
 * Interpose PCM configuration + bounded write/commit durations and ordinal PCM IDs.
 * Does NOT observe CPAL Rust callback itself, guest audout, or physical DAC.
 * Explicitly adds symbol-interposition, locking, syscall and CSV overhead.
 *
 * Build: cc -std=c11 -O2 -fPIC -shared -Wall -Wextra -Werror
 *           -o libmap02_alsa_trace.so tools/map02_alsa_host_trace.c -ldl
 * Run ONLY the research NeXium process with:
 *   VH_MAP02_ALSA_TRACE_PATH=/absolute/owned/file.csv LD_PRELOAD=/absolute/lib.so
 * Never inject into unrelated processes or ship in Nintendo Switch builds.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

/* Linux x86_64 ALSA public ABI; no libasound headers or link needed. */
typedef struct _snd_pcm snd_pcm_t;
typedef struct _snd_pcm_hw_params snd_pcm_hw_params_t;
typedef unsigned long snd_pcm_uframes_t;
typedef long snd_pcm_sframes_t;

/* Process-local stream ordinals; raw snd_pcm_t addresses NEVER enter CSV.
 * Identifies the PCM instance of a hook, not Rust CPAL callback identity.
 * Bounded table/atomic lock, with removal after successful snd_pcm_close. */
#define MAX_STREAMS 32
static atomic_flag stream_lock = ATOMIC_FLAG_INIT;
static snd_pcm_t *stream_ptrs[MAX_STREAMS];
static unsigned stream_ids[MAX_STREAMS];
static unsigned next_stream_id = 1u;
static void lock_streams(void) {
    while (atomic_flag_test_and_set_explicit(
            &stream_lock, memory_order_acquire)) { /* short bounded table */ }
}
static void unlock_streams(void) {
    atomic_flag_clear_explicit(&stream_lock, memory_order_release);
}
static unsigned identify_stream(snd_pcm_t *pcm) {
    if (!pcm) return 0;
    lock_streams();
    for (unsigned i=0;i<MAX_STREAMS;i++) {
        if (stream_ptrs[i]==pcm) {
            unsigned found=stream_ids[i];unlock_streams();return found;
        }
    }
    for (unsigned i=0;i<MAX_STREAMS;i++) {
        if (!stream_ptrs[i]) {
            unsigned fresh=next_stream_id++;
            stream_ptrs[i]=pcm;
            stream_ids[i]=fresh;
            unlock_streams();
            return fresh;
        }
    }
    unlock_streams();
    return 0; /* fail closed: no guessed identity */
}
static void retire_stream(snd_pcm_t *pcm) {
    lock_streams();
    for (unsigned i=0;i<MAX_STREAMS;i++) {
        if (stream_ptrs[i]==pcm) {
            stream_ptrs[i]=NULL; stream_ids[i]=0; break;
        }
    }
    unlock_streams();
}

static _Atomic unsigned emitted = 0;
#define MAX_EVENTS 256

static uint64_t now_ns(void) {
    struct timespec ts = {0, 0};
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0;
    return (uint64_t)ts.tv_sec * UINT64_C(1000000000) + (uint64_t)ts.tv_nsec;
}
static long tid(void) { return syscall(SYS_gettid); }

static void *next_symbol(const char *name) {
    void *fn = dlsym(RTLD_NEXT, name);
    if (!fn) _exit(120);  /* do not invent a successful ALSA operation */
    return fn;
}

static void log_event(const char *event, uint64_t start, uint64_t end,
                      snd_pcm_uframes_t requested, snd_pcm_sframes_t ret,
                      unsigned rate, unsigned channels,
                      snd_pcm_uframes_t period, snd_pcm_uframes_t buffer,
                      unsigned stream_id) {
    const char *path = getenv("VH_MAP02_ALSA_TRACE_PATH");
    if (!path || path[0] != '/' || strlen(path) > 800) return;
    unsigned slot = atomic_fetch_add_explicit(&emitted, 1u, memory_order_relaxed);
    if (slot >= MAX_EVENTS) return;
    /* Append-only, close-on-exec, no game samples, pointers, or file names. */
    int fd = open(path, O_WRONLY | O_APPEND | O_CREAT | O_CLOEXEC, 0600);
    if (fd < 0) return;
    char line[256];
    int n = snprintf(line, sizeof(line),
                     "%s,%" PRIu64 ",%" PRIu64 ",%ld,%lu,%ld,"
                     "%u,%u,%lu,%lu,%u\n",
                     event, start, end, tid(), (unsigned long)requested,
                     (long)ret, rate, channels, (unsigned long)period,
                     (unsigned long)buffer, stream_id);
    if (n > 0 && (size_t)n < sizeof(line))
        (void)syscall(SYS_write, fd, line, (size_t)n);
    (void)close(fd);
}

/* A successful snd_pcm_hw_params applies negotiated ALSA parameters.
 * Value getters read params after real call; failures stay 0/unknown. */
int snd_pcm_hw_params(snd_pcm_t *pcm, snd_pcm_hw_params_t *params) {
    typedef int (*real_t)(snd_pcm_t *, snd_pcm_hw_params_t *);
    real_t real_fn = (real_t)next_symbol("snd_pcm_hw_params");
    uint64_t start = now_ns();
    int result = real_fn(pcm, params);
    uint64_t end = now_ns();
    unsigned rate = 0, channels = 0;
    snd_pcm_uframes_t period = 0, buffer = 0;
    if (result == 0) {
        typedef int (*get_u_t)(const snd_pcm_hw_params_t *, unsigned *);
        typedef int (*get_frame_t)(const snd_pcm_hw_params_t *, snd_pcm_uframes_t *);
        typedef int (*get_near_t)(const snd_pcm_hw_params_t *, snd_pcm_uframes_t *, int *);
        typedef int (*get_rate_t)(const snd_pcm_hw_params_t *, unsigned *, int *);
        get_u_t get_channels = (get_u_t)dlsym(RTLD_NEXT, "snd_pcm_hw_params_get_channels");
        get_frame_t get_buffer = (get_frame_t)dlsym(RTLD_NEXT, "snd_pcm_hw_params_get_buffer_size");
        get_near_t get_period = (get_near_t)dlsym(RTLD_NEXT, "snd_pcm_hw_params_get_period_size");
        get_rate_t get_rate = (get_rate_t)dlsym(RTLD_NEXT, "snd_pcm_hw_params_get_rate");
        int direction = 0;
        if (get_channels && get_channels(params, &channels) != 0) channels = 0;
        if (get_buffer && get_buffer(params, &buffer) != 0) buffer = 0;
        if (get_period && get_period(params, &period, &direction) != 0) period = 0;
        if (get_rate && get_rate(params, &rate, &direction) != 0) rate = 0;
    }
    log_event("HW_PARAMS", start, end, 0, result, rate, channels, period, buffer,
              identify_stream(pcm));
    return result;
}

snd_pcm_sframes_t snd_pcm_writei(snd_pcm_t *pcm, const void *samples,
                                snd_pcm_uframes_t frames) {
    typedef snd_pcm_sframes_t (*real_t)(snd_pcm_t *, const void *, snd_pcm_uframes_t);
    real_t real_fn = (real_t)next_symbol("snd_pcm_writei");
    uint64_t start = now_ns();
    snd_pcm_sframes_t result = real_fn(pcm, samples, frames);
    uint64_t end = now_ns();
    log_event("WRITEI", start, end, frames, result, 0, 0, 0, 0,
              identify_stream(pcm));
    return result;
}

snd_pcm_sframes_t snd_pcm_mmap_commit(snd_pcm_t *pcm,
                                     snd_pcm_uframes_t offset,
                                     snd_pcm_uframes_t frames) {
    typedef snd_pcm_sframes_t (*real_t)(snd_pcm_t *, snd_pcm_uframes_t,
                                        snd_pcm_uframes_t);
    real_t real_fn = (real_t)next_symbol("snd_pcm_mmap_commit");
    uint64_t start = now_ns();
    snd_pcm_sframes_t result = real_fn(pcm, offset, frames);
    uint64_t end = now_ns();
    log_event("MMAP_COMMIT", start, end, frames, result, 0, 0, 0, 0,
              identify_stream(pcm));
    return result;
}

/* Clear a slot only after the underlying ALSA close succeeded. */
int snd_pcm_close(snd_pcm_t *pcm) {
    typedef int (*real_t)(snd_pcm_t *);
    real_t real_fn=(real_t)next_symbol("snd_pcm_close");
    int result=real_fn(pcm);
    if (result==0) retire_stream(pcm);
    return result;
}
