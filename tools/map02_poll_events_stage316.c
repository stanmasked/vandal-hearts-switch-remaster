/*
 * Stage316 opt-in two-position poll requested/returned event-class counters; preserves Stage315 source.
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
#include <sys/syscall.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <sys/epoll.h>
#include <time.h>
#include <unistd.h>

#define VH_SLOTS 64
#define VH_OPS 9
#define VH_KINDS 6
#define VH_PHASE_OPS 13
#define VH_PHASE_OFFSET 33792
#define VH_PRIVATE_TID_OFFSET 53760
#define VH_LIBC_WAIT_OFFSET 54784
#define VH_LIBC_WAIT_OPS 4
#define VH_POLL_ARGUMENT_OFFSET 60928
#define VH_POLL_META_FIELDS 9
#define VH_POLL_EVENT_OFFSET 27664
#define VH_POLL_EVENT_FIELDS 9
#define VH_POLL_EVENT_STATE_OFFSET 33280
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
  /*
   * Stage316 uses 4608 previously reserved bytes in Stage305/308 hole.
   * These are only cumulative anonymous *ordinal 0/1* event-class counts
   * for poll(nfds==2), never fd numbers or raw pollfd/revents/event masks.
   */
  uint64_t poll_event_categories[VH_SLOTS][VH_POLL_EVENT_FIELDS];
  unsigned char padding[32768 - (16 + VH_SLOTS*VH_OPS*VH_KINDS*8)
                        - VH_SLOTS*VH_POLL_EVENT_FIELDS*8];
  uint64_t cpal_callback_entries[VH_SLOTS];
  /* One aligned atomic 64-bit state per TLS alias in the former Stage311
   * padding. Low byte is the currently active two-position poll request;
   * the next byte is the last completed return. Updating/clearing the
   * active byte and publishing the return are one atomic state transition. */
  uint64_t poll_event_state[VH_SLOTS];
  /* Each independently sampled (begin, return, negative_return) is atomic.
   * NEVER treat a single sampled in-flight phase as a deadlock. */
  uint64_t phase[VH_SLOTS][VH_PHASE_OPS][3];
  /*
   * PRIVATE process mmap only! External Stage313 observer joins TIDs with
   * live /proc before exporting solely anonymized aliases.
   * No raw kernel TID may ever be published to CI artifacts or user logs.
   */
  uint64_t native_tid_PRIVATE[VH_SLOTS];
  unsigned char stage314_alignment_padding[512];
  /* begin/return/negative-return; no kernel parameters or addresses stored.
   * This does NOT intercept direct raw syscalls or hidden backend wait sites. */
  uint64_t libc_wait_phase[VH_SLOTS][VH_LIBC_WAIT_OPS][3];
  /* Only coarse numeric arguments and return categories, NEVER descriptor
   * identities, event masks, pollfd contents, caller stacks or OS TIDs.
   * Field indexes: last timeout-encoded, capped number of descriptors,
   * calls with timeout -1, calls timeout 0, calls positive timeout,
   * returns ready>0, returns timed-out==0, returns error<0,
   * calls with unexpected timeout below -1.
   */
  uint64_t poll_meta[VH_SLOTS][VH_POLL_META_FIELDS];
};
_Static_assert(offsetof(struct vh_shared, poll_event_categories)==VH_POLL_EVENT_OFFSET,
               "Stage316 event counters in original unused source memory gap");
_Static_assert(offsetof(struct vh_shared, poll_event_state)==VH_POLL_EVENT_STATE_OFFSET,
               "Stage316 active poll state fits former Stage311 reserved bytes");
_Static_assert(offsetof(struct vh_shared, cpal_callback_entries)==32768,
               "CPAL anonymous TLS counter must be at stable mmap byte offset");
_Static_assert(offsetof(struct vh_shared, phase)==VH_PHASE_OFFSET,
               "Stage311 phase counters must occupy stable reserved offset");
_Static_assert(offsetof(struct vh_shared, native_tid_PRIVATE)==VH_PRIVATE_TID_OFFSET,
               "Stage313 private kernel TID must have fixed mmap byte offset");
