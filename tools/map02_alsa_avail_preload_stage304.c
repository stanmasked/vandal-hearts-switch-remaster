/*
 * Stage304 research-only runtime ALSA entrypoint observer.
 *
 * LD_PRELOAD interposes the public snd_pcm_avail_delay C symbol on NeXium's
 * userspace path without rebuilding NeXium, CPAL, NRO, or changing its data
 * callback. Per-call operations: one TLS slot lookup + relaxed atomics;
 * clock_gettime only on negative results. A separate reporter pthread writes
 * capped monotonic aggregate snapshots. No real Linux TIDs, PCM pointers,
 * samples, error strings, process args or host paths in the exported CSV.
 *
 * This observer changes process scheduling and is NOT a production fix.
 * Internal libasound calls or alternate symbol lookup can bypass preload.
 */
#define _GNU_SOURCE
#include <alsa/asoundlib.h>
#include <dlfcn.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define VH_SLOTS 64
#define VH_REPORTS 240

typedef int (*vh_avail_fn)(snd_pcm_t *, snd_pcm_sframes_t *,
                           snd_pcm_sframes_t *);
typedef struct {
    _Atomic uint64_t calls;
    _Atomic uint64_t successes;
    _Atomic uint64_t eio;
    _Atomic uint64_t epipe;
    _Atomic uint64_t eagain;
    _Atomic uint64_t other_negative;
    _Atomic uint64_t first_negative_ns;
    _Atomic uint64_t last_negative_ns;
} vh_slot;

static vh_slot slots[VH_SLOTS];
static _Atomic unsigned int slot_count = 0;
static _Atomic uint64_t overflow_calls = 0;
static _Atomic int symbol_resolved = 0;
static _Atomic int observer_running = 1;
static pthread_once_t lookup_once = PTHREAD_ONCE_INIT;
static vh_avail_fn real_avail = NULL;
static _Thread_local int tls_index = -1;
static pthread_t reporter_thread;
static int reporter_started = 0;
static char observer_path[4096];

static uint64_t ns_now(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0;
    return (uint64_t)ts.tv_sec * UINT64_C(1000000000) + (uint64_t)ts.tv_nsec;
}

static void resolve_real(void) {
    /* ALSA's public API normally resolves through RTLD_NEXT for CPAL.
     * dlsym failures are counted as OTHER, NOT attributed to EIO/ALSA.
     */
    void *ptr = dlsym(RTLD_NEXT, "snd_pcm_avail_delay");
    if (ptr != NULL) {
        memcpy(&real_avail, &ptr, sizeof(real_avail));
        atomic_store_explicit(&symbol_resolved, 1, memory_order_relaxed);
    }
}

int snd_pcm_avail_delay(snd_pcm_t *pcm, snd_pcm_sframes_t *availp,
                        snd_pcm_sframes_t *delayp) {
    pthread_once(&lookup_once, resolve_real);
    int rc = real_avail == NULL ? -ENOSYS : real_avail(pcm, availp, delayp);

    if (tls_index == -1) {
        unsigned int next = atomic_fetch_add_explicit(
            &slot_count, 1, memory_order_relaxed);
        tls_index = next < VH_SLOTS ? (int)next : -2;
    }
    if (tls_index < 0) {
        atomic_fetch_add_explicit(&overflow_calls, 1, memory_order_relaxed);
        return rc;
    }
    vh_slot *s = &slots[tls_index];
    atomic_fetch_add_explicit(&s->calls, 1, memory_order_relaxed);
    if (rc >= 0) {
        atomic_fetch_add_explicit(&s->successes, 1, memory_order_relaxed);
    } else {
        uint64_t now = ns_now();
        if (rc == -EIO) {
            atomic_fetch_add_explicit(&s->eio, 1, memory_order_relaxed);
        } else if (rc == -EPIPE) {
            atomic_fetch_add_explicit(&s->epipe, 1, memory_order_relaxed);
        } else if (rc == -EAGAIN) {
            atomic_fetch_add_explicit(&s->eagain, 1, memory_order_relaxed);
        } else {
            atomic_fetch_add_explicit(&s->other_negative, 1, memory_order_relaxed);
        }
        uint64_t unset = 0;
        if (now != 0) {
            (void)atomic_compare_exchange_strong_explicit(
                &s->first_negative_ns, &unset, now,
                memory_order_relaxed, memory_order_relaxed);
            atomic_store_explicit(&s->last_negative_ns, now, memory_order_relaxed);
        }
    }
    return rc;
}

static void *reporter(void *unused) {
    (void)unused;
    FILE *out = fopen(observer_path, "w");
    if (out == NULL) return NULL;
    setvbuf(out, NULL, _IOLBF, 0);
    const struct timespec gap = {.tv_sec = 0, .tv_nsec = 200000000};
    for (int n = 0; n < VH_REPORTS; ++n) {
        uint64_t now = ns_now();
        unsigned int seen = atomic_load_explicit(&slot_count,memory_order_relaxed);
        uint64_t overflow = atomic_load_explicit(&overflow_calls,memory_order_relaxed);
        int found = atomic_load_explicit(&symbol_resolved,memory_order_relaxed);
        fprintf(out,"H,%llu,%u,%llu,%d\n",
                (unsigned long long)now,seen,(unsigned long long)overflow,found);
        unsigned int max = seen > VH_SLOTS ? VH_SLOTS : seen;
        for (unsigned int i=0; i<max; ++i) {
            vh_slot *s = &slots[i];
            fprintf(out,"T,%llu,%u,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu\n",
                (unsigned long long)now, i+1,
                (unsigned long long)atomic_load_explicit(&s->calls,memory_order_relaxed),
                (unsigned long long)atomic_load_explicit(&s->successes,memory_order_relaxed),
                (unsigned long long)atomic_load_explicit(&s->eio,memory_order_relaxed),
                (unsigned long long)atomic_load_explicit(&s->epipe,memory_order_relaxed),
                (unsigned long long)atomic_load_explicit(&s->eagain,memory_order_relaxed),
                (unsigned long long)atomic_load_explicit(&s->other_negative,memory_order_relaxed),
                (unsigned long long)atomic_load_explicit(&s->first_negative_ns,memory_order_relaxed),
                (unsigned long long)atomic_load_explicit(&s->last_negative_ns,memory_order_relaxed));
        }
        fflush(out);
        if (!atomic_load_explicit(&observer_running,memory_order_relaxed)) break;
        nanosleep(&gap,NULL);
    }
    fclose(out);
    return NULL;
}

__attribute__((constructor))
static void vh_stage304_start(void) {
    const char *value = getenv("VH_MAP02_ALSA_USERTRACE_PATH");
    if (value == NULL || value[0] != '/' ||
        strlen(value) >= sizeof(observer_path)) return;
    memcpy(observer_path,value,strlen(value)+1);
    if (pthread_create(&reporter_thread,NULL,reporter,NULL)==0)
        reporter_started=1;
}

__attribute__((destructor))
static void vh_stage304_stop(void) {
    atomic_store_explicit(&observer_running,0,memory_order_relaxed);
    if (reporter_started) pthread_join(reporter_thread,NULL);
}
