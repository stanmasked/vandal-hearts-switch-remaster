/*
 * MAP02 Stage273 opt-in Linux NeXium ALSA lifetime COUNTERS.
 * No PCM samples, no original game data, no raw pointer values on disk.
 * Counter mode replaces (not adds to) 256-entry per-write CSV trace.
 * Time-sampled every 200ms; abrupt SIGKILL loses <= one nominal interval.
 * Even this opt-in wrapper changes ALSA scheduling, so not a production fix.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

typedef struct _snd_pcm snd_pcm_t;
typedef struct _snd_pcm_hw_params snd_pcm_hw_params_t;
typedef unsigned long snd_pcm_uframes_t;
typedef long snd_pcm_sframes_t;
enum { SLOTS=32, TICK_NS=200000000 };
typedef struct {
    _Atomic(uintptr_t) ptr; /* never written to artifacts */
    _Atomic unsigned id, rate, channels;
    _Atomic unsigned long period, buffer;
    _Atomic uint64_t write_calls, mmap_calls, positive_frames, errors;
} Entry;
static Entry slots[SLOTS];
static atomic_flag slot_lock=ATOMIC_FLAG_INIT;
static unsigned next_id=1;
static _Atomic int enabled=0, stop_requested=0;
static pthread_t reporter;
static char log_path[820];

