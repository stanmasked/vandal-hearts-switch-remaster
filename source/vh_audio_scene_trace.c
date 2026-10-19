#include "vh_audio_scene_trace.h"

#include <inttypes.h>
#include <stddef.h>

void vh_audio_scene_trace_init(VhAudioSceneTrace *trace) {
    if (!trace) return;
    atomic_init(&trace->reserved, 0u);
    atomic_init(&trace->dropped, 0u);
    for (unsigned i=0; i<VH_AUDIO_SCENE_TRACE_CAPACITY; ++i) {
        atomic_init(&trace->slot[i].ready, 0u);
        trace->slot[i].kind = 0;
        trace->slot[i].serial = 0;
        trace->slot[i].scene = 0;
        trace->slot[i].monotonic_ns = 0;
    }
}

int vh_audio_scene_trace_record(VhAudioSceneTrace *trace,
                                VhAudioSceneTraceKind kind,
                                unsigned serial, unsigned scene,
                                uint64_t monotonic_ns) {
    if (!trace || kind<VH_SCENE_TRACE_INPUT || kind>VH_SCENE_TRACE_PCM_PAGE_SILENT ||
        scene>2u) return -1;
    const unsigned index = atomic_fetch_add_explicit(
        &trace->reserved, 1u, memory_order_relaxed);
    if (index >= VH_AUDIO_SCENE_TRACE_CAPACITY) {
        atomic_fetch_add_explicit(&trace->dropped, 1u,
                                  memory_order_relaxed);
        return 0;
    }
    VhAudioSceneTraceSlot *slot = &trace->slot[index];
    slot->kind = (unsigned)kind;
    slot->serial = serial;
    slot->scene = scene;
    slot->monotonic_ns = monotonic_ns;
    atomic_store_explicit(&slot->ready, 1u, memory_order_release);
    return 1;
}

int vh_audio_scene_trace_snapshot(const VhAudioSceneTrace *trace,
                                  unsigned index,
                                  VhAudioSceneTraceSlot *out) {
    if (!trace || !out || index>=VH_AUDIO_SCENE_TRACE_CAPACITY) return -1;
    if (index>=atomic_load_explicit(&trace->reserved,memory_order_acquire) ||
        !atomic_load_explicit(&trace->slot[index].ready,
                              memory_order_acquire)) return 0;
    const VhAudioSceneTraceSlot *slot=&trace->slot[index];
    /* out->ready is atomic and never copied by C11 struct assignment. */
    out->kind=slot->kind;
    out->serial=slot->serial;
    out->scene=slot->scene;
    out->monotonic_ns=slot->monotonic_ns;
    return 1;
}

static const char *name(unsigned kind) {
    switch(kind) {
    case VH_SCENE_TRACE_INPUT: return "INPUT";
    case VH_SCENE_TRACE_POST: return "POST";
    case VH_SCENE_TRACE_ACCEPT: return "ACCEPT";
    case VH_SCENE_TRACE_SUBMIT_CALL: return "SUBMIT_CALL";
    case VH_SCENE_TRACE_RELEASE_RETURN: return "RELEASE_RETURN";
    case VH_SCENE_TRACE_SUBMIT_ERROR: return "SUBMIT_ERROR";
    default: return "INVALID";
    }
}

int vh_audio_scene_trace_write_csv(const VhAudioSceneTrace *trace,
                                    FILE *out) {
    if (!trace || !out) return -1;
    if (fputs("index,event,serial,scene,monotonic_ns\n",out)<0) return -1;
    unsigned count=atomic_load_explicit(&trace->reserved,
                                         memory_order_acquire);
    if (count>VH_AUDIO_SCENE_TRACE_CAPACITY)
        count=VH_AUDIO_SCENE_TRACE_CAPACITY;
    for (unsigned i=0; i<count; ++i) {
        VhAudioSceneTraceSlot snapshot;
        if (vh_audio_scene_trace_snapshot(trace,i,&snapshot)!=1) return -1;
        if (fprintf(out,"%u,%s,%u,%u,%" PRIu64 "\n",i,
                    name(snapshot.kind),snapshot.serial,snapshot.scene,
                    snapshot.monotonic_ns)<0) return -1;
    }
    return (int)count;
}

unsigned vh_audio_scene_trace_dropped(const VhAudioSceneTrace *trace) {
    return trace ? atomic_load_explicit(&trace->dropped,
                                        memory_order_acquire) : 0;
}
