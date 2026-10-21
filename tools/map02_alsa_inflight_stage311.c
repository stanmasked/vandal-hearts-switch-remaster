/*
 * Stage311 phase-counting ALSA userspace shim. Parent Stage308 native-TLS CPAL marker preserved.
 * Sole observable side effect: atomic anonymous per-thread counters in an
 * explicitly opted-in mmap file. Never log or allocate in an audio callback.
 * No arguments/pointers, PIDs, names or PCM samples are recorded.
 *
 * LD_PRELOAD fundamentally changes dynamic symbol resolution/scheduling.
 * These counts cannot demonstrate native uninstrumented CPAL root cause.
 */
#define _GNU_SOURCE
#include <alsa/asoundlib.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#define VH_SLOTS 64
#define VH_OPS 9
#define VH_KINDS 6
#define VH_PHASE_OPS 13
#define VH_PHASE_OFFSET 33792
#define VH_SIZE 65536
#define VH_MAGIC "VH305AL1"

enum {
  OP_AVAIL_DELAY, OP_PREPARE, OP_RECOVER, OP_STATUS, OP_START,
  OP_DROP, OP_PAUSE, OP_WRITEI, OP_READI, OP_WAIT,
  OP_AVAIL, OP_AVAIL_UPDATE, OP_POLL_DESCRIPTORS
};
enum { KIND_TOTAL, KIND_OK, KIND_EIO, KIND_EPIPE, KIND_EAGAIN, KIND_OTHER_NEG };
struct vh_shared {
  char magic[8];
  uint64_t next_alias;
  uint64_t counters[VH_SLOTS][VH_OPS][VH_KINDS];
  /*
   * Explicit reserved hole makes the callback marker available at fixed
   * byte offset 32768 (16 + 64*9*6*8 = 27664).
   * The original Stage305 reader is unaffected by these new marker fields.
   */
  unsigned char padding[32768 - (16 + VH_SLOTS*VH_OPS*VH_KINDS*8)];
  uint64_t cpal_callback_entries[VH_SLOTS];
  unsigned char stage311_padding[512];
  /* Each independently sampled (begin, return, negative_return) is atomic.
   * NEVER treat a single sampled in-flight phase as a deadlock. */
  uint64_t phase[VH_SLOTS][VH_PHASE_OPS][3];
};
_Static_assert(offsetof(struct vh_shared, cpal_callback_entries)==32768,
               "CPAL anonymous TLS counter must be at stable mmap byte offset");
_Static_assert(offsetof(struct vh_shared, phase)==VH_PHASE_OFFSET,
               "Stage311 phase counters must occupy stable reserved offset");
_Static_assert(sizeof(struct vh_shared)<=VH_SIZE,
               "Stage308 C shim counter storage exceeds bounded private mmap");

static struct vh_shared *vh = NULL;
/* LD_PRELOAD at process start permits initial-exec static TLS: do not
 * invoke a dynamic TLS runtime allocator on the first CPAL callback. */
static __thread __attribute__((tls_model("initial-exec"))) int vh_alias = -1;

#define REAL_FN(name) static __typeof__(&name) real_##name
REAL_FN(snd_pcm_avail_delay);
REAL_FN(snd_pcm_prepare);
REAL_FN(snd_pcm_recover);
REAL_FN(snd_pcm_status);
REAL_FN(snd_pcm_start);
REAL_FN(snd_pcm_drop);
REAL_FN(snd_pcm_pause);
REAL_FN(snd_pcm_writei);
REAL_FN(snd_pcm_readi);
REAL_FN(snd_pcm_wait);
REAL_FN(snd_pcm_avail);
REAL_FN(snd_pcm_avail_update);
REAL_FN(snd_pcm_poll_descriptors);

static int vh_get_alias(struct vh_shared *s) {
  if (vh_alias == -1) {
    uint64_t next = __atomic_fetch_add(&s->next_alias, 1, __ATOMIC_RELAXED);
    vh_alias = next < VH_SLOTS ? (int)next : -2;
  }
  return vh_alias;
}

/*
 * The modified **experimental** NeXium CPAL data callback invokes only this
 * marker through a pointer resolved BEFORE stream.play(), not via a new
 * RT-time dlsym. Both marker and ALSA wrappers share this TLS slot.
 * Identical alias within one run is direct process-thread identity; alias
 * numbers across independent runs are unrelated.
 */
__attribute__((visibility("default")))
void vh_map02_stage308_cpal_callback_mark(void) {
  struct vh_shared *s = vh;
  if (!s) return;
  int alias=vh_get_alias(s);
  if (alias < 0) return;
  __atomic_fetch_add(&s->cpal_callback_entries[alias],1,__ATOMIC_RELAXED);
}