_Static_assert(offsetof(struct vh_shared, libc_wait_phase)==VH_LIBC_WAIT_OFFSET,
               "Stage314 private libc waits must fit in existing bounded map");
_Static_assert(offsetof(struct vh_shared, poll_meta)==VH_POLL_ARGUMENT_OFFSET,
               "Stage315 appended coarse poll metadata must exactly fill reserved mmap");
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
REAL_FN(poll);
REAL_FN(ppoll);
REAL_FN(epoll_wait);
REAL_FN(epoll_pwait);

static int vh_get_alias(struct vh_shared *s) {
  if (vh_alias == -1) {
    uint64_t next = __atomic_fetch_add(&s->next_alias, 1, __ATOMIC_RELAXED);
    vh_alias = next < VH_SLOTS ? (int)next : -2;
    if (vh_alias >= 0) {
      /* Once per thread, not once per callback. May run during the first
       * CPAL callback: strictly intrusive research-only scheduler control.
       * syscall does not write a log or allocate user-visible memory. */
      long tid=syscall(SYS_gettid);
      if (tid>0)
        __atomic_store_n(&s->native_tid_PRIVATE[vh_alias],
                         (uint64_t)tid,__ATOMIC_RELEASE);
    }
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
 * Stage308 CPAL callback marker. One SYS_gettid is performed on FIRST alias creation, possibly RT-side. No per-callback gettid, clock, malloc or log.
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
  RESOLVE(poll);
  RESOLVE(ppoll);
  RESOLVE(epoll_wait);
  RESOLVE(epoll_pwait);
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

/* Stage314 libc boundary-only research. The one-time native alias lookup
 * potentially invokes gettid if this is the first entry on a given thread.
 * Once assigned, counts are relaxed-atomic only. No logging, clocks, malloc
 * or OS thread identifiers in emitted source evidence.
 */
static int vh_libc_begin(unsigned op) {
  struct vh_shared *s=vh;
  if (!s || op>=VH_LIBC_WAIT_OPS) return -1;
  int alias=vh_get_alias(s);
  if (alias>=0)
    __atomic_fetch_add(&s->libc_wait_phase[alias][op][0],1,__ATOMIC_RELAXED);
  return alias;
}
static void vh_libc_finish(int alias,unsigned op,int rc) {
  struct vh_shared *s=vh;
  if (!s || alias<0 || op>=VH_LIBC_WAIT_OPS) return;
  if (rc<0)
    __atomic_fetch_add(&s->libc_wait_phase[alias][op][2],1,__ATOMIC_RELAXED);
  __atomic_fetch_add(&s->libc_wait_phase[alias][op][1],1,__ATOMIC_RELAXED);
}
enum {
  VH_POLL_LAST_TIMEOUT_PLUS_ONE,
  VH_POLL_LAST_NFDS_CAPPED,
  VH_POLL_TIMEOUT_INFINITE_COUNT,
  VH_POLL_TIMEOUT_IMMEDIATE_COUNT,
  VH_POLL_TIMEOUT_FINITE_COUNT,
  VH_POLL_RETURN_FD_READY_COUNT,
  VH_POLL_RETURN_ZERO_COUNT,
  VH_POLL_RETURN_ERROR_COUNT,
  VH_POLL_TIMEOUT_INVALID_NEGATIVE_COUNT
};
static void vh_poll_arguments(int alias,nfds_t nfds,int timeout) {
  struct vh_shared *s=vh;
  if (!s || alias<0 || alias>=VH_SLOTS) return;
  uint64_t *v=s->poll_meta[alias];
  /* This is the timeout of the MOST RECENT call entry on a native thread.
   * UINT64_MAX indicates unsupported timeout < -1; no FD values copied.
   * The kernel-visible poll timeout can differ due to libc/ALSA behavior. */
  uint64_t encoded=(timeout<-1) ? UINT64_MAX
                               : (uint64_t)((int64_t)timeout+1);
  __atomic_store_n(&v[VH_POLL_LAST_TIMEOUT_PLUS_ONE],encoded,__ATOMIC_RELAXED);
  __atomic_store_n(&v[VH_POLL_LAST_NFDS_CAPPED],
                   nfds<=64 ? (uint64_t)nfds : 65,__ATOMIC_RELAXED);
  unsigned slot=timeout==-1 ? VH_POLL_TIMEOUT_INFINITE_COUNT
               : timeout==0 ? VH_POLL_TIMEOUT_IMMEDIATE_COUNT
               : timeout>0 ? VH_POLL_TIMEOUT_FINITE_COUNT
               : VH_POLL_TIMEOUT_INVALID_NEGATIVE_COUNT;
  __atomic_fetch_add(&v[slot],1,__ATOMIC_RELAXED);
}
static void vh_poll_return(int alias,int rc) {
  struct vh_shared *s=vh;
  if (!s || alias<0 || alias>=VH_SLOTS) return;
  uint64_t *v=s->poll_meta[alias];
  unsigned slot=rc>0 ? VH_POLL_RETURN_FD_READY_COUNT
               : rc==0 ? VH_POLL_RETURN_ZERO_COUNT
               : VH_POLL_RETURN_ERROR_COUNT;
  __atomic_fetch_add(&v[slot],1,__ATOMIC_RELAXED);
}
enum {
  VH_ORD0_REQUEST_POLLIN, VH_ORD0_REQUEST_POLLOUT,
  VH_ORD1_REQUEST_POLLIN, VH_ORD1_REQUEST_POLLOUT,
  VH_ORD0_RETURN_POLLIN, VH_ORD0_RETURN_POLLOUT,
  VH_ORD1_RETURN_POLLIN, VH_ORD1_RETURN_POLLOUT,
  VH_RETURN_EXCEPTIONAL_ANY
};
static void vh_poll_event_entry(int alias,const struct pollfd *fds,nfds_t nfds) {
  struct vh_shared *s=vh;
  if (!s || alias<0 || alias>=VH_SLOTS) return;
  uint8_t code=0;
  if (nfds==2 && fds) {
    /* Bit 7 marks a valid two-position snapshot. Bits 0..3 mean
     * ordinal0 IN/OUT and ordinal1 IN/OUT. Other request bits are not saved. */
    short a=fds[0].events, b=fds[1].events;
    code=0x80;
    if (a&POLLIN) code|=1u<<0;
    if (a&POLLOUT) code|=1u<<1;
    if (b&POLLIN) code|=1u<<2;
    if (b&POLLOUT) code|=1u<<3;
    uint64_t *v=s->poll_event_categories[alias];
    if (a&POLLIN) __atomic_fetch_add(&v[VH_ORD0_REQUEST_POLLIN],1,__ATOMIC_RELAXED);
    if (a&POLLOUT) __atomic_fetch_add(&v[VH_ORD0_REQUEST_POLLOUT],1,__ATOMIC_RELAXED);
    if (b&POLLIN) __atomic_fetch_add(&v[VH_ORD1_REQUEST_POLLIN],1,__ATOMIC_RELAXED);
    if (b&POLLOUT) __atomic_fetch_add(&v[VH_ORD1_REQUEST_POLLOUT],1,__ATOMIC_RELAXED);
  }
  /* Keep the previous return in the high byte, but publish the active
   * request (or zero for any other poll shape) in the low byte. */
  uint64_t state=__atomic_load_n(&s->poll_event_state[alias],__ATOMIC_RELAXED);
  __atomic_store_n(&s->poll_event_state[alias],
                   (state&~UINT64_C(0xff))|code,__ATOMIC_RELAXED);
}
static void vh_poll_event_return(int alias,const struct pollfd *fds,nfds_t nfds,int rc) {
  struct vh_shared *s=vh;
  if (!s || alias<0 || alias>=VH_SLOTS) return;
  uint8_t code=0;
  if (nfds==2 && fds) {
    /* Return status bits 5..6: 1=ready, 2=timeout, 3=error.
     * Bit 7 marks two valid positions; bits 0..3 encode IN/OUT per ordinal;
     * bit 4 flags at least one exceptional revent (ERR/HUP/NVAL/PRI). */
    unsigned status=rc>0 ? 1u : rc==0 ? 2u : 3u;
    code=(uint8_t)(0x80u|(status<<5));
    if (rc>0) {
      uint64_t *v=s->poll_event_categories[alias];
      short a=fds[0].revents, b=fds[1].revents;
      if (a&POLLIN) { code|=1u<<0; __atomic_fetch_add(&v[VH_ORD0_RETURN_POLLIN],1,__ATOMIC_RELAXED); }
      if (a&POLLOUT) { code|=1u<<1; __atomic_fetch_add(&v[VH_ORD0_RETURN_POLLOUT],1,__ATOMIC_RELAXED); }
      if (b&POLLIN) { code|=1u<<2; __atomic_fetch_add(&v[VH_ORD1_RETURN_POLLIN],1,__ATOMIC_RELAXED); }
      if (b&POLLOUT) { code|=1u<<3; __atomic_fetch_add(&v[VH_ORD1_RETURN_POLLOUT],1,__ATOMIC_RELAXED); }
      if ((a|b)&(POLLERR|POLLHUP|POLLNVAL|POLLPRI)) {
        code|=1u<<4;
        __atomic_fetch_add(&v[VH_RETURN_EXCEPTIONAL_ANY],1,__ATOMIC_RELAXED);
      }
    }
  }
  /* One atomic 64-bit transition clears the active request and publishes
   * the last completed return; a reader can never combine a stale active
   * request with the newly completed result. */
  __atomic_store_n(&s->poll_event_state[alias],((uint64_t)code)<<8,
                   __ATOMIC_RELAXED);
}
/* POSIX poll is a cancellation point. If its caller is canceled while
 * blocked, normal return bookkeeping never executes. Clear only the active
 * request byte and preserve the last completed return byte. The unmatched
 * libc entry/return counters remain evidence of an interrupted call. */
static void vh_poll_event_cancel_cleanup(void *opaque) {
  const int alias=*(const int *)opaque;
  struct vh_shared *s=vh;
  if (!s || alias<0 || alias>=VH_SLOTS) return;
  __atomic_fetch_and(&s->poll_event_state[alias], ~UINT64_C(0xff),
                     __ATOMIC_RELAXED);
}

int poll(struct pollfd *fds,nfds_t nfds,int timeout) {
  ASSERT_RESOLVED(real_poll);
  int alias=vh_libc_begin(0);
  vh_poll_arguments(alias,nfds,timeout);
  int rc;
  /* Register before publishing an active request. Keep cleanup installed
   * until the atomic active/last-return transition has completed. */
  pthread_cleanup_push(vh_poll_event_cancel_cleanup, &alias);
  vh_poll_event_entry(alias,fds,nfds);
  rc=real_poll(fds,nfds,timeout);
  vh_poll_event_return(alias,fds,nfds,rc);
  pthread_cleanup_pop(0);
  vh_poll_return(alias,rc);
  vh_libc_finish(alias,0,rc);
  return rc;
}
int ppoll(struct pollfd *fds,nfds_t nfds,
          const struct timespec *timeout,const sigset_t *mask) {
  ASSERT_RESOLVED(real_ppoll);
  int alias=vh_libc_begin(1);
  int rc=real_ppoll(fds,nfds,timeout,mask);
  vh_libc_finish(alias,1,rc);
  return rc;
}
int epoll_wait(int epfd,struct epoll_event *events,int maxevents,int timeout) {
  ASSERT_RESOLVED(real_epoll_wait);
  int alias=vh_libc_begin(2);
  int rc=real_epoll_wait(epfd,events,maxevents,timeout);
  vh_libc_finish(alias,2,rc);
  return rc;
}
int epoll_pwait(int epfd,struct epoll_event *events,int maxevents,
                int timeout,const sigset_t *mask) {
  ASSERT_RESOLVED(real_epoll_pwait);
  int alias=vh_libc_begin(3);
  int rc=real_epoll_pwait(epfd,events,maxevents,timeout,mask);
  vh_libc_finish(alias,3,rc);
  return rc;
}