static void lock_slots(void) {
    while(atomic_flag_test_and_set_explicit(&slot_lock,memory_order_acquire)) {}
}
static void unlock_slots(void) {
    atomic_flag_clear_explicit(&slot_lock,memory_order_release);
}
static Entry *lookup(snd_pcm_t *p) {
    if (!p) return NULL;
    uintptr_t ptr=(uintptr_t)p;
    for (unsigned n=0;n<SLOTS;n++) {
        if (atomic_load_explicit(&slots[n].ptr,memory_order_acquire)==ptr)
            return &slots[n];
    }
    lock_slots();
    Entry *found=NULL;
    for (unsigned n=0;n<SLOTS;n++) {
        if (atomic_load(&slots[n].ptr)==ptr) {found=&slots[n];break;}
    }
    if (!found) {
        for (unsigned n=0;n<SLOTS;n++) {
            if (atomic_load(&slots[n].ptr)==0) {
                found=&slots[n];
                atomic_store(&found->id,next_id++);
                atomic_store(&found->rate,0);
                atomic_store(&found->channels,0);
                atomic_store(&found->period,0);
                atomic_store(&found->buffer,0);
                atomic_store(&found->write_calls,0);
                atomic_store(&found->mmap_calls,0);
                atomic_store(&found->positive_frames,0);
                atomic_store(&found->errors,0);
                atomic_store_explicit(&found->ptr,ptr,memory_order_release);
                break;
            }
        }
    }
    unlock_slots();
    return found; /* NULL => untracked, never infer ownership */
}
static uint64_t now_ns(void) {
    struct timespec ts={0,0};
    if(clock_gettime(CLOCK_MONOTONIC,&ts))return 0;
    return (uint64_t)ts.tv_sec*UINT64_C(1000000000)+(uint64_t)ts.tv_nsec;
}
static void *symbol(const char *name) {
    void *p=dlsym(RTLD_NEXT,name);
    if(!p)_exit(120);
    return p;
}
static void write_snapshot(void) {
    if(!atomic_load(&enabled))return;
    const uint64_t now=now_ns();
    if(!now)return;
    int fd=open(log_path,O_WRONLY|O_APPEND|O_CREAT|O_CLOEXEC,0600);
    if(fd<0)return;
    char line[256];
    int n=snprintf(line,sizeof(line),
                   "T,%" PRIu64 ",0,0,0,0,0,0,0,0,0\n",now);
    if(n>0&&(size_t)n<sizeof(line)) {
        ssize_t written=write(fd,line,(size_t)n);
        if(written!=n) {close(fd);return;} /* incomplete snapshot fails audit */
    }
    for (unsigned i=0;i<SLOTS;i++) {
        Entry *e=&slots[i];
        unsigned id=atomic_load(&e->id);
        if (!id||!atomic_load(&e->ptr))continue;
        n=snprintf(line,sizeof(line),
                   "S,%" PRIu64 ",%u,%u,%u,%lu,%lu,"
                   "%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "\n",
                   now,id,atomic_load(&e->rate),atomic_load(&e->channels),
                   atomic_load(&e->period),atomic_load(&e->buffer),
                   atomic_load(&e->write_calls),atomic_load(&e->mmap_calls),
                   atomic_load(&e->positive_frames),atomic_load(&e->errors));
        if(n>0&&(size_t)n<sizeof(line)) {
        ssize_t written=write(fd,line,(size_t)n);
        if(written!=n) {close(fd);return;} /* incomplete snapshot fails audit */
    }
    }
    close(fd);
}
static void *report_loop(void *arg) {
    (void)arg;
    write_snapshot(); /* initial time marker */
    struct timespec sleep_for={0,TICK_NS};
    while(!atomic_load(&stop_requested)) {
        (void)nanosleep(&sleep_for,NULL);
        write_snapshot();
    }
    return NULL;
}
__attribute__((constructor))
static void start_reporter(void) {
    const char *p=getenv("VH_MAP02_ALSA_LIFETIME_PATH");
    if(!p||*p!='/'||strlen(p)>800)return;
    memcpy(log_path,p,strlen(p)+1);
    atomic_store(&enabled,1);
    if(pthread_create(&reporter,NULL,report_loop,NULL)!=0)
        atomic_store(&enabled,0);
}
__attribute__((destructor))
static void finish_reporter(void) {
    if(!atomic_load(&enabled))return;
    atomic_store(&stop_requested,1);
    (void)pthread_join(reporter,NULL);
    write_snapshot();
}
int snd_pcm_hw_params(snd_pcm_t *p, snd_pcm_hw_params_t *par) {
    typedef int (*real_t)(snd_pcm_t*,snd_pcm_hw_params_t*);
    int ret=((real_t)symbol("snd_pcm_hw_params"))(p,par);
    if(ret==0 && atomic_load(&enabled)) {
        Entry *e=lookup(p);
        if(e) {
            unsigned rate=0,channels=0;
            snd_pcm_uframes_t period=0,buffer=0;
            int dir=0;
            typedef int (*g_u)(const snd_pcm_hw_params_t*,unsigned*);
            typedef int (*g_r)(const snd_pcm_hw_params_t*,unsigned*,int*);
            typedef int (*g_f)(const snd_pcm_hw_params_t*,snd_pcm_uframes_t*);
            typedef int (*g_d)(const snd_pcm_hw_params_t*,snd_pcm_uframes_t*,int*);
            g_u gc=(g_u)dlsym(RTLD_NEXT,"snd_pcm_hw_params_get_channels");
            g_r gr=(g_r)dlsym(RTLD_NEXT,"snd_pcm_hw_params_get_rate");
            g_f gb=(g_f)dlsym(RTLD_NEXT,"snd_pcm_hw_params_get_buffer_size");
            g_d gp=(g_d)dlsym(RTLD_NEXT,"snd_pcm_hw_params_get_period_size");
            if(gc&&(gc(par,&channels)!=0))channels=0;
            if(gr&&(gr(par,&rate,&dir)!=0))rate=0;
            if(gb&&(gb(par,&buffer)!=0))buffer=0;
            if(gp&&(gp(par,&period,&dir)!=0))period=0;
            atomic_store(&e->channels,channels);
            atomic_store(&e->rate,rate);
            atomic_store(&e->period,period);
            atomic_store(&e->buffer,buffer);
        }
    }
    return ret;
}
static void count_transfer(Entry *e, int mmap, snd_pcm_sframes_t ret) {
    if(!e)return;
    if(mmap)atomic_fetch_add(&e->mmap_calls,1);
    else atomic_fetch_add(&e->write_calls,1);
    if(ret>0)atomic_fetch_add(&e->positive_frames,(uint64_t)ret);
    else if(ret<0)atomic_fetch_add(&e->errors,1);
}
snd_pcm_sframes_t snd_pcm_writei(snd_pcm_t *p,const void *data,snd_pcm_uframes_t frames) {
    typedef snd_pcm_sframes_t(*fn)(snd_pcm_t*,const void*,snd_pcm_uframes_t);
    snd_pcm_sframes_t ret=((fn)symbol("snd_pcm_writei"))(p,data,frames);
    if(atomic_load(&enabled))count_transfer(lookup(p),0,ret);
    return ret;
}
snd_pcm_sframes_t snd_pcm_mmap_commit(snd_pcm_t *p,snd_pcm_uframes_t off,
                                      snd_pcm_uframes_t frames) {
    typedef snd_pcm_sframes_t(*fn)(snd_pcm_t*,snd_pcm_uframes_t,snd_pcm_uframes_t);
    snd_pcm_sframes_t ret=((fn)symbol("snd_pcm_mmap_commit"))(p,off,frames);
    if(atomic_load(&enabled))count_transfer(lookup(p),1,ret);
    return ret;
}
int snd_pcm_close(snd_pcm_t *p) {
    typedef int(*fn)(snd_pcm_t*);
    int ret=((fn)symbol("snd_pcm_close"))(p);
    if(!ret && atomic_load(&enabled)) {
        lock_slots();
        for(unsigned i=0;i<SLOTS;i++) {
            if(atomic_load(&slots[i].ptr)==(uintptr_t)p) {
                atomic_store(&slots[i].ptr,0);
                break;
            }
        }
        unlock_slots();
    }
    return ret;
}