/*
 * All phase counters are per anonymous TLS alias, shared with the real
 * Stage308 CPAL callback marker. Never call gettid, clock, malloc or log.
 * Sampling these counters is strictly OUTSIDE the audio callback process.
 */
static int vh_phase_begin(unsigned op) {
  struct vh_shared *s=vh;
  if (!s || op>=VH_PHASE_OPS) return -1;
  int alias=vh_get_alias(s);
  if (alias>=0) __atomic_fetch_add(&s->phase[alias][op][0],1,__ATOMIC_RELAXED);
  return alias;
}
static void vh_phase_end(int alias,unsigned op,long long rc) {
  struct vh_shared *s=vh;
  if (!s || alias<0 || op>=VH_PHASE_OPS) return;
  if (rc<0) __atomic_fetch_add(&s->phase[alias][op][2],1,__ATOMIC_RELAXED);
  __atomic_fetch_add(&s->phase[alias][op][1],1,__ATOMIC_RELAXED);
}

static void vh_record(unsigned op, long long rc) {
  struct vh_shared *s = vh;
  if (!s || op >= VH_OPS) return;
  int alias=vh_get_alias(s);
  if (alias < 0) return;
  uint64_t *count = s->counters[alias][op];
  unsigned kind = KIND_OK;
  if (rc == -EIO) kind = KIND_EIO;
  else if (rc == -EPIPE) kind = KIND_EPIPE;
  else if (rc == -EAGAIN) kind = KIND_EAGAIN;
  else if (rc < 0) kind = KIND_OTHER_NEG;
  __atomic_fetch_add(&count[KIND_TOTAL], 1, __ATOMIC_RELAXED);
  __atomic_fetch_add(&count[kind], 1, __ATOMIC_RELAXED);
}

__attribute__((constructor))
static void vh_initialize(void) {
  const char *path = getenv("VH_STAGE305_ALSA_COUNTER_PATH");
  if (path && path[0] == '/') {
    int fd = open(path, O_RDWR | O_CLOEXEC | O_NOFOLLOW);
    if (fd >= 0) {
      struct stat st;
      if (fstat(fd, &st) == 0 && S_ISREG(st.st_mode) &&
          st.st_size == VH_SIZE) {
        void *mapped = mmap(NULL, VH_SIZE, PROT_READ | PROT_WRITE,
                            MAP_SHARED, fd, 0);
        if (mapped != MAP_FAILED) {
          struct vh_shared *candidate = (struct vh_shared *)mapped;
          if (memcmp(candidate->magic, VH_MAGIC, 8) == 0) {
            vh = candidate;
          } else {
            munmap(mapped, VH_SIZE);
          }
        }
      }
      close(fd);
    }
  }
#define RESOLVE(name) real_##name = (__typeof__(&name))dlsym(RTLD_NEXT, #name)
  RESOLVE(snd_pcm_avail_delay);
  RESOLVE(snd_pcm_prepare);
  RESOLVE(snd_pcm_recover);
  RESOLVE(snd_pcm_status);
  RESOLVE(snd_pcm_start);
  RESOLVE(snd_pcm_drop);
  RESOLVE(snd_pcm_pause);
  RESOLVE(snd_pcm_writei);
  RESOLVE(snd_pcm_readi);
  RESOLVE(snd_pcm_wait);
  RESOLVE(snd_pcm_avail);
  RESOLVE(snd_pcm_avail_update);
  RESOLVE(snd_pcm_poll_descriptors);
#undef RESOLVE
}

