/*
 * Stage308 opt-in same-process thread-identity marker (inherits Stage305 ALSA interposer).
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
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#define VH_SLOTS 64
#define VH_OPS 9
#define VH_KINDS 6
#define VH_SIZE 65536
#define VH_MAGIC "VH305AL1"

enum {
  OP_AVAIL_DELAY, OP_PREPARE, OP_RECOVER, OP_STATUS, OP_START,
  OP_DROP, OP_PAUSE, OP_WRITEI, OP_READI
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
};

static struct vh_shared *vh = NULL;
static __thread int vh_alias = -1;

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
#undef RESOLVE
}

#define ASSERT_RESOLVED(fn) do { if (!(fn)) abort(); } while(0)
int snd_pcm_avail_delay(snd_pcm_t *pcm, snd_pcm_sframes_t *avail,
                        snd_pcm_sframes_t *delay) {
  ASSERT_RESOLVED(real_snd_pcm_avail_delay);
  int rc = real_snd_pcm_avail_delay(pcm, avail, delay);
  vh_record(OP_AVAIL_DELAY, rc);
  return rc;
}
int snd_pcm_prepare(snd_pcm_t *pcm) {
  ASSERT_RESOLVED(real_snd_pcm_prepare);
  int rc = real_snd_pcm_prepare(pcm); vh_record(OP_PREPARE, rc); return rc;
}
int snd_pcm_recover(snd_pcm_t *pcm, int err, int silent) {
  ASSERT_RESOLVED(real_snd_pcm_recover);
  int rc = real_snd_pcm_recover(pcm, err, silent);
  vh_record(OP_RECOVER, rc); return rc;
}
int snd_pcm_status(snd_pcm_t *pcm, snd_pcm_status_t *status) {
  ASSERT_RESOLVED(real_snd_pcm_status);
  int rc = real_snd_pcm_status(pcm, status);
  vh_record(OP_STATUS, rc); return rc;
}
int snd_pcm_start(snd_pcm_t *pcm) {
  ASSERT_RESOLVED(real_snd_pcm_start);
  int rc = real_snd_pcm_start(pcm); vh_record(OP_START, rc); return rc;
}
int snd_pcm_drop(snd_pcm_t *pcm) {
  ASSERT_RESOLVED(real_snd_pcm_drop);
  int rc = real_snd_pcm_drop(pcm); vh_record(OP_DROP, rc); return rc;
}
int snd_pcm_pause(snd_pcm_t *pcm, int enable) {
  ASSERT_RESOLVED(real_snd_pcm_pause);
  int rc = real_snd_pcm_pause(pcm, enable);
  vh_record(OP_PAUSE, rc); return rc;
}
snd_pcm_sframes_t snd_pcm_writei(snd_pcm_t *pcm, const void *buffer,
                                 snd_pcm_uframes_t size) {
  ASSERT_RESOLVED(real_snd_pcm_writei);
  snd_pcm_sframes_t rc = real_snd_pcm_writei(pcm, buffer, size);
  vh_record(OP_WRITEI, rc); return rc;
}
snd_pcm_sframes_t snd_pcm_readi(snd_pcm_t *pcm, void *buffer,
                                snd_pcm_uframes_t size) {
  ASSERT_RESOLVED(real_snd_pcm_readi);
  snd_pcm_sframes_t rc = real_snd_pcm_readi(pcm, buffer, size);
  vh_record(OP_READI, rc); return rc;
}