#define ASSERT_RESOLVED(fn) do { if (!(fn)) abort(); } while(0)
int snd_pcm_avail_delay(snd_pcm_t *pcm, snd_pcm_sframes_t *avail,
                        snd_pcm_sframes_t *delay) {
  ASSERT_RESOLVED(real_snd_pcm_avail_delay);
  int alias=vh_phase_begin(OP_AVAIL_DELAY);
  int rc = real_snd_pcm_avail_delay(pcm, avail, delay);
  vh_record(OP_AVAIL_DELAY, rc); vh_phase_end(alias,OP_AVAIL_DELAY,rc);
  return rc;
}
int snd_pcm_prepare(snd_pcm_t *pcm) {
  ASSERT_RESOLVED(real_snd_pcm_prepare);
  int alias=vh_phase_begin(OP_PREPARE);
  int rc = real_snd_pcm_prepare(pcm); vh_record(OP_PREPARE, rc); vh_phase_end(alias,OP_PREPARE,rc); return rc;
}
int snd_pcm_recover(snd_pcm_t *pcm, int err, int silent) {
  ASSERT_RESOLVED(real_snd_pcm_recover);
  int alias=vh_phase_begin(OP_RECOVER);
  int rc = real_snd_pcm_recover(pcm, err, silent);
  vh_record(OP_RECOVER, rc); vh_phase_end(alias,OP_RECOVER,rc); return rc;
}
int snd_pcm_status(snd_pcm_t *pcm, snd_pcm_status_t *status) {
  ASSERT_RESOLVED(real_snd_pcm_status);
  int alias=vh_phase_begin(OP_STATUS);
  int rc = real_snd_pcm_status(pcm, status);
  vh_record(OP_STATUS, rc); vh_phase_end(alias,OP_STATUS,rc); return rc;
}
int snd_pcm_start(snd_pcm_t *pcm) {
  ASSERT_RESOLVED(real_snd_pcm_start);
  int alias=vh_phase_begin(OP_START);
  int rc = real_snd_pcm_start(pcm); vh_record(OP_START, rc); vh_phase_end(alias,OP_START,rc); return rc;
}
int snd_pcm_drop(snd_pcm_t *pcm) {
  ASSERT_RESOLVED(real_snd_pcm_drop);
  int alias=vh_phase_begin(OP_DROP);
  int rc = real_snd_pcm_drop(pcm); vh_record(OP_DROP, rc); vh_phase_end(alias,OP_DROP,rc); return rc;
}
int snd_pcm_pause(snd_pcm_t *pcm, int enable) {
  ASSERT_RESOLVED(real_snd_pcm_pause);
  int alias=vh_phase_begin(OP_PAUSE);
  int rc = real_snd_pcm_pause(pcm, enable);
  vh_record(OP_PAUSE, rc); vh_phase_end(alias,OP_PAUSE,rc); return rc;
}
snd_pcm_sframes_t snd_pcm_writei(snd_pcm_t *pcm, const void *buffer,
                                 snd_pcm_uframes_t size) {
  ASSERT_RESOLVED(real_snd_pcm_writei);
  int alias=vh_phase_begin(OP_WRITEI);
  snd_pcm_sframes_t rc = real_snd_pcm_writei(pcm, buffer, size);
  vh_record(OP_WRITEI, rc); vh_phase_end(alias,OP_WRITEI,rc); return rc;
}
snd_pcm_sframes_t snd_pcm_readi(snd_pcm_t *pcm, void *buffer,
                                snd_pcm_uframes_t size) {
  ASSERT_RESOLVED(real_snd_pcm_readi);
  int alias=vh_phase_begin(OP_READI);
  snd_pcm_sframes_t rc = real_snd_pcm_readi(pcm, buffer, size);
  vh_record(OP_READI, rc); vh_phase_end(alias,OP_READI,rc); return rc;
}

/* Four new userspace ALSA exported functions are observed separately from
 * the original Stage305 9-op source counters. They forward exact return
 * codes and never claim to cover direct internal dlsym or CPAL mechanisms.
 */
int snd_pcm_wait(snd_pcm_t *pcm, int timeout) {
  ASSERT_RESOLVED(real_snd_pcm_wait);
  int alias=vh_phase_begin(OP_WAIT);
  int rc=real_snd_pcm_wait(pcm,timeout);
  vh_phase_end(alias,OP_WAIT,rc);
  return rc;
}
snd_pcm_sframes_t snd_pcm_avail(snd_pcm_t *pcm) {
  ASSERT_RESOLVED(real_snd_pcm_avail);
  int alias=vh_phase_begin(OP_AVAIL);
  snd_pcm_sframes_t rc=real_snd_pcm_avail(pcm);
  vh_phase_end(alias,OP_AVAIL,rc);
  return rc;
}
snd_pcm_sframes_t snd_pcm_avail_update(snd_pcm_t *pcm) {
  ASSERT_RESOLVED(real_snd_pcm_avail_update);
  int alias=vh_phase_begin(OP_AVAIL_UPDATE);
  snd_pcm_sframes_t rc=real_snd_pcm_avail_update(pcm);
  vh_phase_end(alias,OP_AVAIL_UPDATE,rc);
  return rc;
}
int snd_pcm_poll_descriptors(snd_pcm_t *pcm,struct pollfd *pfds,unsigned int space) {
  ASSERT_RESOLVED(real_snd_pcm_poll_descriptors);
  int alias=vh_phase_begin(OP_POLL_DESCRIPTORS);
  int rc=real_snd_pcm_poll_descriptors(pcm,pfds,space);
  vh_phase_end(alias,OP_POLL_DESCRIPTORS,rc);
  return rc;
}
